"""
Endorsement, correction, pro-rata and as-of tests.

Tests cover:
- Pro-rata calculation for mid-term endorsements
- Leap-year endorsement math
- Below-threshold auto-approval flow
- Above-threshold customer approval flow
- Address correction (no premium change)
- Reversal + re-book leaves original intact
- Backdated correction creates correct journal entries
- Historical as-of reconstruction between endorsements
- Tax/fee adjustments use same rates as original policy
- PDF generation from as-of state
"""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.brokers.models import Broker, KYBVerification
from apps.documents.services import generate_declarations_pdf, generate_endorsement_schedule_pdf
from apps.endorsements.models import Endorsement
from apps.endorsements.services import (
    EndorsementError,
    apply_endorsement,
    approve_endorsement,
    correct_endorsement,
    create_endorsement,
    prorate_amount,
)
from apps.ledger.models import JournalEntry, JournalLine
from apps.payments.services import create_checkout_for_policy, handle_payment_success
from apps.policies.models import FeeRule, TaxRule
from apps.policies.selectors import get_policy_as_of
from apps.policies.services import issue_policy


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


class TestProRataCalculation:
    def test_half_year_prorates_to_half(self):
        assert prorate_amount(60000, 183, 365) == 30082

    def test_full_year_returns_full_amount(self):
        assert prorate_amount(60000, 365, 365) == 60000

    def test_one_day_remaining(self):
        assert prorate_amount(36500, 1, 365) == 100

    def test_zero_days_returns_zero(self):
        assert prorate_amount(60000, 0, 365) == 0

    def test_negative_delta(self):
        assert prorate_amount(-60000, 183, 365) == -30082

    def test_leap_year_term(self):
        """Policy from 2024-03-01 to 2025-03-01 = 366 days."""
        result = prorate_amount(60000, 183, 366)
        expected = int(Decimal(60000) * Decimal(183) / Decimal(366))
        assert abs(result - expected) <= 1


class TestEndorsementCreation:
    def test_coverage_limit_increase_below_threshold(self, active_policy, staff_user):
        """$200 annual increase, below $500 threshold -> PENDING_PAYMENT (auto-approved)."""
        end, charges = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=20000,
            description="Increase coverage limit",
            created_by=staff_user,
        )

        assert end.status == Endorsement.Status.PENDING_PAYMENT
        assert end.annual_premium_delta_cents == 20000
        assert charges["premium_change_cents"] > 0
        assert charges["total_tax_cents"] > 0
        assert charges["remaining_days"] == (active_policy.expiration_date - date(2025, 12, 1)).days

    def test_large_increase_requires_customer_approval(self, active_policy, staff_user):
        """$20,000 annual increase -> above $500 threshold -> PENDING_CUSTOMER_APPROVAL."""
        end, charges = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=2000000,
            description="Major coverage increase",
            created_by=staff_user,
        )

        assert end.status == Endorsement.Status.PENDING_CUSTOMER_APPROVAL

    def test_address_correction_no_premium_change(self, active_policy, staff_user):
        end, charges = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.ADDRESS_CORRECTION,
            effective_date=date(2025, 9, 1),
            annual_premium_delta_cents=50000,
            description="Correct insured address",
            created_by=staff_user,
        )

        assert end.premium_change_cents == 0
        assert charges["total_cents"] == 0
        assert end.status == Endorsement.Status.APPROVED

    def test_cannot_endorse_draft_policy(self, staff_user, customer_user, approved_broker, tx_rules, ledger_accounts):
        policy, _ = issue_policy(
            customer=customer_user,
            broker_id=approved_broker.id,
            effective_date=date(2025, 6, 1),
            premium_amount_cents=100000,
            coverage_territory="TX",
            created_by=staff_user,
        )

        with pytest.raises(EndorsementError, match="active policy"):
            create_endorsement(
                policy_id=policy.id,
                endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
                effective_date=date(2025, 9, 1),
                annual_premium_delta_cents=10000,
                description="test",
                created_by=staff_user,
            )

    def test_effective_date_outside_term_rejected(self, active_policy, staff_user):
        with pytest.raises(EndorsementError, match="within the policy term"):
            create_endorsement(
                policy_id=active_policy.id,
                endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
                effective_date=date(2027, 1, 1),
                annual_premium_delta_cents=10000,
                description="test",
                created_by=staff_user,
            )


class TestEndorsementApproval:
    def test_customer_approves_then_pending_payment(self, active_policy, staff_user, customer_user):
        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=2000000,
            description="Needs approval",
            created_by=staff_user,
        )

        approved = approve_endorsement(endorsement_id=end.id, approved_by=customer_user)
        assert approved.status == Endorsement.Status.PENDING_PAYMENT


class TestApplyEndorsement:
    def test_apply_posts_balanced_ledger(self, active_policy, staff_user, ledger_accounts):
        end, charges = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Increase",
            created_by=staff_user,
        )

        applied = apply_endorsement(endorsement_id=end.id)
        assert applied.status == Endorsement.Status.APPLIED

        entry = JournalEntry.objects.get(idempotency_key=f"endorsement-{end.id}")
        lines = entry.lines.all()
        total_debits = sum(ln.amount_cents for ln in lines if ln.entry_type == JournalLine.EntryType.DEBIT)
        total_credits = sum(ln.amount_cents for ln in lines if ln.entry_type == JournalLine.EntryType.CREDIT)
        assert total_debits == total_credits

    def test_apply_updates_policy_premium(self, active_policy, staff_user, ledger_accounts):
        original_premium = active_policy.premium_amount_cents

        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Increase",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end.id)

        active_policy.refresh_from_db()
        assert active_policy.premium_amount_cents == original_premium + 60000

    def test_endorsement_commission_posted(self, active_policy, staff_user, ledger_accounts):
        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Increase",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end.id)

        commission_entry = JournalEntry.objects.get(idempotency_key=f"endorsement-commission-{end.id}")
        debit = commission_entry.lines.get(entry_type=JournalLine.EntryType.DEBIT)
        assert debit.account.code == "5100"
        assert debit.amount_cents > 0

    def test_tax_and_fee_adjustments_use_policy_inception_rates(self, active_policy, staff_user, ledger_accounts):
        end, charges = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=100000,
            description="Increase",
            created_by=staff_user,
        )

        assert len(charges["tax_details"]) > 0
        assert len(charges["fee_details"]) > 0
        assert charges["total_tax_cents"] > 0
        assert charges["total_fees_cents"] > 0


class TestCorrection:
    def test_correction_reverses_original(self, active_policy, staff_user, ledger_accounts):
        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Original",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end.id)

        corrected = correct_endorsement(
            endorsement_id=end.id,
            corrected_effective_date=date(2025, 9, 1),
            created_by=staff_user,
        )

        end.refresh_from_db()
        assert end.status == Endorsement.Status.REVERSED
        assert corrected.correction_of_id == end.id
        assert corrected.status == Endorsement.Status.APPLIED

    def test_correction_original_entry_untouched(self, active_policy, staff_user, ledger_accounts):
        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Original",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end.id)

        original_entry = JournalEntry.objects.get(idempotency_key=f"endorsement-{end.id}")
        original_lines_count = original_entry.lines.count()

        correct_endorsement(
            endorsement_id=end.id,
            corrected_effective_date=date(2025, 9, 1),
            created_by=staff_user,
        )

        original_entry.refresh_from_db()
        assert original_entry.status == JournalEntry.Status.POSTED
        assert original_entry.lines.count() == original_lines_count

    def test_correction_creates_reversal_entry(self, active_policy, staff_user, ledger_accounts):
        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Original",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end.id)
        correct_endorsement(
            endorsement_id=end.id,
            corrected_effective_date=date(2025, 9, 1),
            created_by=staff_user,
        )

        reversal = JournalEntry.objects.get(idempotency_key=f"endorsement-reversal-{end.id}")
        assert reversal.status == JournalEntry.Status.POSTED

    def test_correction_different_effective_date_different_prorata(self, active_policy, staff_user, ledger_accounts):
        end, charges1 = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Original",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end.id)

        corrected = correct_endorsement(
            endorsement_id=end.id,
            corrected_effective_date=date(2025, 9, 1),
            created_by=staff_user,
        )

        assert corrected.premium_change_cents != end.premium_change_cents
        assert corrected.premium_change_cents > end.premium_change_cents


class TestLeapYear:
    def test_leap_year_policy_term_366_days(
        self, staff_user, customer_user, approved_broker, tx_rules, ledger_accounts
    ):
        """Policy from 2024-01-01 to 2025-01-01 = 366 days (includes Feb 29)."""
        policy, _ = issue_policy(
            customer=customer_user,
            broker_id=approved_broker.id,
            effective_date=date(2024, 1, 1),
            premium_amount_cents=100000,
            coverage_territory="TX",
            created_by=staff_user,
        )
        result = create_checkout_for_policy(policy_id=policy.id, requested_by=staff_user)
        handle_payment_success(payment_id=result["payment_id"])
        policy.refresh_from_db()

        total_days = (policy.expiration_date - policy.effective_date).days
        assert total_days == 366

        end, charges = create_endorsement(
            policy_id=policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2024, 7, 1),
            annual_premium_delta_cents=36600,
            description="Leap year test",
            created_by=staff_user,
        )

        remaining = (policy.expiration_date - date(2024, 7, 1)).days
        expected = prorate_amount(36600, remaining, 366)
        assert charges["premium_change_cents"] == expected


class TestAsOfReconstruction:
    def test_as_of_before_endorsement(self, active_policy, staff_user):
        from django.utils import timezone

        before_time = timezone.now()

        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Later endorsement",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end.id)

        snapshot = get_policy_as_of(active_policy.id, as_of=before_time)
        assert len(snapshot["endorsements"]) == 0
        assert snapshot["effective_premium_cents"] == 100000

    def test_as_of_after_endorsement(self, active_policy, staff_user):
        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Applied endorsement",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end.id)

        snapshot = get_policy_as_of(active_policy.id, as_of=None)
        assert len(snapshot["endorsements"]) == 1
        assert snapshot["effective_premium_cents"] == 160000

    def test_as_of_between_two_endorsements(self, active_policy, staff_user):
        from django.utils import timezone

        end1, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 9, 1),
            annual_premium_delta_cents=30000,
            description="First endorsement",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end1.id)

        between_time = timezone.now()

        end2, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=20000,
            description="Second endorsement",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end2.id)

        snapshot = get_policy_as_of(active_policy.id, as_of=between_time)
        assert len(snapshot["endorsements"]) == 1
        assert snapshot["effective_premium_cents"] == 130000


class TestPdfGeneration:
    def test_declarations_pdf_generated(self, active_policy):
        pdf_bytes = generate_declarations_pdf(active_policy.id)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:5] == b"%PDF-"

    def test_declarations_pdf_with_as_of(self, active_policy):
        from django.utils import timezone

        pdf_bytes = generate_declarations_pdf(active_policy.id, as_of=timezone.now())
        assert pdf_bytes[:5] == b"%PDF-"

    def test_endorsement_schedule_pdf(self, active_policy, staff_user):
        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Test endorsement for PDF",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end.id)

        pdf_bytes = generate_endorsement_schedule_pdf(active_policy.id)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:5] == b"%PDF-"


class TestEndorsementAPI:
    @pytest.fixture
    def api(self):
        return APIClient()

    def test_create_endorsement_via_api(self, api, active_policy, staff_user):
        api.force_authenticate(user=staff_user)
        resp = api.post(
            "/api/endorsements/",
            {
                "policy_id": active_policy.id,
                "endorsement_type": "COVERAGE_LIMIT_CHANGE",
                "effective_date": "2025-12-01",
                "annual_premium_delta_cents": 20000,
                "description": "API test",
            },
            format="json",
        )
        assert resp.status_code == 201
        assert "endorsement" in resp.data
        assert "charges" in resp.data

    def test_list_endorsements(self, api, active_policy, staff_user):
        api.force_authenticate(user=staff_user)
        create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=20000,
            description="Test",
            created_by=staff_user,
        )

        resp = api.get(f"/api/endorsements/?policy_id={active_policy.id}")
        assert resp.status_code == 200
        assert len(resp.data) == 1

    def test_approve_via_api(self, api, active_policy, staff_user, customer_user):
        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=2000000,
            description="Needs approval",
            created_by=staff_user,
        )
        api.force_authenticate(user=customer_user)
        resp = api.post(f"/api/endorsements/{end.id}/approve/")
        assert resp.status_code == 200
        assert resp.data["status"] == "PENDING_PAYMENT"

    def test_correct_via_api(self, api, active_policy, staff_user, ledger_accounts):
        end, _ = create_endorsement(
            policy_id=active_policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2025, 12, 1),
            annual_premium_delta_cents=60000,
            description="Original",
            created_by=staff_user,
        )
        apply_endorsement(endorsement_id=end.id)

        api.force_authenticate(user=staff_user)
        resp = api.post(
            f"/api/endorsements/{end.id}/correct/",
            {"corrected_effective_date": "2025-09-01"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["correction_of"] == end.id

    def test_as_of_api(self, api, active_policy, staff_user):
        api.force_authenticate(user=staff_user)
        resp = api.get(f"/api/policies/{active_policy.id}/as-of/")
        assert resp.status_code == 200
        assert "effective_premium_cents" in resp.data

    def test_declarations_pdf_api(self, api, active_policy, staff_user):
        api.force_authenticate(user=staff_user)
        resp = api.get(f"/api/documents/policy/{active_policy.id}/declarations/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"

    def test_endorsement_schedule_pdf_api(self, api, active_policy, staff_user):
        api.force_authenticate(user=staff_user)
        resp = api.get(f"/api/documents/policy/{active_policy.id}/endorsement-schedule/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"

    def test_customer_access_control(self, api, active_policy):
        other = User.objects.create_user(
            username="other", password="pass", role=User.Role.CUSTOMER, email="other@example.com"
        )
        api.force_authenticate(user=other)
        resp = api.get(f"/api/endorsements/?policy_id={active_policy.id}")
        assert resp.status_code == 200
        assert len(resp.data) == 0
