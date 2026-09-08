import hashlib
import hmac
import json
import time

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.brokers.models import Broker
from apps.integrations.models import WebhookEvent


def build_persona_payload(*, event_id, inquiry_id, reference_id, persona_status):
    return {
        "data": {
            "id": event_id,
            "type": "event",
            "attributes": {
                "name": "inquiry.completed",
                "payload": {
                    "data": {
                        "id": inquiry_id,
                        "type": "inquiry",
                        "attributes": {
                            "reference-id": reference_id,
                            "status": persona_status,
                        },
                    },
                },
            },
        },
    }


def sign_payload(payload_body, secret, timestamp=None):
    ts = timestamp or str(int(time.time()))
    signed_payload = f"{ts}.{payload_body}"
    sig = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def pending_broker(db):
    user = User.objects.create_user(username="broker_wh", password="pass", role=User.Role.STAFF)
    return Broker.objects.create(
        user=user,
        company_name="Webhook Agency",
        commission_rate_bps=1500,
        status=Broker.Status.PENDING_KYB,
    )


WEBHOOK_SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def _persona_secret(settings):
    settings.PERSONA_WEBHOOK_SECRET = WEBHOOK_SECRET


class TestPersonaWebhook:
    def test_valid_webhook_processes(self, api, pending_broker):
        payload = build_persona_payload(
            event_id="evt-001",
            inquiry_id="inq-001",
            reference_id=f"broker-{pending_broker.id}",
            persona_status="completed",
        )
        body = json.dumps(payload)
        sig = sign_payload(body, WEBHOOK_SECRET)
        resp = api.post(
            "/api/integrations/webhooks/persona/",
            data=body,
            content_type="application/json",
            HTTP_PERSONA_SIGNATURE=sig,
        )
        assert resp.status_code == 200
        pending_broker.refresh_from_db()
        assert pending_broker.status == Broker.Status.APPROVED

    def test_duplicate_webhook_is_idempotent(self, api, pending_broker):
        payload = build_persona_payload(
            event_id="evt-dup",
            inquiry_id="inq-dup",
            reference_id=f"broker-{pending_broker.id}",
            persona_status="completed",
        )
        body = json.dumps(payload)
        sig = sign_payload(body, WEBHOOK_SECRET)

        resp1 = api.post(
            "/api/integrations/webhooks/persona/",
            data=body,
            content_type="application/json",
            HTTP_PERSONA_SIGNATURE=sig,
        )
        assert resp1.status_code == 200

        resp2 = api.post(
            "/api/integrations/webhooks/persona/",
            data=body,
            content_type="application/json",
            HTTP_PERSONA_SIGNATURE=sig,
        )
        assert resp2.status_code == 200
        assert resp2.data["detail"] == "Already processed"
        assert WebhookEvent.objects.filter(event_id="evt-dup").count() == 1

    def test_invalid_signature_rejected(self, api, pending_broker):
        payload = build_persona_payload(
            event_id="evt-bad",
            inquiry_id="inq-bad",
            reference_id=f"broker-{pending_broker.id}",
            persona_status="completed",
        )
        body = json.dumps(payload)
        resp = api.post(
            "/api/integrations/webhooks/persona/",
            data=body,
            content_type="application/json",
            HTTP_PERSONA_SIGNATURE="t=123,v1=invalidsig",
        )
        assert resp.status_code == 403

    def test_missing_signature_rejected(self, api, pending_broker):
        payload = build_persona_payload(
            event_id="evt-nosig",
            inquiry_id="inq-nosig",
            reference_id=f"broker-{pending_broker.id}",
            persona_status="completed",
        )
        body = json.dumps(payload)
        resp = api.post(
            "/api/integrations/webhooks/persona/",
            data=body,
            content_type="application/json",
        )
        assert resp.status_code == 403
