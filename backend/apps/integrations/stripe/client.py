import logging
import uuid

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)

SIMULATED_PREFIX = "SIMULATED"


def create_checkout_session(*, amount_cents, currency="usd", metadata=None, success_url, cancel_url):
    """
    Create a Stripe Checkout Session for a one-time payment.
    Returns dict with session_id and checkout_url.
    Falls back to SIMULATED mode when STRIPE_SECRET_KEY is not configured.
    """
    secret_key = settings.STRIPE_SECRET_KEY

    if not secret_key:
        simulated_id = f"{SIMULATED_PREFIX}-cs-{uuid.uuid4().hex[:12]}"
        logger.warning("STRIPE_SECRET_KEY not configured — returning SIMULATED checkout session: %s", simulated_id)
        return {
            "session_id": simulated_id,
            "checkout_url": None,
            "simulated": True,
        }

    stripe.api_key = secret_key

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": currency,
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": "Policy Premium + Tax + Fees",
                    },
                },
                "quantity": 1,
            },
        ],
        metadata=metadata or {},
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return {
        "session_id": session.id,
        "checkout_url": session.url,
        "simulated": False,
    }


def retrieve_checkout_session(session_id):
    """Retrieve a Stripe Checkout Session by ID."""
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe.checkout.Session.retrieve(session_id)


def create_stripe_refund(*, payment_intent_id, amount_cents, metadata=None):
    """
    Create a Stripe refund against a PaymentIntent.
    Falls back to SIMULATED mode when STRIPE_SECRET_KEY is not configured.
    """
    secret_key = settings.STRIPE_SECRET_KEY

    if not secret_key:
        simulated_id = f"{SIMULATED_PREFIX}-rf-{uuid.uuid4().hex[:12]}"
        logger.warning("STRIPE_SECRET_KEY not configured — returning SIMULATED refund: %s", simulated_id)
        return {"refund_id": simulated_id, "simulated": True}

    stripe.api_key = secret_key

    refund = stripe.Refund.create(
        payment_intent=payment_intent_id,
        amount=amount_cents,
        metadata=metadata or {},
    )

    return {"refund_id": refund.id, "simulated": False}
