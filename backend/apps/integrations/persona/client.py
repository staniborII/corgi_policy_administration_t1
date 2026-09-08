import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SIMULATED_PREFIX = "SIMULATED"


def create_persona_inquiry(*, reference_id, company_name):
    """
    Create a Persona business inquiry.
    Returns the inquiry ID from Persona, or a simulated ID if credentials are not configured.
    """
    api_key = settings.PERSONA_API_KEY
    template_id = settings.PERSONA_TEMPLATE_ID

    if not api_key or not template_id:
        simulated_id = f"{SIMULATED_PREFIX}-inq-{reference_id}"
        logger.warning("Persona credentials not configured — returning SIMULATED inquiry: %s", simulated_id)
        return simulated_id

    response = requests.post(
        f"{settings.PERSONA_API_BASE}/inquiries",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Persona-Version": "2023-01-05",
            "Content-Type": "application/json",
        },
        json={
            "data": {
                "attributes": {
                    "inquiry-template-id": template_id,
                    "reference-id": reference_id,
                    "fields": {
                        "name-business": {"type": "string", "value": company_name},
                    },
                },
            },
        },
        timeout=30,
    )
    response.raise_for_status()

    inquiry_data = response.json()
    return inquiry_data["data"]["id"]
