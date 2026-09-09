"""
Stripe premium collection tests.

Tests cover:
- Successful payment posts ledger entries exactly once
- Duplicate webhook/payment processing is idempotent
- Failed payment does not activate policy
- Charge total = premium + tax + fee
- Ledger entries balance exactly
- Commission uses integer cents and deterministic rounding
- Policy state transitions (DRAFT -> PENDING_PAYMENT -> ACTIVE)
"""

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.brokers.models import Broker, KYBVerification
from apps.ledger.models import JournalEntry, JournalLine
from apps.ledger.services import get_account_balance
from apps.payments.models import Payment
from apps.payments.services import (
    PaymentError,
    create_checkout_for_policy,
    handle_payment_failure,
    handle_payment_success,
    simulate_payment_success,
)
from apps.policies.models import FeeRule, Policy, PolicyEvent, TaxRule
from apps.policies.services import calculate_rate_amount, issue_policy


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="staff", password="testpass", role=User.Role.STAFF, is_staff=True)


@pytest.fixture
def customer_user(db):
    return User.objects.create_user(
        username="customer", password="testpass", role=User.Role.CUSTOMER, email="cust@example.com"
    )


@pytest.fixture
def approved_broker(db):
    user = User.objects.create_user(username="broker_user", password="pass", role=User.Role.STAFF)
    broker = Broker.objects.create(
        user=user,
        company_name="Test Agency",
        commission_rate_bps=1500,
        status=Broker.Status.APPROVED,
    )
    KYBVerification.objects.create(broker=broker, persona_inquiry_id="inq-ok", status=KYBVerification.Status.COMPLETED)
    return broker


@pytest.fixture
def tx_rules(db):
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
def ledger_accounts(db):
    from apps.ledger.models import LedgerAccount

    accounts = [
        ("1010", "Stripe Clearing", "ASSET", "DEBIT"),
        ("2000", "Unearned Premium", "LIABILITY", "CREDIT"),
        ("2100", "State Premium Tax Payable", "LIABILITY", "CREDIT"),
        ("2150", "Stamping Fee Payable", "LIABILITY", "CREDIT"),
        ("2200", "Broker Commission Payable", "LIABILITY", "CREDIT"),
        ("5100", "Commission Expense", "EXPENSE", "DEBIT"),
    ]
    for code, name, acct_type, normal in accounts:
        LedgerAccount.objects.get_or_create(
            code=code,
            defaults={"name": name, "account_type": acct_type, "normal_balance": normal},
        )


@pytest.fixture
def draft_policy(staff_user, customer_user, approved_broker, tx_rules, ledger_accounts):
    tomorrow = date.today() + timedelta(days=1)
    policy, charges = issue_policy(
        customer=customer_user,
        broker_id=approved_broker.id,
        effective_date=tomorrow,
        premium_amount_cents=100000,
        coverage_territory="TX",
        created_by=staff_user,
    )
    return policy


class TestPaymentCheckout:
    def test_create_checkout_transitions_to_pending_payment(self, draft_policy, staff_user):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        draft_policy.refresh_from_db()
        assert draft_policy.status == Policy.Status.PENDING_PAYMENT
        assert result["simulated"] is True
        assert result["session_id"].startswith("SIMULATED")

    def test_creates_payment_record(self, draft_policy, staff_user):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        payment = Payment.objects.get(id=result["payment_id"])
        assert payment.status == Payment.Status.PENDING
        assert payment.amount_cents == 104890
        assert payment.charges_snapshot is not None
        assert payment.charges_snapshot["premium_cents"] == 100000

    def test_records_payment_requested_event(self, draft_policy, staff_user):
        create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        event = PolicyEvent.objects.filter(
            policy=draft_policy, event_type=PolicyEvent.EventType.PAYMENT_REQUESTED
        ).first()
        assert event is not None
        assert event.data["simulated"] is True

    def test_active_policy_not_payable(self, draft_policy, staff_user):
        draft_policy.status = Policy.Status.ACTIVE
        draft_policy.save()

        with pytest.raises(PaymentError, match="not in a payable state"):
            create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

    def test_past_effective_date_not_payable(self, draft_policy, staff_user):
        draft_policy.effective_date = date.today() - timedelta(days=1)
        draft_policy.save()

        with pytest.raises(PaymentError, match="effective date.*has passed"):
            create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)


class TestPaymentSuccess:
    def test_successful_payment_activates_policy(self, draft_policy, staff_user):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        handle_payment_success(payment_id=result["payment_id"], stripe_payment_intent_id="pi-test-123")

        draft_policy.refresh_from_db()
        assert draft_policy.status == Policy.Status.ACTIVE

    def test_posts_balanced_ledger_entry(self, draft_policy, staff_user):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        handle_payment_success(payment_id=result["payment_id"])

        premium_entry = JournalEntry.objects.filter(
            idempotency_key=f"premium-collection-{result['payment_id']}"
        ).first()
        assert premium_entry is not None
        assert premium_entry.status == JournalEntry.Status.POSTED

        lines = premium_entry.lines.all()
        total_debits = sum(ln.amount_cents for ln in lines if ln.entry_type == JournalLine.EntryType.DEBIT)
        total_credits = sum(ln.amount_cents for ln in lines if ln.entry_type == JournalLine.EntryType.CREDIT)
        assert total_debits == total_credits

    def test_charge_total_equals_premium_plus_tax_plus_fee(self, draft_policy, staff_user):
        """$1,000 premium + $48.50 tax + $0.40 fee = $1,048.90"""
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        handle_payment_success(payment_id=result["payment_id"])

        premium_entry = JournalEntry.objects.get(idempotency_key=f"premium-collection-{result['payment_id']}")
        debit_line = premium_entry.lines.filter(entry_type=JournalLine.EntryType.DEBIT).first()
        assert debit_line.amount_cents == 104890

        credit_lines = premium_entry.lines.filter(entry_type=JournalLine.EntryType.CREDIT)
        amounts = {ln.account.code: ln.amount_cents for ln in credit_lines}
        assert amounts["2000"] == 100000
        assert amounts["2100"] == 4850
        assert amounts["2150"] == 40

    def test_commission_posted_on_collected_premium(self, draft_policy, staff_user, approved_broker):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        handle_payment_success(payment_id=result["payment_id"])

        commission_entry = JournalEntry.objects.get(idempotency_key=f"commission-{result['payment_id']}")
        expected_commission = calculate_rate_amount(100000, approved_broker.commission_rate_bps)
        assert expected_commission == 15000

        debit = commission_entry.lines.get(entry_type=JournalLine.EntryType.DEBIT)
        credit = commission_entry.lines.get(entry_type=JournalLine.EntryType.CREDIT)
        assert debit.account.code == "5100"
        assert debit.amount_cents == 15000
        assert credit.account.code == "2200"
        assert credit.amount_cents == 15000

    def test_creates_activated_event(self, draft_policy, staff_user):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        handle_payment_success(payment_id=result["payment_id"], stripe_payment_intent_id="pi-test-456")

        event = PolicyEvent.objects.filter(policy=draft_policy, event_type=PolicyEvent.EventType.ACTIVATED).first()
        assert event is not None
        assert event.data["commission_cents"] == 15000
        assert event.data["stripe_payment_intent_id"] == "pi-test-456"


class TestIdempotency:
    def test_duplicate_payment_success_posts_ledger_once(self, draft_policy, staff_user):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)
        payment_id = result["payment_id"]

        handle_payment_success(payment_id=payment_id, stripe_payment_intent_id="pi-1")
        handle_payment_success(payment_id=payment_id, stripe_payment_intent_id="pi-1")

        premium_entries = JournalEntry.objects.filter(idempotency_key=f"premium-collection-{payment_id}")
        assert premium_entries.count() == 1

        commission_entries = JournalEntry.objects.filter(idempotency_key=f"commission-{payment_id}")
        assert commission_entries.count() == 1


class TestPaymentFailure:
    def test_failed_payment_does_not_activate_policy(self, draft_policy, staff_user):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        handle_payment_failure(payment_id=result["payment_id"], reason="Card declined")

        draft_policy.refresh_from_db()
        assert draft_policy.status == Policy.Status.PENDING_PAYMENT

        payment = Payment.objects.get(id=result["payment_id"])
        assert payment.status == Payment.Status.FAILED

    def test_no_ledger_entries_on_failure(self, draft_policy, staff_user):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        handle_payment_failure(payment_id=result["payment_id"])

        assert not JournalEntry.objects.filter(idempotency_key=f"premium-collection-{result['payment_id']}").exists()


class TestSimulatedPayment:
    def test_simulate_completes_payment(self, draft_policy, staff_user):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        payment = simulate_payment_success(payment_id=result["payment_id"])

        assert payment.status == Payment.Status.SUCCEEDED
        assert payment.stripe_payment_intent_id.startswith("SIMULATED")

        draft_policy.refresh_from_db()
        assert draft_policy.status == Policy.Status.ACTIVE


class TestLedgerBalances:
    def test_balances_correct_after_payment(self, draft_policy, staff_user):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        handle_payment_success(payment_id=result["payment_id"])

        assert get_account_balance("1010") == 104890
        assert get_account_balance("2000") == 100000
        assert get_account_balance("2100") == 4850
        assert get_account_balance("2150") == 40
        assert get_account_balance("2200") == 15000
        assert get_account_balance("5100") == 15000


class TestCommissionRounding:
    def test_commission_uses_integer_cents_deterministic(self, db, customer_user, tx_rules, ledger_accounts):
        user = User.objects.create_user(username="broker2", password="pass", role=User.Role.STAFF)
        broker = Broker.objects.create(
            user=user,
            company_name="Odd Rate Agency",
            commission_rate_bps=1333,
            status=Broker.Status.APPROVED,
        )
        KYBVerification.objects.create(
            broker=broker, persona_inquiry_id="inq-2", status=KYBVerification.Status.COMPLETED
        )

        staff = User.objects.create_user(username="staff2", password="pass", role=User.Role.STAFF, is_staff=True)
        policy, _ = issue_policy(
            customer=customer_user,
            broker_id=broker.id,
            effective_date=date.today() + timedelta(days=1),
            premium_amount_cents=77777,
            coverage_territory="TX",
            created_by=staff,
        )

        result = create_checkout_for_policy(policy_id=policy.id, requested_by=staff)
        handle_payment_success(payment_id=result["payment_id"])

        expected = calculate_rate_amount(77777, 1333)
        assert expected == 10368

        commission_entry = JournalEntry.objects.get(idempotency_key=f"commission-{result['payment_id']}")
        assert commission_entry.lines.get(entry_type=JournalLine.EntryType.DEBIT).amount_cents == 10368


class TestStripeWebhookAPI:
    def test_stripe_webhook_missing_signature_rejected_when_secret_configured(self, api, settings):
        settings.STRIPE_WEBHOOK_SECRET = "whsec_test_secret"
        response = api.post(
            "/api/integrations/webhooks/stripe/",
            data='{"id": "evt_test", "type": "checkout.session.completed"}',
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_stripe_webhook_invalid_json_rejected(self, api):
        response = api.post(
            "/api/integrations/webhooks/stripe/",
            data="not json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_stripe_webhook_checkout_completed(self, api, draft_policy, staff_user, ledger_accounts):
        """Full webhook flow in dev mode (no secret configured)."""
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)
        session_id = result["session_id"]

        webhook_payload = {
            "id": "evt_test_checkout_001",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "payment_intent": "pi_test_from_webhook",
                },
            },
        }

        response = api.post(
            "/api/integrations/webhooks/stripe/",
            data=webhook_payload,
            format="json",
        )
        assert response.status_code == 200

        draft_policy.refresh_from_db()
        assert draft_policy.status == Policy.Status.ACTIVE

        payment = Payment.objects.get(id=result["payment_id"])
        assert payment.status == Payment.Status.SUCCEEDED
        assert payment.stripe_payment_intent_id == "pi_test_from_webhook"

    def test_stripe_webhook_duplicate_is_idempotent(self, api, draft_policy, staff_user, ledger_accounts):
        result = create_checkout_for_policy(policy_id=draft_policy.id, requested_by=staff_user)

        webhook_payload = {
            "id": "evt_test_dup_001",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": result["session_id"],
                    "payment_intent": "pi_dup_test",
                },
            },
        }

        resp1 = api.post("/api/integrations/webhooks/stripe/", data=webhook_payload, format="json")
        resp2 = api.post("/api/integrations/webhooks/stripe/", data=webhook_payload, format="json")

        assert resp1.status_code == 200
        assert resp2.status_code == 200

        from apps.integrations.models import WebhookEvent

        events = WebhookEvent.objects.filter(event_id="evt_test_dup_001")
        assert events.count() == 1


class TestPaymentAPI:
    def test_create_checkout_via_api(self, api, draft_policy, customer_user):
        api.force_authenticate(user=customer_user)
        resp = api.post("/api/payments/checkout/", {"policy_id": draft_policy.id})
        assert resp.status_code == 201
        assert resp.data["simulated"] is True
        assert "payment_id" in resp.data

    def test_list_payments_for_policy(self, api, draft_policy, staff_user, customer_user):
        api.force_authenticate(user=staff_user)
        api.post("/api/payments/checkout/", {"policy_id": draft_policy.id})

        api.force_authenticate(user=customer_user)
        resp = api.get(f"/api/payments/policy/{draft_policy.id}/")
        assert resp.status_code == 200
        assert len(resp.data) == 1

    def test_simulate_via_api(self, api, draft_policy, staff_user):
        api.force_authenticate(user=staff_user)
        checkout_resp = api.post("/api/payments/checkout/", {"policy_id": draft_policy.id})
        payment_id = checkout_resp.data["payment_id"]

        resp = api.post(f"/api/payments/{payment_id}/simulate/")
        assert resp.status_code == 200
        assert resp.data["status"] == "SUCCEEDED"

    def test_customer_cannot_see_other_policy_payments(self, api, draft_policy):
        other = User.objects.create_user(
            username="other", password="pass", role=User.Role.CUSTOMER, email="other@example.com"
        )
        api.force_authenticate(user=other)
        resp = api.get(f"/api/payments/policy/{draft_policy.id}/")
        assert resp.status_code == 404
