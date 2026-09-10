import logging
import uuid

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)

SIMULATED_PREFIX = "SIMULATED"


def create_connect_account(*, reference_id, company_name):
    """
    Create a Stripe Connect Express account for broker KYB onboarding.
    Returns the account ID, or a simulated ID if Stripe keys are not configured.
    """
    secret_key = settings.STRIPE_SECRET_KEY

    if not secret_key:
        simulated_id = f"{SIMULATED_PREFIX}-acct-{uuid.uuid4().hex[:12]}"
        logger.warning("STRIPE_SECRET_KEY not configured — returning SIMULATED Connect account: %s", simulated_id)
        return simulated_id

    stripe.api_key = secret_key

    account = stripe.Account.create(
        type="express",
        country="US",
        business_type="company",
        company={"name": company_name},
        metadata={"reference_id": reference_id, "source": "corgi_kyb"},
        capabilities={
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
    )

    logger.info("Stripe Connect account created: account_id=%s, reference=%s", account.id, reference_id)
    return account.id


def create_account_link(*, account_id, refresh_url, return_url):
    """
    Create a Stripe Account Link for hosted onboarding.
    Returns the onboarding URL, or None in simulated mode.
    """
    secret_key = settings.STRIPE_SECRET_KEY

    if not secret_key or account_id.startswith(SIMULATED_PREFIX):
        logger.warning("Simulated mode — no real onboarding URL for account %s", account_id)
        return None

    stripe.api_key = secret_key

    account_link = stripe.AccountLink.create(
        account=account_id,
        type="account_onboarding",
        refresh_url=refresh_url,
        return_url=return_url,
    )

    logger.info("Account link created for %s", account_id)
    return account_link.url


def retrieve_account_status(account_id):
    """
    Retrieve the verification status of a Stripe Connect account.
    Returns a dict with charges_enabled, payouts_enabled, requirements_due, disabled_reason.
    """
    secret_key = settings.STRIPE_SECRET_KEY

    if not secret_key or account_id.startswith(SIMULATED_PREFIX):
        return {
            "charges_enabled": False,
            "payouts_enabled": False,
            "requirements_due": [],
            "disabled_reason": "simulated",
        }

    stripe.api_key = secret_key

    account = stripe.Account.retrieve(account_id)

    return {
        "charges_enabled": account.charges_enabled,
        "payouts_enabled": account.payouts_enabled,
        "requirements_due": list(account.requirements.currently_due or []),
        "disabled_reason": account.requirements.disabled_reason,
    }


def is_account_verified(account_id):
    """Check if a Stripe Connect account has completed KYB verification."""
    status = retrieve_account_status(account_id)
    return status["charges_enabled"] and not status["requirements_due"]
