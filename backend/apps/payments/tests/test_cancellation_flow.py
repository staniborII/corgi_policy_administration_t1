import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.brokers.models import Broker
from apps.ledger.models import JournalEntry, JournalLine, LedgerAccount
from apps.ledger.services import get_account_balance
from apps.payments.models import Payment, Refund
from apps.payments.services import handle_payment_success, handle_refund_success
from apps.policies.models import FeeRule, Policy, PolicyEvent, TaxRule
from apps.policies.services import (
    cancel_policy,
    compute_cancellation_refund,
    issue_policy,
    prorate_amount,
)
from apps.reconciliation.services import generate_broker_statement


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
    """Create a policy, pay it, and return it ACTIVE with ledger entries."""
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
class TestProRataCancellation:
    def test_mid_term_unearned_premium(self, active_policy, staff_user):
        """Cancel at 6 months: unearned = 50% of premium."""
        cancellation_date = date(2025, 7, 1)
        result = compute_cancellation_refund(policy=active_policy, cancellation_date=cancellation_date)

        total_days = (active_policy.expiration_date - active_policy.effective_date).days
        remaining = (active_policy.expiration_date - cancellation_date).days
        expected = prorate_amount(100_000, remaining, total_days)

        assert result["unearned_premium_cents"] == expected
        assert result["remaining_days"] == remaining
        assert result["total_days"] == total_days

    def test_refundable_tax_on_unearned(self, active_policy, staff_user):
        """Refundable tax is calculated on the unearned premium, not the original."""
        cancellation_date = date(2025, 7, 1)
        result = compute_cancellation_refund(policy=active_policy, cancellation_date=cancellation_date)

        unearned = result["unearned_premium_cents"]
        expected_tax = int(Decimal(unearned) * Decimal(485) / Decimal(10000) + Decimal("0.5"))
        expected_fee = int(Decimal(unearned) * Decimal(4) / Decimal(10000) + Decimal("0.5"))

        assert result["total_refundable_tax_cents"] == expected_tax
        assert result["total_refundable_fees_cents"] == expected_fee
        assert result["total_refund_cents"] == unearned + expected_tax + expected_fee

    def test_commission_clawback_matches_unearned(self, active_policy, staff_user):
        """Commission clawback = commission_rate * unearned_premium."""
        cancellation_date = date(2025, 7, 1)
        result = compute_cancellation_refund(policy=active_policy, cancellation_date=cancellation_date)

        unearned = result["unearned_premium_cents"]
        expected_clawback = int(Decimal(unearned) * Decimal(1500) / Decimal(10000) + Decimal("0.5"))

        assert result["commission_clawback_cents"] == expected_clawback

    def test_cancel_on_last_day_zero_refund(self, active_policy, staff_user):
        """Cancelling on the last day = zero remaining = zero refund."""
        cancellation_date = active_policy.expiration_date
        result = compute_cancellation_refund(policy=active_policy, cancellation_date=cancellation_date)
        assert result["unearned_premium_cents"] == 0
        assert result["total_refund_cents"] == 0

    def test_cancel_before_effective_raises(self, active_policy, staff_user):
        """Cancellation before the effective date is an error."""
        with pytest.raises(Exception, match="before policy effective date"):
            compute_cancellation_refund(policy=active_policy, cancellation_date=date(2024, 12, 1))


@pytest.mark.django_db
class TestLeapYearCancellation:
    def test_leap_year_term_days(self, _chart_of_accounts, _tx_rules, customer, broker, staff_user):
        """Policy starting 2024-01-01 expires 2025-01-01 = 366 days (2024 is leap year)."""
        policy, charges = issue_policy(
            customer=customer,
            broker_id=broker.id,
            effective_date=date(2024, 1, 1),
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

        result = compute_cancellation_refund(policy=policy, cancellation_date=date(2024, 7, 1))
        assert result["total_days"] == 366
        expected_remaining = (date(2025, 1, 1) - date(2024, 7, 1)).days
        assert result["remaining_days"] == expected_remaining


@pytest.mark.django_db
class TestCancelPolicyFlow:
    def test_cancel_creates_pending_refund(self, active_policy, staff_user):
        """Cancelling creates a PENDING refund (not SUCCEEDED) — ledger waits for provider."""
        result = cancel_policy(policy_id=active_policy.id, cancelled_by=staff_user, cancellation_date=date(2025, 7, 1))

        assert result["policy"].status == Policy.Status.CANCELLED
        refund = result["refund"]
        assert refund is not None
        assert refund.status == Refund.Status.PENDING
        assert refund.stripe_refund_id.startswith("SIMULATED")
        assert refund.amount_cents == result["total_refund_cents"]

    def test_cancel_records_event(self, active_policy, staff_user):
        cancel_policy(policy_id=active_policy.id, cancelled_by=staff_user, cancellation_date=date(2025, 7, 1))
        event = PolicyEvent.objects.filter(policy=active_policy, event_type=PolicyEvent.EventType.CANCELLED).first()
        assert event is not None
        assert event.data["unearned_premium_cents"] > 0

    def test_cancel_non_active_raises(self, _chart_of_accounts, _tx_rules, customer, broker, staff_user):
        """Cannot cancel a DRAFT policy."""
        policy, _ = issue_policy(
            customer=customer,
            broker_id=broker.id,
            effective_date=date(2025, 1, 1),
            premium_amount_cents=100_000,
            coverage_territory="TX",
            created_by=staff_user,
        )
        with pytest.raises(Exception, match="Can only cancel an active policy"):
            cancel_policy(policy_id=policy.id, cancelled_by=staff_user)

    def test_open_claim_remains_after_cancellation(self, active_policy, staff_user):
        """Claims with incidents during active coverage survive cancellation."""
        from apps.claims.services import submit_claim

        claim = submit_claim(
            policy_id=active_policy.id,
            date_of_loss=date(2025, 3, 15),
            description="Test claim",
            user=staff_user,
        )

        cancel_policy(policy_id=active_policy.id, cancelled_by=staff_user, cancellation_date=date(2025, 7, 1))

        claim.refresh_from_db()
        assert claim.status == "OPEN"


@pytest.mark.django_db
class TestRefundLedger:
    def test_refund_posts_ledger_on_success(self, active_policy, staff_user):
        """Ledger entries only appear after refund confirmation, not at cancellation."""
        result = cancel_policy(policy_id=active_policy.id, cancelled_by=staff_user, cancellation_date=date(2025, 7, 1))
        refund = result["refund"]

        refund_entries_before = JournalEntry.objects.filter(idempotency_key=f"cancellation-refund-{refund.id}").count()
        assert refund_entries_before == 0

        handle_refund_success(refund_id=refund.id)

        refund_entries_after = JournalEntry.objects.filter(idempotency_key=f"cancellation-refund-{refund.id}").count()
        assert refund_entries_after == 1

    def test_refund_balanced_entry(self, active_policy, staff_user):
        """Refund journal entry must be balanced."""
        result = cancel_policy(policy_id=active_policy.id, cancelled_by=staff_user, cancellation_date=date(2025, 7, 1))
        handle_refund_success(refund_id=result["refund"].id)

        entry = JournalEntry.objects.get(idempotency_key=f"cancellation-refund-{result['refund'].id}")
        debits = sum(line.amount_cents for line in entry.lines.filter(entry_type=JournalLine.EntryType.DEBIT))
        credits = sum(line.amount_cents for line in entry.lines.filter(entry_type=JournalLine.EntryType.CREDIT))
        assert debits == credits

    def test_commission_clawback_posted(self, active_policy, staff_user):
        """Commission clawback posts as DR 2200 / CR 4200."""
        result = cancel_policy(policy_id=active_policy.id, cancelled_by=staff_user, cancellation_date=date(2025, 7, 1))
        handle_refund_success(refund_id=result["refund"].id)

        clawback_entry = JournalEntry.objects.get(idempotency_key=f"commission-clawback-{result['refund'].id}")
        dr_lines = clawback_entry.lines.filter(entry_type=JournalLine.EntryType.DEBIT)
        cr_lines = clawback_entry.lines.filter(entry_type=JournalLine.EntryType.CREDIT)
        assert dr_lines.first().account.code == "2200"
        assert cr_lines.first().account.code == "4200"

    def test_refund_idempotent(self, active_policy, staff_user):
        """Duplicate refund success = one financial effect."""
        result = cancel_policy(policy_id=active_policy.id, cancelled_by=staff_user, cancellation_date=date(2025, 7, 1))

        handle_refund_success(refund_id=result["refund"].id)
        handle_refund_success(refund_id=result["refund"].id)

        entries = JournalEntry.objects.filter(idempotency_key=f"cancellation-refund-{result['refund'].id}").count()
        assert entries == 1

    def test_refund_posts_once(self, active_policy, staff_user):
        """A second call to handle_refund_success doesn't duplicate."""
        result = cancel_policy(policy_id=active_policy.id, cancelled_by=staff_user, cancellation_date=date(2025, 7, 1))
        refund = result["refund"]

        refund1 = handle_refund_success(refund_id=refund.id)
        refund2 = handle_refund_success(refund_id=refund.id)

        assert refund1.status == Refund.Status.SUCCEEDED
        assert refund2.status == Refund.Status.SUCCEEDED
        assert JournalEntry.objects.filter(memo__contains="Cancellation refund").count() == 1


@pytest.mark.django_db
class TestBrokerStatement:
    def _statement_period(self):
        """Return a period covering today (when test payments are recorded)."""
        today = date.today()
        return today.replace(day=1), today.replace(day=28)

    def test_statement_ties_to_ledger(self, active_policy, staff_user, broker):
        """Statement premium and commission match ledger account totals."""
        start, end = self._statement_period()
        statement = generate_broker_statement(broker=broker, period_start=start, period_end=end)

        commission_payable = get_account_balance("2200")
        assert statement.total_commission_cents == commission_payable

    def test_statement_with_clawback(self, active_policy, staff_user, broker):
        """Statement reflects commission clawback after cancellation."""
        result = cancel_policy(policy_id=active_policy.id, cancelled_by=staff_user, cancellation_date=date(2025, 7, 1))
        handle_refund_success(refund_id=result["refund"].id)

        start, end = self._statement_period()
        statement = generate_broker_statement(broker=broker, period_start=start, period_end=end)

        assert statement.total_clawback_cents == result["commission_clawback_cents"]
        assert statement.net_due_cents == statement.total_commission_cents - statement.total_clawback_cents

    def test_statement_rerun_identical(self, active_policy, staff_user, broker):
        """Re-running for the same period returns the identical statement."""
        start, end = self._statement_period()
        s1 = generate_broker_statement(broker=broker, period_start=start, period_end=end)
        s2 = generate_broker_statement(broker=broker, period_start=start, period_end=end)
        assert s1.id == s2.id
        assert s1.total_premium_cents == s2.total_premium_cents

    def test_statement_data_contains_details(self, active_policy, staff_user, broker):
        """Statement data JSON includes payment details."""
        start, end = self._statement_period()
        statement = generate_broker_statement(broker=broker, period_start=start, period_end=end)
        assert len(statement.statement_data["payments"]) >= 1
        assert "policy_number" in statement.statement_data["payments"][0]
