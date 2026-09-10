import logging

from django.db import transaction
from django.utils.crypto import get_random_string

from apps.accounts.models import User
from apps.brokers.models import Broker, KYBVerification
from apps.integrations.persona.client import create_persona_inquiry
from apps.ws.notifications import notify_broker_change

logger = logging.getLogger(__name__)


class BrokerError(Exception):
    pass


@transaction.atomic
def create_broker(*, company_name, commission_rate_bps, contact_email, contact_first_name, contact_last_name):
    """Create a broker with a contact user account and initiate KYB."""
    if User.objects.filter(username=contact_email).exists():
        raise BrokerError(f"User with email {contact_email} already exists")

    user = User.objects.create_user(
        username=contact_email,
        email=contact_email,
        first_name=contact_first_name,
        last_name=contact_last_name,
        password=get_random_string(20),
        role=User.Role.STAFF,
    )

    broker = Broker.objects.create(
        user=user,
        company_name=company_name,
        commission_rate_bps=commission_rate_bps,
        status=Broker.Status.PENDING_KYB,
    )

    logger.info(f"Broker created: broker_id={broker.id}")

    return broker


@transaction.atomic
def initiate_kyb(*, broker_id):
    """Create a Persona inquiry and KYBVerification record."""
    broker = Broker.objects.select_for_update().get(id=broker_id)

    if broker.status == Broker.Status.APPROVED:
        raise BrokerError("Broker is already approved")

    inquiry_id = create_persona_inquiry(
        reference_id=f"broker-{broker.id}",
        company_name=broker.company_name,
    )

    kyb = KYBVerification.objects.create(
        broker=broker,
        persona_inquiry_id=inquiry_id,
        status=KYBVerification.Status.PENDING,
    )

    broker.status = Broker.Status.PENDING_KYB
    broker.save(update_fields=["status", "updated_at"])

    logger.info(f"KYB initiated: broker_id={broker_id}, provider_reference={inquiry_id}")

    return kyb


@transaction.atomic
def process_kyb_webhook(*, broker_id, inquiry_id, persona_status):
    """
    Update broker KYB state from a Persona webhook.
    Tolerates out-of-order events: never regresses from a final state (APPROVED/REJECTED).
    """
    broker = Broker.objects.select_for_update().get(id=broker_id)

    old_status = broker.status
    if broker.status in (Broker.Status.APPROVED, Broker.Status.REJECTED):
        logger.info(f"KYB webhook skipped for broker_id={broker_id}, already in terminal status={broker.status}")
        return broker

    kyb = KYBVerification.objects.filter(
        broker=broker,
        persona_inquiry_id=inquiry_id,
    ).first()

    if not kyb:
        kyb = KYBVerification.objects.create(
            broker=broker,
            persona_inquiry_id=inquiry_id,
            status=KYBVerification.Status.PENDING,
        )

    if persona_status == "completed":
        kyb.status = KYBVerification.Status.COMPLETED
        kyb.save(update_fields=["status", "updated_at"])
        broker.status = Broker.Status.APPROVED
        broker.save(update_fields=["status", "updated_at"])
    elif persona_status in ("failed", "declined"):
        kyb.status = KYBVerification.Status.FAILED
        kyb.save(update_fields=["status", "updated_at"])
        broker.status = Broker.Status.REJECTED
        broker.save(update_fields=["status", "updated_at"])

    logger.info(f"KYB status updated: broker_id={broker_id}, old_status={old_status} -> new_status={broker.status}")

    transaction.on_commit(lambda: notify_broker_change(broker, "broker.kyb_updated"))

    return broker
