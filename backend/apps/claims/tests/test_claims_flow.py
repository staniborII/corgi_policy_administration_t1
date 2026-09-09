"""
Claims, reserves, maker-checker, payout tests.

Tests cover:
- Reserve adjustments append rather than mutate
- Incurred = paid + reserve
- Payment over limit rejected
- Maker cannot approve own payment
- Second staff user can approve
- Duplicate payout event does not double payment
- Returned payout produces correct compensating financial events
- Valid pre-cancellation claim remains open after cancellation
- Unverified claimant payout destination blocks payout execution
- Bank-verification simulator states are clearly labelled SIMULATED
"""

from datetime import date

import pytest

from apps.accounts.models import User
from apps.brokers.models import Broker, KYBVerification
from apps.claims.models import Claim, ClaimPayment, ReserveEvent
from apps.claims.services import (
    APPROVAL_THRESHOLD_CENTS,
    ClaimError,
    approve_claim_payment,
    create_claim_payment,
    execute_payout,
    get_claim_financials,
    get_paid_total,
    get_reserve_balance,
    handle_payout_returned,
    handle_payout_settled,
    set_payout_destination,
    set_reserve,
    submit_claim,
    verify_payout_destination,
)
from apps.ledger.models import JournalEntry, JournalLine, LedgerAccount
from apps.ledger.services import get_account_balance
from apps.payments.services import create_checkout_for_policy, handle_payment_success
from apps.policies.models import FeeRule, Policy, TaxRule
from apps.policies.services import issue_policy


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="staff1", password="testpass", role=User.Role.STAFF, is_staff=True)


@pytest.fixture
def staff_user2(db):
    return User.objects.create_user(username="staff2", password="testpass", role=User.Role.STAFF, is_staff=True)


@pytest.fixture
def customer_user(db):
    return User.objects.create_user(username="customer", password="testpass", role=User.Role.CUSTOMER)


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
    accounts = [
        ("1000", "Cash", "ASSET", "DEBIT"),
        ("1010", "Stripe Clearing", "ASSET", "DEBIT"),
        ("2000", "Unearned Premium", "LIABILITY", "CREDIT"),
        ("2100", "State Premium Tax Payable", "LIABILITY", "CREDIT"),
        ("2150", "Stamping Fee Payable", "LIABILITY", "CREDIT"),
        ("2200", "Broker Commission Payable", "LIABILITY", "CREDIT"),
        ("2300", "Claim Reserve", "LIABILITY", "CREDIT"),
        ("5000", "Claims Expense", "EXPENSE", "DEBIT"),
        ("5100", "Commission Expense", "EXPENSE", "DEBIT"),
    ]
    for code, name, acct_type, normal in accounts:
        LedgerAccount.objects.get_or_create(
            code=code,
            defaults={"name": name, "account_type": acct_type, "normal_balance": normal},
        )


@pytest.fixture
def active_policy(staff_user, customer_user, approved_broker, tx_rules, ledger_accounts):
    policy, _ = issue_policy(
        customer=customer_user,
        broker_id=approved_broker.id,
        effective_date=date(2025, 6, 1),
        premium_amount_cents=100000,
        coverage_territory="TX",
        created_by=staff_user,
    )
    result = create_checkout_for_policy(policy_id=policy.id, requested_by=staff_user)
    handle_payment_success(payment_id=result["payment_id"])
    policy.refresh_from_db()
    return policy


@pytest.fixture
def open_claim(active_policy, customer_user):
    return submit_claim(
        policy_id=active_policy.id,
        date_of_loss=date(2025, 9, 1),
        description="Water damage to warehouse",
        estimated_amount_cents=500000,
        user=customer_user,
    )


@pytest.fixture
def reserved_claim(open_claim, staff_user):
    set_reserve(
        claim_id=open_claim.id,
        amount_cents=800000,
        reserve_type=ReserveEvent.ReserveType.INITIAL,
        memo="Initial reserve estimate",
        user=staff_user,
    )
    open_claim.refresh_from_db()
    return open_claim


class TestClaimSubmission:
    def test_submit_claim_on_active_policy(self, active_policy, customer_user):
        claim = submit_claim(
            policy_id=active_policy.id,
            date_of_loss=date(2025, 9, 1),
            description="Slip and fall",
            user=customer_user,
        )
        assert claim.status == Claim.Status.OPEN
        assert claim.claim_number.startswith("CLM-")
        assert claim.policy == active_policy

    def test_reject_claim_outside_coverage_dates(self, active_policy, customer_user):
        with pytest.raises(ClaimError, match="within policy coverage dates"):
            submit_claim(
                policy_id=active_policy.id,
                date_of_loss=date(2024, 1, 1),
                description="Before coverage",
                user=customer_user,
            )

    def test_pre_cancellation_claim_remains_valid(self, active_policy, customer_user, staff_user):
        claim = submit_claim(
            policy_id=active_policy.id,
            date_of_loss=date(2025, 9, 1),
            description="Incident during active period",
            user=customer_user,
        )

        active_policy.status = Policy.Status.CANCELLED
        active_policy.save()

        claim.refresh_from_db()
        assert claim.status == Claim.Status.OPEN

        claim2 = submit_claim(
            policy_id=active_policy.id,
            date_of_loss=date(2025, 8, 15),
            description="Another incident during active period",
            user=customer_user,
        )
        assert claim2.status == Claim.Status.OPEN


class TestReserves:
    def test_initial_reserve_sets_status(self, open_claim, staff_user):
        event = set_reserve(
            claim_id=open_claim.id,
            amount_cents=800000,
            reserve_type=ReserveEvent.ReserveType.INITIAL,
            memo="Initial reserve",
            user=staff_user,
        )
        open_claim.refresh_from_db()
        assert open_claim.status == Claim.Status.RESERVED
        assert event.amount_cents == 800000
        assert event.reserve_type == ReserveEvent.ReserveType.INITIAL

    def test_reserve_adjustments_append_not_mutate(self, reserved_claim, staff_user):
        initial_count = reserved_claim.reserve_events.count()

        set_reserve(
            claim_id=reserved_claim.id,
            amount_cents=200000,
            reserve_type=ReserveEvent.ReserveType.ADJUSTMENT,
            memo="More info received",
            user=staff_user,
        )

        assert reserved_claim.reserve_events.count() == initial_count + 1
        assert get_reserve_balance(reserved_claim.id) == 1000000

    def test_incurred_equals_paid_plus_reserve(self, reserved_claim, staff_user, staff_user2):
        set_payout_destination(claim_id=reserved_claim.id, payee_name="Warehouse Corp", account_last_four="9876")
        verify_payout_destination(claim_id=reserved_claim.id, outcome="VERIFIED")

        payment = create_claim_payment(
            claim_id=reserved_claim.id, amount_cents=400000, payee="Warehouse Corp", user=staff_user
        )
        if payment.status == ClaimPayment.Status.PENDING_APPROVAL:
            payment = approve_claim_payment(payment_id=payment.id, user=staff_user2)

        payment = execute_payout(payment_id=payment.id, user=staff_user)
        handle_payout_settled(payout_reference=payment.payout_reference, amount_cents=400000)

        financials = get_claim_financials(reserved_claim.id)
        assert financials["incurred_cents"] == financials["paid_cents"] + financials["reserve_cents"]
        assert financials["paid_cents"] == 400000
        assert financials["reserve_cents"] == 800000

    def test_reserve_creates_journal_entries(self, open_claim, staff_user, ledger_accounts):
        entries_before = JournalEntry.objects.count()

        set_reserve(
            claim_id=open_claim.id,
            amount_cents=500000,
            reserve_type=ReserveEvent.ReserveType.INITIAL,
            user=staff_user,
        )

        assert JournalEntry.objects.count() == entries_before + 1
        je = JournalEntry.objects.order_by("-id").first()
        lines = je.lines.all()
        assert lines.count() == 2
        debit_line = lines.get(entry_type=JournalLine.EntryType.DEBIT)
        credit_line = lines.get(entry_type=JournalLine.EntryType.CREDIT)
        assert debit_line.account.code == "5000"
        assert credit_line.account.code == "2300"

    def test_negative_reserve_adjustment_reverses_entries(self, reserved_claim, staff_user, ledger_accounts):
        set_reserve(
            claim_id=reserved_claim.id,
            amount_cents=-300000,
            reserve_type=ReserveEvent.ReserveType.RELEASE,
            memo="Partial release",
            user=staff_user,
        )

        assert get_reserve_balance(reserved_claim.id) == 500000

    def test_cannot_set_initial_reserve_twice(self, reserved_claim, staff_user):
        with pytest.raises(ClaimError, match="Initial reserve already exists"):
            set_reserve(
                claim_id=reserved_claim.id,
                amount_cents=100000,
                reserve_type=ReserveEvent.ReserveType.INITIAL,
                user=staff_user,
            )


class TestClaimPayments:
    def test_payment_over_limit_rejected(self, reserved_claim, staff_user):
        reserved_claim.policy.coverage_limit_cents = 500000
        reserved_claim.policy.save()

        with pytest.raises(ClaimError, match="exceed policy limit"):
            create_claim_payment(claim_id=reserved_claim.id, amount_cents=600000, payee="Claimant", user=staff_user)

    def test_small_payment_auto_approved(self, reserved_claim, staff_user):
        payment = create_claim_payment(
            claim_id=reserved_claim.id,
            amount_cents=APPROVAL_THRESHOLD_CENTS - 1,
            payee="Claimant",
            user=staff_user,
        )
        assert payment.status == ClaimPayment.Status.APPROVED

    def test_large_payment_needs_approval(self, reserved_claim, staff_user):
        payment = create_claim_payment(
            claim_id=reserved_claim.id,
            amount_cents=APPROVAL_THRESHOLD_CENTS,
            payee="Claimant",
            user=staff_user,
        )
        assert payment.status == ClaimPayment.Status.PENDING_APPROVAL


class TestMakerChecker:
    def test_maker_cannot_approve_own_payment(self, reserved_claim, staff_user):
        payment = create_claim_payment(
            claim_id=reserved_claim.id, amount_cents=APPROVAL_THRESHOLD_CENTS, payee="Claimant", user=staff_user
        )

        with pytest.raises(ClaimError, match="Maker cannot approve"):
            approve_claim_payment(payment_id=payment.id, user=staff_user)

    def test_second_staff_can_approve(self, reserved_claim, staff_user, staff_user2):
        payment = create_claim_payment(
            claim_id=reserved_claim.id, amount_cents=APPROVAL_THRESHOLD_CENTS, payee="Claimant", user=staff_user
        )

        approved = approve_claim_payment(payment_id=payment.id, user=staff_user2)
        assert approved.status == ClaimPayment.Status.APPROVED
        assert approved.approved_by == staff_user2


class TestPayoutFlow:
    @pytest.fixture
    def approved_payment(self, reserved_claim, staff_user, staff_user2):
        set_payout_destination(claim_id=reserved_claim.id, payee_name="Warehouse Corp", account_last_four="1234")
        verify_payout_destination(claim_id=reserved_claim.id, outcome="VERIFIED")

        payment = create_claim_payment(
            claim_id=reserved_claim.id, amount_cents=300000, payee="Warehouse Corp", user=staff_user
        )
        if payment.status == ClaimPayment.Status.PENDING_APPROVAL:
            payment = approve_claim_payment(payment_id=payment.id, user=staff_user2)
        return payment

    def test_execute_payout_sets_pending(self, approved_payment, staff_user):
        payment = execute_payout(payment_id=approved_payment.id, user=staff_user)
        assert payment.status == ClaimPayment.Status.PENDING
        assert payment.payout_reference.startswith("SIM-PAY-")

    def test_payout_settled_creates_ledger_entries(self, approved_payment, staff_user, ledger_accounts):
        payment = execute_payout(payment_id=approved_payment.id, user=staff_user)

        cash_before = get_account_balance("1000")
        reserve_before = get_account_balance("2300")

        handle_payout_settled(payout_reference=payment.payout_reference, amount_cents=300000)

        payment.refresh_from_db()
        assert payment.status == ClaimPayment.Status.SETTLED

        assert get_account_balance("1000") == cash_before - 300000
        assert get_account_balance("2300") == reserve_before - 300000

    def test_duplicate_payout_settled_is_idempotent(self, approved_payment, staff_user):
        payment = execute_payout(payment_id=approved_payment.id, user=staff_user)
        ref = payment.payout_reference

        handle_payout_settled(payout_reference=ref, amount_cents=300000)
        handle_payout_settled(payout_reference=ref, amount_cents=300000)

        assert get_paid_total(payment.claim_id) == 300000

    def test_returned_payout_compensating_entries(self, approved_payment, staff_user, ledger_accounts):
        payment = execute_payout(payment_id=approved_payment.id, user=staff_user)
        ref = payment.payout_reference

        handle_payout_settled(payout_reference=ref, amount_cents=300000)

        cash_after_settle = get_account_balance("1000")
        reserve_after_settle = get_account_balance("2300")

        handle_payout_returned(payout_reference=ref, reason="Account closed")

        payment.refresh_from_db()
        assert payment.status == ClaimPayment.Status.RETURNED

        assert get_account_balance("1000") == cash_after_settle + 300000
        assert get_account_balance("2300") == reserve_after_settle + 300000


class TestPayoutDestination:
    def test_unverified_destination_blocks_payout(self, reserved_claim, staff_user, staff_user2):
        set_payout_destination(claim_id=reserved_claim.id, payee_name="Claimant", account_last_four="5678")

        payment = create_claim_payment(
            claim_id=reserved_claim.id, amount_cents=100000, payee="Claimant", user=staff_user
        )
        if payment.status == ClaimPayment.Status.PENDING_APPROVAL:
            payment = approve_claim_payment(payment_id=payment.id, user=staff_user2)

        with pytest.raises(ClaimError, match="must be VERIFIED"):
            execute_payout(payment_id=payment.id, user=staff_user)

    def test_no_destination_blocks_payout(self, reserved_claim, staff_user, staff_user2):
        payment = create_claim_payment(
            claim_id=reserved_claim.id, amount_cents=100000, payee="Claimant", user=staff_user
        )
        if payment.status == ClaimPayment.Status.PENDING_APPROVAL:
            payment = approve_claim_payment(payment_id=payment.id, user=staff_user2)

        with pytest.raises(ClaimError, match="No payout destination"):
            execute_payout(payment_id=payment.id, user=staff_user)

    def test_bank_verification_labelled_simulated(self, reserved_claim):
        dest = set_payout_destination(claim_id=reserved_claim.id, payee_name="Claimant", account_last_four="4321")
        assert dest.provider == "SIMULATED"
        assert dest.provider_reference.startswith("SIM-BANK-")

    def test_failed_verification_blocks_payout(self, reserved_claim, staff_user, staff_user2):
        set_payout_destination(claim_id=reserved_claim.id, payee_name="Claimant", account_last_four="1111")
        verify_payout_destination(claim_id=reserved_claim.id, outcome="FAILED")

        payment = create_claim_payment(
            claim_id=reserved_claim.id, amount_cents=100000, payee="Claimant", user=staff_user
        )
        if payment.status == ClaimPayment.Status.PENDING_APPROVAL:
            payment = approve_claim_payment(payment_id=payment.id, user=staff_user2)

        with pytest.raises(ClaimError, match="must be VERIFIED"):
            execute_payout(payment_id=payment.id, user=staff_user)
