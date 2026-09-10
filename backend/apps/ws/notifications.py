import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def _send_to_group(group_name, event_type, data):
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "notify",
                "payload": {"event": event_type, **data},
            },
        )
    except Exception:
        logger.debug("WebSocket notification failed for group=%s event=%s", group_name, event_type, exc_info=True)


def notify_user(user_id, event_type, data=None):
    _send_to_group(f"user_{user_id}", event_type, data or {})


def notify_staff(event_type, data=None):
    _send_to_group("role_STAFF", event_type, data or {})


def notify_policy_change(policy, event_type):
    data = {"policy_id": policy.id, "policy_number": policy.policy_number}
    notify_user(policy.customer_id, event_type, data)
    notify_staff(event_type, data)


def notify_claim_change(claim, event_type):
    data = {"claim_id": claim.id, "claim_number": claim.claim_number, "policy_id": claim.policy_id}
    notify_user(claim.policy.customer_id, event_type, data)
    notify_staff(event_type, data)


def notify_broker_change(broker, event_type):
    data = {"broker_id": broker.id, "company_name": broker.company_name}
    notify_staff(event_type, data)
