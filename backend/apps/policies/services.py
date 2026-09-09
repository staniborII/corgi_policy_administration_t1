import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.brokers.models import Broker
from apps.policies.models import FeeRule, Policy, PolicyEvent
from apps.policies.selectors import get_applicable_fee_rules, get_applicable_tax_rules

_ONE = Decimal("1")
_BPS_DIVISOR = Decimal("10000")


class PolicyError(Exception):
    pass


def calculate_policy_expiration(effective_date: date) -> date:
    try:
        return effective_date.replace(year=effective_date.year + 1)
    except ValueError:
        return date(effective_date.year + 1, 2, 28)


def calculate_rate_amount(amount_cents: int, rate_bps: int) -> int:
    """(amount_cents * rate_bps) / 10000, rounded half-up to nearest cent."""
    result = Decimal(amount_cents) * Decimal(rate_bps) / _BPS_DIVISOR
    return int(result.quantize(_ONE, rounding=ROUND_HALF_UP))


def calculate_fee_amount(fee_rule: FeeRule, premium_cents: int) -> int:
    if fee_rule.fee_type == FeeRule.FeeType.FLAT:
        return fee_rule.amount_cents or 0
    return calculate_rate_amount(premium_cents, fee_rule.rate_bps or 0)


def compute_policy_charges(*, premium_cents, jurisdiction, effective_date):
    """
    Compute the full charge breakdown: premium, taxes, and fees as separate components.
    Returns a dict with premium, tax_details, fee_details, and total.
    """
    tax_rules = get_applicable_tax_rules(jurisdiction, as_of=effective_date)
    fee_rules = get_applicable_fee_rules(jurisdiction, as_of=effective_date)

    tax_details = []
    total_tax = 0
    for rule in tax_rules:
        amount = calculate_rate_amount(premium_cents, rule.rate_bps)
        total_tax += amount
        tax_details.append(
            {
                "rule_id": rule.id,
                "name": rule.name,
                "rate_bps": rule.rate_bps,
                "amount_cents": amount,
                "is_refundable": rule.is_refundable,
            }
        )

    fee_details = []
    total_fees = 0
    for rule in fee_rules:
        amount = calculate_fee_amount(rule, premium_cents)
        total_fees += amount
        fee_details.append(
            {
                "rule_id": rule.id,
                "name": rule.name,
                "fee_type": rule.fee_type,
                "amount_cents": amount,
                "is_refundable": rule.is_refundable,
            }
        )

    return {
        "premium_cents": premium_cents,
        "tax_details": tax_details,
        "total_tax_cents": total_tax,
        "fee_details": fee_details,
        "total_fees_cents": total_fees,
        "total_cents": premium_cents + total_tax + total_fees,
    }


def generate_policy_number():
    return f"POL-{uuid.uuid4().hex[:8].upper()}"


@transaction.atomic
def issue_policy(*, customer, broker_id, effective_date, premium_amount_cents, coverage_territory, created_by=None):
    """
    Create a new policy in DRAFT status for an approved broker.
    Calculates end date, tax/fee breakdown, and records a CREATED event.
    """
    broker = Broker.objects.get(id=broker_id)

    if broker.status != Broker.Status.APPROVED:
        raise PolicyError("Cannot issue policy through a non-approved broker")

    expiration_date = calculate_policy_expiration(effective_date)

    charges = compute_policy_charges(
        premium_cents=premium_amount_cents,
        jurisdiction=coverage_territory,
        effective_date=effective_date,
    )

    policy = Policy.objects.create(
        policy_number=generate_policy_number(),
        customer=customer,
        broker=broker,
        status=Policy.Status.DRAFT,
        effective_date=effective_date,
        expiration_date=expiration_date,
        premium_amount_cents=premium_amount_cents,
        coverage_territory=coverage_territory,
    )

    PolicyEvent.objects.create(
        policy=policy,
        event_type=PolicyEvent.EventType.CREATED,
        effective_at=timezone.now(),
        created_by=created_by,
        data={
            "charges": charges,
            "broker_commission_rate_bps": broker.commission_rate_bps,
        },
    )

    return policy, charges
