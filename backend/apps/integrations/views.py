import json
import logging

from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.brokers.services import process_kyb_webhook
from apps.integrations.persona.webhooks import (
    mark_webhook_failed,
    mark_webhook_processed,
    parse_persona_webhook,
    record_webhook_event,
    verify_persona_signature,
)
from apps.integrations.stripe.webhooks import verify_stripe_signature
from apps.payments.models import Payment
from apps.payments.services import handle_payment_failure, handle_payment_success

logger = logging.getLogger(__name__)


class PersonaWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        payload_body = request.body.decode("utf-8")
        signature = request.headers.get("Persona-Signature", "")

        if not verify_persona_signature(payload_body=payload_body, signature_header=signature):
            return Response({"detail": "Invalid signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            payload = json.loads(payload_body)
        except json.JSONDecodeError:
            return Response({"detail": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)

        event_id = payload.get("data", {}).get("id", "")
        if not event_id:
            return Response({"detail": "Missing event ID"}, status=status.HTTP_400_BAD_REQUEST)

        parsed = parse_persona_webhook(payload)

        webhook_event, created = record_webhook_event(
            provider="PERSONA",
            event_id=event_id,
            event_type=parsed["event_type"],
            payload=payload,
        )

        if not created:
            return Response({"detail": "Already processed"}, status=status.HTTP_200_OK)

        try:
            reference_id = parsed["reference_id"]
            if reference_id and reference_id.startswith("broker-"):
                broker_id = int(reference_id.split("-", 1)[1])
                process_kyb_webhook(
                    broker_id=broker_id,
                    inquiry_id=parsed["inquiry_id"],
                    persona_status=parsed["status"],
                )
            mark_webhook_processed(webhook_event)
        except Exception:
            logger.exception("Error processing Persona webhook %s", event_id)
            mark_webhook_failed(webhook_event, "Processing error")
            return Response({"detail": "Processing error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"detail": "OK"}, status=status.HTTP_200_OK)


class StripeWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        payload_body = request.body.decode("utf-8")
        signature = request.headers.get("Stripe-Signature", "")

        if not verify_stripe_signature(payload_body=payload_body, signature_header=signature):
            return Response({"detail": "Invalid signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            event_data = json.loads(payload_body)
        except json.JSONDecodeError:
            return Response({"detail": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)

        event_id = event_data.get("id", "")
        event_type = event_data.get("type", "")

        if not event_id:
            return Response({"detail": "Missing event ID"}, status=status.HTTP_400_BAD_REQUEST)

        webhook_event, created = record_webhook_event(
            provider="STRIPE",
            event_id=event_id,
            event_type=event_type,
            payload=event_data,
        )

        if not created:
            return Response({"detail": "Already processed"}, status=status.HTTP_200_OK)

        try:
            self._dispatch_event(event_type, event_data)
            mark_webhook_processed(webhook_event)
        except Exception:
            logger.exception("Error processing Stripe webhook %s", event_id)
            mark_webhook_failed(webhook_event, "Processing error")
            return Response({"detail": "Processing error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"detail": "OK"}, status=status.HTTP_200_OK)

    def _dispatch_event(self, event_type, event_data):
        if event_type == "checkout.session.completed":
            self._handle_checkout_completed(event_data)
        elif event_type == "checkout.session.expired":
            self._handle_checkout_expired(event_data)

    def _handle_checkout_completed(self, event_data):
        session = event_data.get("data", {}).get("object", {})
        session_id = session.get("id", "")
        payment_intent_id = session.get("payment_intent", "")

        try:
            payment = Payment.objects.get(stripe_checkout_session_id=session_id)
        except Payment.DoesNotExist:
            logger.warning("No payment found for checkout session %s", session_id)
            return

        handle_payment_success(
            payment_id=payment.id,
            stripe_payment_intent_id=payment_intent_id,
        )

    def _handle_checkout_expired(self, event_data):
        session = event_data.get("data", {}).get("object", {})
        session_id = session.get("id", "")

        try:
            payment = Payment.objects.get(stripe_checkout_session_id=session_id)
        except Payment.DoesNotExist:
            logger.warning("No payment found for expired checkout session %s", session_id)
            return

        handle_payment_failure(
            payment_id=payment.id,
            reason="Checkout session expired",
        )
