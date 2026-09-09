import uuid


def simulate_payout(payment):
    return f"SIM-PAY-{uuid.uuid4().hex[:12].upper()}"


def simulate_bank_verification(destination):
    return {
        "provider": "SIMULATED",
        "reference": destination.provider_reference,
        "status": destination.verification_status,
    }
