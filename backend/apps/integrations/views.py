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
