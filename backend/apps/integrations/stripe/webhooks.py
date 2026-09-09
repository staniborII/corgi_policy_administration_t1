import logging

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)


def verify_stripe_signature(*, payload_body, signature_header):
    """
    Verify Stripe webhook signature.
    Returns True if signature is valid or secret is not configured (dev mode).
    Returns False if signature verification fails.
    """
    secret = settings.STRIPE_WEBHOOK_SECRET
    if not secret:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured — skipping signature verification")
        return True

    if not signature_header:
        return False

    try:
        stripe.Webhook.construct_event(payload_body, signature_header, secret)
        return True
    except stripe.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        return False
    except ValueError:
        logger.warning("Stripe webhook payload invalid")
        return False
