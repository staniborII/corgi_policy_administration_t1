import pytest


@pytest.fixture(autouse=True)
def _no_stripe_keys(settings):
    """Ensure tests run in simulated mode — never hit real Stripe APIs."""
    settings.STRIPE_SECRET_KEY = ""
    settings.STRIPE_PUBLISHABLE_KEY = ""
    settings.STRIPE_WEBHOOK_SECRET = ""
