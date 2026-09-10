import json

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.brokers.models import Broker, KYBVerification
from apps.integrations.models import WebhookEvent


def build_account_updated_payload(
    *, event_id, account_id, charges_enabled, requirements_due=None, disabled_reason=None
):
    return {
        "id": event_id,
        "type": "account.updated",
        "account": account_id,
        "data": {
            "object": {
                "id": account_id,
                "object": "account",
                "charges_enabled": charges_enabled,
                "payouts_enabled": charges_enabled,
                "requirements": {
                    "currently_due": requirements_due or [],
                    "past_due": [],
                    "eventually_due": [],
                    "disabled_reason": disabled_reason,
                    "current_deadline": None,
                },
            },
        },
    }


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def pending_broker(db):
    user = User.objects.create_user(username="broker_connect", password="pass", role=User.Role.STAFF)
    broker = Broker.objects.create(
        user=user,
        company_name="Connect Test Agency",
        commission_rate_bps=1500,
        status=Broker.Status.PENDING_KYB,
        stripe_connect_account_id="acct_test_123",
    )
    KYBVerification.objects.create(
        broker=broker,
        provider=KYBVerification.Provider.STRIPE_CONNECT,
        provider_reference="acct_test_123",
        status=KYBVerification.Status.PENDING,
    )
    return broker


@pytest.fixture(autouse=True)
def _no_stripe_secret(settings):
    settings.STRIPE_WEBHOOK_SECRET = ""


class TestStripeConnectKYBWebhook:
    def test_account_verified_approves_broker(self, api_client, pending_broker):
        payload = build_account_updated_payload(
            event_id="evt_connect_001",
            account_id="acct_test_123",
            charges_enabled=True,
        )
        resp = api_client.post(
            "/api/integrations/webhooks/stripe/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        pending_broker.refresh_from_db()
        assert pending_broker.status == Broker.Status.APPROVED

        kyb = pending_broker.kyb_verifications.latest("created_at")
        assert kyb.status == KYBVerification.Status.COMPLETED
        assert kyb.provider == KYBVerification.Provider.STRIPE_CONNECT

    def test_account_with_requirements_stays_pending(self, api_client, pending_broker):
        payload = build_account_updated_payload(
            event_id="evt_connect_002",
            account_id="acct_test_123",
            charges_enabled=False,
            requirements_due=["company.tax_id", "business_profile.url"],
        )
        resp = api_client.post(
            "/api/integrations/webhooks/stripe/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        pending_broker.refresh_from_db()
        assert pending_broker.status == Broker.Status.PENDING_KYB

    def test_account_rejected_rejects_broker(self, api_client, pending_broker):
        payload = build_account_updated_payload(
            event_id="evt_connect_003",
            account_id="acct_test_123",
            charges_enabled=False,
            disabled_reason="rejected.fraud",
        )
        resp = api_client.post(
            "/api/integrations/webhooks/stripe/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        pending_broker.refresh_from_db()
        assert pending_broker.status == Broker.Status.REJECTED

        kyb = pending_broker.kyb_verifications.latest("created_at")
        assert kyb.status == KYBVerification.Status.FAILED

    def test_duplicate_webhook_idempotent(self, api_client, pending_broker):
        payload = build_account_updated_payload(
            event_id="evt_connect_dup",
            account_id="acct_test_123",
            charges_enabled=True,
        )
        body = json.dumps(payload)

        resp1 = api_client.post("/api/integrations/webhooks/stripe/", data=body, content_type="application/json")
        assert resp1.status_code == 200

        resp2 = api_client.post("/api/integrations/webhooks/stripe/", data=body, content_type="application/json")
        assert resp2.status_code == 200
        assert resp2.data["detail"] == "Already processed"
        assert WebhookEvent.objects.filter(event_id="evt_connect_dup").count() == 1

    def test_terminal_state_not_regressed(self, api_client, pending_broker):
        approve_payload = build_account_updated_payload(
            event_id="evt_connect_approve",
            account_id="acct_test_123",
            charges_enabled=True,
        )
        api_client.post(
            "/api/integrations/webhooks/stripe/",
            data=json.dumps(approve_payload),
            content_type="application/json",
        )
        pending_broker.refresh_from_db()
        assert pending_broker.status == Broker.Status.APPROVED

        reject_payload = build_account_updated_payload(
            event_id="evt_connect_late_reject",
            account_id="acct_test_123",
            charges_enabled=False,
            disabled_reason="rejected.fraud",
        )
        api_client.post(
            "/api/integrations/webhooks/stripe/",
            data=json.dumps(reject_payload),
            content_type="application/json",
        )
        pending_broker.refresh_from_db()
        assert pending_broker.status == Broker.Status.APPROVED

    def test_unknown_account_ignored(self, api_client, db):
        payload = build_account_updated_payload(
            event_id="evt_connect_unknown",
            account_id="acct_nonexistent",
            charges_enabled=True,
        )
        resp = api_client.post(
            "/api/integrations/webhooks/stripe/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200


class TestKYBProviderConfig:
    def test_provider_switching(self, db):
        from apps.integrations.models import KYBProviderConfig

        assert KYBProviderConfig.get_active_provider() == KYBProviderConfig.KYBProvider.STRIPE_CONNECT

        KYBProviderConfig.objects.create(active_provider=KYBProviderConfig.KYBProvider.PERSONA)
        assert KYBProviderConfig.get_active_provider() == KYBProviderConfig.KYBProvider.PERSONA

        config = KYBProviderConfig.objects.get(pk=1)
        config.active_provider = KYBProviderConfig.KYBProvider.SIMULATED
        config.save()
        assert KYBProviderConfig.get_active_provider() == KYBProviderConfig.KYBProvider.SIMULATED
