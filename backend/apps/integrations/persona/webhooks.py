import hashlib
import hmac
import logging

from django.conf import settings
from django.utils import timezone

from apps.integrations.models import WebhookEvent

logger = logging.getLogger(__name__)


def verify_persona_signature(*, payload_body, signature_header):
    """
    Verify Persona webhook signature using HMAC-SHA256.
    Returns True if valid, False otherwise.
    """
    secret = settings.PERSONA_WEBHOOK_SECRET
    if not secret:
        logger.warning("PERSONA_WEBHOOK_SECRET not configured — skipping signature verification")
        return True

    if not signature_header:
        return False

    # Persona sends: t=<timestamp>,v1=<signature>
    parts = {}
    for part in signature_header.split(","):
        key, _, value = part.partition("=")
        parts[key.strip()] = value.strip()

    timestamp = parts.get("t", "")
    received_sig = parts.get("v1", "")

    if not timestamp or not received_sig:
        return False

    signed_payload = f"{timestamp}.{payload_body}"
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, received_sig)


def parse_persona_webhook(payload):
    """Extract relevant fields from a Persona webhook payload."""
    data = payload.get("data", {})
    attributes = data.get("attributes", {})

    event_type = attributes.get("name", "")
    payload_data = attributes.get("payload", {}).get("data", {})
    inquiry_attributes = payload_data.get("attributes", {})

    inquiry_id = payload_data.get("id", "")
    reference_id = inquiry_attributes.get("reference-id", "")
    persona_status = inquiry_attributes.get("status", "")

    return {
        "event_type": event_type,
        "inquiry_id": inquiry_id,
        "reference_id": reference_id,
        "status": persona_status,
    }


def record_webhook_event(*, provider, event_id, event_type, payload):
    """
    Record a webhook event idempotently. Returns (event, created).
    If the event already exists, returns the existing record.
    """
    idempotency_key = f"{provider}-{event_id}"

    existing = WebhookEvent.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing, False

    event = WebhookEvent.objects.create(
        provider=provider,
        event_id=event_id,
        event_type=event_type,
        payload=payload,
        status=WebhookEvent.Status.RECEIVED,
        idempotency_key=idempotency_key,
    )
    return event, True


def mark_webhook_processed(event):
    event.status = WebhookEvent.Status.PROCESSED
    event.processed_at = timezone.now()
    event.save(update_fields=["status", "processed_at"])


def mark_webhook_failed(event, error_message):
    event.status = WebhookEvent.Status.FAILED
    event.error_message = error_message
    event.processed_at = timezone.now()
    event.save(update_fields=["status", "error_message", "processed_at"])
