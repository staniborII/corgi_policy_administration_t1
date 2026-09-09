import uuid
from datetime import date
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.brokers.models import Broker
from apps.ledger.models import LedgerAccount
from apps.payments.models import Payment
from apps.payments.services import handle_payment_success, handle_refund_success
from apps.policies.models import FeeRule, TaxRule
from apps.policies.services import cancel_policy, issue_policy
from apps.reconciliation.models import ReconciliationBreak, ReconciliationRun
from apps.reconciliation.services import resolve_break, run_reconciliation


@pytest.fixture
def _chart_of_accounts(db):
    accounts = [
        ("1000", "Cash", "ASSET", "DEBIT"),
        ("1010", "Stripe Clearing", "ASSET", "DEBIT"),
        ("1100", "Premium Receivable", "ASSET", "DEBIT"),
        ("2000", "Unearned Premium", "LIABILITY", "CREDIT"),
        ("2100", "State Premium Tax Payable", "LIABILITY", "CREDIT"),
        ("2150", "Stamping Fee Payable", "LIABILITY", "CREDIT"),
        ("2200", "Broker Commission Payable", "LIABILITY", "CREDIT"),
        ("2300", "Claim Reserve", "LIABILITY", "CREDIT"),
        ("2400", "Refund Payable", "LIABILITY", "CREDIT"),
        ("4000", "Earned Premium", "REVENUE", "CREDIT"),
        ("4100", "Fee Revenue", "REVENUE", "CREDIT"),
        ("4200", "Commission Clawback", "REVENUE", "CREDIT"),
        ("5000", "Claims Expense", "EXPENSE", "DEBIT"),
        ("5100", "Commission Expense", "EXPENSE", "DEBIT"),
    ]
    for code, name, acct_type, normal in accounts:
        LedgerAccount.objects.create(code=code, name=name, account_type=acct_type, normal_balance=normal)


@pytest.fixture
def _tx_rules(db):
    TaxRule.objects.create(
        jurisdiction="TX",
        name="TX Surplus Lines Premium Tax",
        component_type="TAX",
        rate_bps=485,
        effective_from=date(2024, 1, 1),
        is_refundable=True,
    )
    FeeRule.objects.create(
        jurisdiction="TX",
        name="TX SLTX Stamping Fee",
        fee_type="RATE",
        rate_bps=4,
        effective_from=date(2024, 1, 1),
        is_refundable=True,
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="staff1", password="testpass", role=User.Role.STAFF, is_staff=True)


@pytest.fixture
def customer(db):
    return User.objects.create_user(username="customer", password="testpass", role=User.Role.CUSTOMER)


@pytest.fixture
def broker(db):
    user = User.objects.create_user(username="broker_user", password="pass", role=User.Role.STAFF)
    return Broker.objects.create(
        user=user,
        company_name="Test Broker",
        status=Broker.Status.APPROVED,
        commission_rate_bps=1500,
    )


@pytest.fixture
def active_policy(_chart_of_accounts, _tx_rules, customer, broker, staff_user):
    policy, charges = issue_policy(
        customer=customer,
        broker_id=broker.id,
        effective_date=date(2025, 1, 1),
        premium_amount_cents=100_000,
        coverage_territory="TX",
        created_by=staff_user,
    )
    now = timezone.now()
    payment = Payment.objects.create(
        policy=policy,
        amount_cents=charges["total_cents"],
        status=Payment.Status.PENDING,
        stripe_checkout_session_id=f"SIMULATED-cs-{uuid.uuid4().hex[:12]}",
        stripe_payment_intent_id=f"SIMULATED-pi-{uuid.uuid4().hex[:12]}",
        charges_snapshot=charges,
        idempotency_key=f"policy-initial-{policy.id}",
        effective_at=now,
    )
    handle_payment_success(payment_id=payment.id, stripe_payment_intent_id=payment.stripe_payment_intent_id)
    policy.refresh_from_db()
    return policy


@pytest.mark.django_db
class TestReconciliationRun:
    def test_clean_run_no_breaks(self, active_policy):
        """Reconciliation with consistent SIMULATED data produces no breaks."""
        recon = run_reconciliation()
        assert recon.status == ReconciliationRun.Status.COMPLETED
        assert recon.breaks.count() == 0

    def test_missing_provider_row_detected(self, active_policy):
        """A local payment with a non-SIMULATED PI ID missing from provider is flagged."""
        payment = Payment.objects.filter(policy=active_policy).first()
        payment.stripe_payment_intent_id = "pi_real_missing_123"
        payment.save(update_fields=["stripe_payment_intent_id"])

        with patch("apps.reconciliation.services._get_provider_payments", return_value={}):
            with patch("apps.reconciliation.services._get_provider_refunds", return_value={}):
                recon = run_reconciliation()

        breaks = recon.breaks.all()
        assert breaks.count() >= 1
        missing = breaks.filter(break_type=ReconciliationBreak.BreakType.MISSING_IN_PROVIDER)
        assert missing.exists()

    def test_missing_local_row_detected(self, _chart_of_accounts):
        """A provider payment not present locally is flagged."""
        provider_payments = {"pi_unknown_xyz": {"id": "pi_unknown_xyz", "amount": 50000, "status": "succeeded"}}

        with patch("apps.reconciliation.services._get_provider_payments", return_value=provider_payments):
            with patch("apps.reconciliation.services._get_provider_refunds", return_value={}):
                recon = run_reconciliation()

        breaks = recon.breaks.all()
        assert breaks.filter(break_type=ReconciliationBreak.BreakType.MISSING_IN_LEDGER).exists()

    def test_amount_mismatch_detected(self, active_policy):
        """Amount difference between local and provider is flagged."""
        payment = Payment.objects.filter(policy=active_policy).first()
        pi_id = "pi_real_amount_test"
        payment.stripe_payment_intent_id = pi_id
        payment.save(update_fields=["stripe_payment_intent_id"])

        provider_payments = {pi_id: {"id": pi_id, "amount": payment.amount_cents + 100, "status": "succeeded"}}

        with patch("apps.reconciliation.services._get_provider_payments", return_value=provider_payments):
            with patch("apps.reconciliation.services._get_provider_refunds", return_value={}):
                recon = run_reconciliation()

        mismatch = recon.breaks.filter(break_type=ReconciliationBreak.BreakType.AMOUNT_MISMATCH)
        assert mismatch.exists()
        brk = mismatch.first()
        assert brk.expected_amount_cents == payment.amount_cents
        assert brk.actual_amount_cents == payment.amount_cents + 100

    def test_duplicate_webhook_harmless(self, active_policy, staff_user):
        """Replaying a payment success twice still results in one effect."""
        payment = Payment.objects.filter(policy=active_policy, status=Payment.Status.SUCCEEDED).first()
        handle_payment_success(payment_id=payment.id, stripe_payment_intent_id=payment.stripe_payment_intent_id)

        recon = run_reconciliation()
        assert recon.status == ReconciliationRun.Status.COMPLETED
        assert recon.breaks.count() == 0

    def test_out_of_order_webhook_tolerated(self, active_policy, staff_user):
        """Cancellation refund processed out of order still reconciles cleanly."""
        result = cancel_policy(
            policy_id=active_policy.id,
            cancelled_by=staff_user,
            cancellation_date=date(2025, 7, 1),
        )
        handle_refund_success(refund_id=result["refund"].id)

        recon = run_reconciliation()
        assert recon.status == ReconciliationRun.Status.COMPLETED

    def test_provider_outage_leaves_consistent_state(self, _chart_of_accounts):
        """Provider outage (exception from provider fetch) marks run as FAILED."""
        with patch(
            "apps.reconciliation.services._get_provider_payments",
            side_effect=Exception("Stripe API unavailable"),
        ):
            with pytest.raises(Exception, match="Stripe API unavailable"):
                run_reconciliation()

        run = ReconciliationRun.objects.order_by("-started_at").first()
        assert run.status == ReconciliationRun.Status.FAILED
        assert "error" in run.summary


@pytest.mark.django_db
class TestBreakResolution:
    def test_resolve_break(self, active_policy, staff_user):
        """Resolving a break marks it resolved with notes."""
        payment = Payment.objects.filter(policy=active_policy).first()
        payment.stripe_payment_intent_id = "pi_test_resolve"
        payment.save(update_fields=["stripe_payment_intent_id"])

        with patch("apps.reconciliation.services._get_provider_payments", return_value={}):
            with patch("apps.reconciliation.services._get_provider_refunds", return_value={}):
                recon = run_reconciliation()

        brk = recon.breaks.first()
        assert brk is not None

        resolved = resolve_break(break_id=brk.id, resolved_by=staff_user, notes="Manual verification")
        assert resolved.resolved is True
        assert resolved.status == ReconciliationBreak.Status.RESOLVED
        assert resolved.resolution_notes == "Manual verification"
        assert resolved.resolved_by == staff_user


@pytest.mark.django_db
class TestMCPSafety:
    def test_agent_cannot_approve_own_action(self, _chart_of_accounts, staff_user):
        """MCP create_action_request creates a PENDING approval, not an auto-approved one."""
        from apps.claims.models import Claim, ClaimPayment
        from apps.mcp.server import create_action_request
        from apps.policies.models import Policy

        policy = Policy.objects.create(
            policy_number="POL-TEST",
            customer=staff_user,
            broker=Broker.objects.create(
                user=User.objects.create_user(username="b2", password="p"),
                company_name="B2",
                status=Broker.Status.APPROVED,
                commission_rate_bps=1000,
            ),
            status=Policy.Status.ACTIVE,
            effective_date=date(2025, 1, 1),
            expiration_date=date(2026, 1, 1),
            premium_amount_cents=100_000,
            coverage_territory="TX",
        )
        claim = Claim.objects.create(
            policy=policy,
            claim_number="CLM-TEST01",
            status="OPEN",
            date_of_loss=date(2025, 6, 1),
            description="Test",
            created_by=staff_user,
        )
        cp = ClaimPayment.objects.create(
            claim=claim,
            amount_cents=1000,
            status="APPROVED",
            payee="Test",
            effective_at=timezone.now(),
            created_by=staff_user,
        )

        result = create_action_request(
            action_type="CLAIM_PAYMENT",
            target_type="claim_payment",
            target_id=cp.id,
            requested_by_username=staff_user.username,
            description="Agent requests payout",
        )

        assert result["status"] == "PENDING"
        assert "approval queue" in result["message"]

        from apps.approvals.models import Approval

        approval = Approval.objects.get(id=result["approval_id"])
        assert approval.status == Approval.Status.PENDING
        assert approval.requested_by == staff_user
        assert "[MCP Agent]" in approval.reason

    def test_agent_cannot_write_directly_to_ledger(self):
        """MCP tools do not expose any ledger mutation functions."""
        from apps.mcp.server import mcp as mcp_server

        tool_names = [t.name for t in mcp_server._tool_manager.list_tools()]
        assert "post_journal_entry" not in tool_names
        assert "reverse_journal_entry" not in tool_names
        assert "delete" not in " ".join(tool_names).lower()
