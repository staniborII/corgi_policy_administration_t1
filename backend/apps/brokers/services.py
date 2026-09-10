import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.utils.crypto import get_random_string

from apps.accounts.models import User
from apps.brokers.models import Broker, KYBVerification
from apps.integrations.models import KYBProviderConfig
from apps.integrations.persona.client import create_persona_inquiry
from apps.integrations.stripe.connect import create_account_link, create_connect_account
from apps.ws.notifications import notify_broker_change

logger = logging.getLogger(__name__)


class BrokerError(Exception):
    pass


@transaction.atomic
def create_broker(*, company_name, commission_rate_bps, contact_email, contact_first_name, contact_last_name):
    """Create a broker with a contact user account."""
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

    logger.info("Broker created: broker_id=%s", broker.id)

    return broker


@transaction.atomic
def initiate_kyb(*, broker_id):
    """Initiate KYB verification using the active provider (Stripe Connect, Persona, or Simulated)."""
    broker = Broker.objects.select_for_update().get(id=broker_id)

    if broker.status == Broker.Status.APPROVED:
        raise BrokerError("Broker is already approved")

    active_provider = KYBProviderConfig.get_active_provider()

    if active_provider == KYBProviderConfig.KYBProvider.STRIPE_CONNECT:
        return _initiate_stripe_connect_kyb(broker)
    elif active_provider == KYBProviderConfig.KYBProvider.PERSONA:
        return _initiate_persona_kyb(broker)
    else:
        return _initiate_simulated_kyb(broker)


def _initiate_stripe_connect_kyb(broker):
    """Create a Stripe Connect Express account and return an onboarding link."""
    reference_id = f"broker-{broker.id}"
    try:
        account_id = create_connect_account(reference_id=reference_id, company_name=broker.company_name)
    except Exception as exc:
        raise BrokerError(f"Stripe Connect error: {exc}") from exc

    broker.stripe_connect_account_id = account_id
    broker.status = Broker.Status.PENDING_KYB
    broker.save(update_fields=["stripe_connect_account_id", "status", "updated_at"])

    frontend_url = settings.FRONTEND_URL
    try:
        onboarding_url = create_account_link(
            account_id=account_id,
            refresh_url=f"{frontend_url}/staff/brokers?kyb_refresh={broker.id}",
            return_url=f"{frontend_url}/staff/brokers?kyb_complete={broker.id}",
        )
    except Exception as exc:
        raise BrokerError(f"Stripe Connect onboarding link error: {exc}") from exc

    kyb = KYBVerification.objects.create(
        broker=broker,
        provider=KYBVerification.Provider.STRIPE_CONNECT,
        provider_reference=account_id,
        status=KYBVerification.Status.PENDING,
        onboarding_url=onboarding_url or "",
    )

    logger.info("Stripe Connect KYB initiated: broker_id=%s, account_id=%s", broker.id, account_id)
    return kyb


def _initiate_persona_kyb(broker):
    """Create a Persona inquiry for KYB verification."""
    reference_id = f"broker-{broker.id}"
    inquiry_id = create_persona_inquiry(reference_id=reference_id, company_name=broker.company_name)

    kyb = KYBVerification.objects.create(
        broker=broker,
        provider=KYBVerification.Provider.PERSONA,
        provider_reference=inquiry_id,
        persona_inquiry_id=inquiry_id,
        status=KYBVerification.Status.PENDING,
    )

    broker.status = Broker.Status.PENDING_KYB
    broker.save(update_fields=["status", "updated_at"])

    logger.info("Persona KYB initiated: broker_id=%s, inquiry_id=%s", broker.id, inquiry_id)
    return kyb


def _initiate_simulated_kyb(broker):
    """Create a simulated KYB verification."""
    simulated_ref = f"SIMULATED-kyb-{uuid.uuid4().hex[:12]}"

    kyb = KYBVerification.objects.create(
        broker=broker,
        provider=KYBVerification.Provider.SIMULATED,
        provider_reference=simulated_ref,
        status=KYBVerification.Status.PENDING,
    )

    broker.status = Broker.Status.PENDING_KYB
    broker.save(update_fields=["status", "updated_at"])

    logger.info("Simulated KYB initiated: broker_id=%s, ref=%s", broker.id, simulated_ref)
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
        logger.info("KYB webhook skipped for broker_id=%s, already in terminal status=%s", broker_id, broker.status)
        return broker

    kyb = KYBVerification.objects.filter(
        broker=broker,
        persona_inquiry_id=inquiry_id,
    ).first()

    if not kyb:
        kyb = KYBVerification.objects.create(
            broker=broker,
            provider=KYBVerification.Provider.PERSONA,
            provider_reference=inquiry_id,
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

    logger.info("KYB status updated: broker_id=%s, old=%s -> new=%s", broker_id, old_status, broker.status)

    transaction.on_commit(lambda: notify_broker_change(broker, "broker.kyb_updated"))

    return broker


@transaction.atomic
def process_connect_account_updated(*, account_id, charges_enabled, requirements_due, disabled_reason=None):
    """
    Update broker KYB state from a Stripe Connect account.updated webhook.
    Tolerates out-of-order events: never regresses from APPROVED/REJECTED.
    """
    try:
        broker = Broker.objects.select_for_update().get(stripe_connect_account_id=account_id)
    except Broker.DoesNotExist:
        logger.warning("No broker found for Connect account %s", account_id)
        return None

    old_status = broker.status
    if broker.status in (Broker.Status.APPROVED, Broker.Status.REJECTED):
        logger.info("Connect webhook skipped for broker_id=%s, already terminal status=%s", broker.id, broker.status)
        return broker

    kyb = KYBVerification.objects.filter(
        broker=broker,
        provider=KYBVerification.Provider.STRIPE_CONNECT,
        provider_reference=account_id,
    ).first()

    if not kyb:
        kyb = KYBVerification.objects.create(
            broker=broker,
            provider=KYBVerification.Provider.STRIPE_CONNECT,
            provider_reference=account_id,
            status=KYBVerification.Status.PENDING,
        )

    kyb.result_payload = {
        "charges_enabled": charges_enabled,
        "requirements_due": requirements_due,
        "disabled_reason": disabled_reason,
    }

    if charges_enabled and not requirements_due:
        kyb.status = KYBVerification.Status.COMPLETED
        kyb.save(update_fields=["status", "result_payload", "updated_at"])
        broker.status = Broker.Status.APPROVED
        broker.save(update_fields=["status", "updated_at"])
    elif disabled_reason and disabled_reason.startswith("rejected"):
        kyb.status = KYBVerification.Status.FAILED
        kyb.save(update_fields=["status", "result_payload", "updated_at"])
        broker.status = Broker.Status.REJECTED
        broker.save(update_fields=["status", "updated_at"])
    else:
        kyb.save(update_fields=["result_payload", "updated_at"])

    logger.info("Connect KYB updated: broker_id=%s, old=%s -> new=%s", broker.id, old_status, broker.status)

    transaction.on_commit(lambda: notify_broker_change(broker, "broker.kyb_updated"))

    return broker
