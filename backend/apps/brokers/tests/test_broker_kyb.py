import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.brokers.models import Broker, KYBVerification
from apps.brokers.services import create_broker, process_kyb_webhook


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="staff", password="testpass", role=User.Role.STAFF, is_staff=True)


@pytest.fixture
def approved_broker(db):
    user = User.objects.create_user(username="broker_contact", password="pass", role=User.Role.STAFF)
    broker = Broker.objects.create(
        user=user,
        company_name="Approved Agency",
        commission_rate_bps=1500,
        status=Broker.Status.APPROVED,
    )
    KYBVerification.objects.create(broker=broker, persona_inquiry_id="inq-123", status=KYBVerification.Status.COMPLETED)
    return broker


@pytest.fixture
def pending_broker(db):
    user = User.objects.create_user(username="pending_contact", password="pass", role=User.Role.STAFF)
    return Broker.objects.create(
        user=user,
        company_name="Pending Agency",
        commission_rate_bps=1200,
        status=Broker.Status.PENDING_KYB,
    )


class TestCreateBroker:
    def test_create_via_api(self, api, staff_user):
        api.force_authenticate(user=staff_user)
        resp = api.post(
            "/api/brokers/",
            {
                "company_name": "Test Agency",
                "commission_rate_bps": 1500,
                "contact_email": "agent@test.com",
                "contact_first_name": "John",
                "contact_last_name": "Agent",
            },
        )
        assert resp.status_code == 201
        assert resp.data["company_name"] == "Test Agency"
        assert resp.data["status"] == "PENDING_KYB"

    def test_create_via_service(self, db):
        broker = create_broker(
            company_name="Service Agency",
            commission_rate_bps=1000,
            contact_email="svc@test.com",
            contact_first_name="Svc",
            contact_last_name="Contact",
        )
        assert broker.status == Broker.Status.PENDING_KYB
        assert broker.user.email == "svc@test.com"


class TestKYBWebhookProcessing:
    def test_approved_status_transition(self, pending_broker):
        broker = process_kyb_webhook(
            broker_id=pending_broker.id,
            inquiry_id="inq-001",
            persona_status="completed",
        )
        assert broker.status == Broker.Status.APPROVED
        kyb = KYBVerification.objects.get(broker=broker, persona_inquiry_id="inq-001")
        assert kyb.status == KYBVerification.Status.COMPLETED

    def test_rejected_status_transition(self, pending_broker):
        broker = process_kyb_webhook(
            broker_id=pending_broker.id,
            inquiry_id="inq-002",
            persona_status="failed",
        )
        assert broker.status == Broker.Status.REJECTED

    def test_duplicate_webhook_is_harmless(self, pending_broker):
        process_kyb_webhook(
            broker_id=pending_broker.id,
            inquiry_id="inq-003",
            persona_status="completed",
        )
        broker = process_kyb_webhook(
            broker_id=pending_broker.id,
            inquiry_id="inq-003",
            persona_status="completed",
        )
        assert broker.status == Broker.Status.APPROVED

    def test_cannot_regress_approved_to_rejected(self, pending_broker):
        process_kyb_webhook(
            broker_id=pending_broker.id,
            inquiry_id="inq-004",
            persona_status="completed",
        )
        broker = process_kyb_webhook(
            broker_id=pending_broker.id,
            inquiry_id="inq-005",
            persona_status="failed",
        )
        assert broker.status == Broker.Status.APPROVED

    def test_cannot_regress_rejected_to_pending(self, pending_broker):
        process_kyb_webhook(
            broker_id=pending_broker.id,
            inquiry_id="inq-006",
            persona_status="failed",
        )
        broker = process_kyb_webhook(
            broker_id=pending_broker.id,
            inquiry_id="inq-007",
            persona_status="completed",
        )
        assert broker.status == Broker.Status.REJECTED
