from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.brokers.models import Broker, KYBVerification
from apps.policies.models import FeeRule, Policy, TaxRule
from apps.policies.services import PolicyError, compute_policy_charges, issue_policy


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="staff", password="testpass", role=User.Role.STAFF, is_staff=True)


@pytest.fixture
def customer_user(db):
    return User.objects.create_user(
        username="customer",
        password="testpass",
        role=User.Role.CUSTOMER,
        email="cust@example.com",
    )


@pytest.fixture
def other_customer(db):
    return User.objects.create_user(
        username="other",
        password="testpass",
        role=User.Role.CUSTOMER,
        email="other@example.com",
    )


@pytest.fixture
def approved_broker(db):
    user = User.objects.create_user(username="broker_user", password="pass", role=User.Role.STAFF)
    broker = Broker.objects.create(
        user=user,
        company_name="Approved Agency",
        commission_rate_bps=1500,
        status=Broker.Status.APPROVED,
    )
    KYBVerification.objects.create(broker=broker, persona_inquiry_id="inq-ok", status=KYBVerification.Status.COMPLETED)
    return broker


@pytest.fixture
def pending_broker(db):
    user = User.objects.create_user(username="pending_broker", password="pass", role=User.Role.STAFF)
    return Broker.objects.create(
        user=user,
        company_name="Pending Agency",
        commission_rate_bps=1200,
        status=Broker.Status.PENDING_KYB,
    )


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


class TestPolicyIssuance:
    def test_issue_with_approved_broker(self, approved_broker, customer_user, tx_rules):
        policy, charges = issue_policy(
            customer=customer_user,
            broker_id=approved_broker.id,
            effective_date=date(2025, 6, 1),
            premium_amount_cents=100000,
            coverage_territory="TX",
        )
        assert policy.status == Policy.Status.DRAFT
        assert policy.expiration_date == date(2026, 6, 1)
        assert policy.premium_amount_cents == 100000

    def test_non_approved_broker_blocked(self, pending_broker, customer_user, tx_rules):
        with pytest.raises(PolicyError, match="non-approved"):
            issue_policy(
                customer=customer_user,
                broker_id=pending_broker.id,
                effective_date=date(2025, 6, 1),
                premium_amount_cents=100000,
                coverage_territory="TX",
            )

    def test_policy_end_date_uses_anniversary(self, approved_broker, customer_user, tx_rules):
        policy, _ = issue_policy(
            customer=customer_user,
            broker_id=approved_broker.id,
            effective_date=date(2024, 2, 29),
            premium_amount_cents=50000,
            coverage_territory="TX",
        )
        assert policy.expiration_date == date(2025, 2, 28)

    def test_tx_charges_breakdown(self, tx_rules, db):
        """$1,000.00 premium: tax=4850, fee=40, total=104890."""
        charges = compute_policy_charges(
            premium_cents=100000,
            jurisdiction="TX",
            effective_date=date(2025, 1, 1),
        )
        assert charges["premium_cents"] == 100000
        assert charges["total_tax_cents"] == 4850
        assert charges["total_fees_cents"] == 40
        assert charges["total_cents"] == 104890

    def test_creates_policy_event(self, approved_broker, customer_user, tx_rules):
        policy, _ = issue_policy(
            customer=customer_user,
            broker_id=approved_broker.id,
            effective_date=date(2025, 7, 1),
            premium_amount_cents=80000,
            coverage_territory="TX",
        )
        assert policy.events.count() == 1
        event = policy.events.first()
        assert event.event_type == "CREATED"
        assert "charges" in event.data


class TestPolicyAPI:
    def test_create_policy_via_api(self, api, staff_user, customer_user, approved_broker, tx_rules):
        api.force_authenticate(user=staff_user)
        resp = api.post(
            "/api/policies/",
            {
                "customer_id": customer_user.id,
                "broker_id": approved_broker.id,
                "effective_date": "2025-06-01",
                "premium_amount_cents": 100000,
                "coverage_territory": "TX",
            },
        )
        assert resp.status_code == 201
        assert resp.data["policy"]["status"] == "DRAFT"
        assert "charges" in resp.data

    def test_customer_sees_own_policy(self, api, staff_user, customer_user, approved_broker, tx_rules):
        api.force_authenticate(user=staff_user)
        resp = api.post(
            "/api/policies/",
            {
                "customer_id": customer_user.id,
                "broker_id": approved_broker.id,
                "effective_date": "2025-06-01",
                "premium_amount_cents": 100000,
                "coverage_territory": "TX",
            },
        )
        policy_id = resp.data["policy"]["id"]

        api.force_authenticate(user=customer_user)
        resp = api.get("/api/policies/")
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["id"] == policy_id

    def test_customer_cannot_see_other_policy(
        self, api, staff_user, customer_user, other_customer, approved_broker, tx_rules
    ):
        api.force_authenticate(user=staff_user)
        resp = api.post(
            "/api/policies/",
            {
                "customer_id": customer_user.id,
                "broker_id": approved_broker.id,
                "effective_date": "2025-06-01",
                "premium_amount_cents": 100000,
                "coverage_territory": "TX",
            },
        )
        policy_id = resp.data["policy"]["id"]

        api.force_authenticate(user=other_customer)
        resp = api.get(f"/api/policies/{policy_id}/")
        assert resp.status_code == 404

    def test_staff_sees_all_policies(self, api, staff_user, customer_user, approved_broker, tx_rules):
        api.force_authenticate(user=staff_user)
        api.post(
            "/api/policies/",
            {
                "customer_id": customer_user.id,
                "broker_id": approved_broker.id,
                "effective_date": "2025-06-01",
                "premium_amount_cents": 100000,
                "coverage_territory": "TX",
            },
        )
        resp = api.get("/api/policies/")
        assert resp.status_code == 200
        assert len(resp.data) >= 1
