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


def prorate_amount(annual_amount_cents: int, remaining_days: int, total_days: int) -> int:
    if total_days <= 0:
        return 0
    result = Decimal(annual_amount_cents) * Decimal(remaining_days) / Decimal(total_days)
    return int(result.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def compute_cancellation_refund(*, policy, cancellation_date):
    """
    Calculate all refundable components for a pro-rata cancellation.
    Returns a dict with unearned premium, refundable taxes/fees, commission clawback, and total.
    """
    total_days = (policy.expiration_date - policy.effective_date).days
    remaining_days = (policy.expiration_date - cancellation_date).days

    if remaining_days < 0:
        remaining_days = 0
    if remaining_days > total_days:
        raise PolicyError("Cancellation date is before policy effective date")

    unearned_premium = prorate_amount(policy.premium_amount_cents, remaining_days, total_days)

    tax_rules = get_applicable_tax_rules(policy.coverage_territory, as_of=policy.effective_date)
    fee_rules = get_applicable_fee_rules(policy.coverage_territory, as_of=policy.effective_date)

    refundable_tax_details = []
    total_refundable_tax = 0
    for rule in tax_rules:
        if rule.is_refundable:
            amount = calculate_rate_amount(unearned_premium, rule.rate_bps)
            total_refundable_tax += amount
            refundable_tax_details.append(
                {"rule_id": rule.id, "name": rule.name, "rate_bps": rule.rate_bps, "amount_cents": amount}
            )

    refundable_fee_details = []
    total_refundable_fees = 0
    for rule in fee_rules:
        if rule.is_refundable:
            amount = calculate_fee_amount(rule, unearned_premium)
            total_refundable_fees += amount
            refundable_fee_details.append({"rule_id": rule.id, "name": rule.name, "amount_cents": amount})

    total_refund = unearned_premium + total_refundable_tax + total_refundable_fees

    commission_clawback = calculate_rate_amount(unearned_premium, policy.broker.commission_rate_bps)

    return {
        "cancellation_date": str(cancellation_date),
        "total_days": total_days,
        "remaining_days": remaining_days,
        "unearned_premium_cents": unearned_premium,
        "refundable_tax_details": refundable_tax_details,
        "total_refundable_tax_cents": total_refundable_tax,
        "refundable_fee_details": refundable_fee_details,
        "total_refundable_fees_cents": total_refundable_fees,
        "total_refund_cents": total_refund,
        "commission_clawback_cents": commission_clawback,
    }


@transaction.atomic
def cancel_policy(*, policy_id, cancelled_by, cancellation_date=None):
    """
    Cancel an active policy with pro-rata refund.
    Creates a Stripe refund (PENDING until provider confirms).
    Ledger entries are NOT posted here — they wait for refund confirmation.
    """
    from apps.integrations.stripe.client import create_stripe_refund
    from apps.payments.models import Payment, Refund

    policy = Policy.objects.select_for_update().get(id=policy_id)

    if policy.status != Policy.Status.ACTIVE:
        raise PolicyError("Can only cancel an active policy")

    if cancellation_date is None:
        cancellation_date = date.today()

    refund_data = compute_cancellation_refund(policy=policy, cancellation_date=cancellation_date)
    total_refund = refund_data["total_refund_cents"]
    now = timezone.now()

    refund = None
    if total_refund > 0:
        payment = Payment.objects.filter(policy=policy, status=Payment.Status.SUCCEEDED).order_by("created_at").first()
        if not payment:
            raise PolicyError("No successful payment found to refund")

        result = create_stripe_refund(
            payment_intent_id=payment.stripe_payment_intent_id,
            amount_cents=total_refund,
            metadata={
                "policy_id": str(policy.id),
                "policy_number": policy.policy_number,
                "idempotency_key": f"cancel-refund-{policy.id}",
            },
        )

        refund = Refund.objects.create(
            payment=payment,
            amount_cents=total_refund,
            status=Refund.Status.PENDING,
            stripe_refund_id=result["refund_id"],
            reason=f"Pro-rata cancellation as of {cancellation_date}",
            charges_snapshot=refund_data,
            effective_at=now,
        )

    policy.status = Policy.Status.CANCELLED
    policy.save(update_fields=["status", "updated_at"])

    PolicyEvent.objects.create(
        policy=policy,
        event_type=PolicyEvent.EventType.CANCELLED,
        effective_at=now,
        created_by=cancelled_by,
        data={
            **refund_data,
            "refund_id": refund.id if refund else None,
        },
    )

    return {"policy": policy, "refund": refund, **refund_data}


@transaction.atomic
def decline_policy(*, policy_id, declined_by):
    """
    Customer declines a policy before payment.
    Only DRAFT or PENDING_PAYMENT policies can be declined.
    No refund is needed since no payment has been made.
    """
    policy = Policy.objects.select_for_update().get(id=policy_id)

    if policy.status not in (Policy.Status.DRAFT, Policy.Status.PENDING_PAYMENT):
        raise PolicyError("Can only decline a policy that has not been paid")

    if policy.customer_id != declined_by.id:
        raise PolicyError("Only the policy customer can decline")

    now = timezone.now()
    policy.status = Policy.Status.CANCELLED
    policy.save(update_fields=["status", "updated_at"])

    PolicyEvent.objects.create(
        policy=policy,
        event_type=PolicyEvent.EventType.CANCELLED,
        effective_at=now,
        created_by=declined_by,
        data={"reason": "Declined by customer before payment"},
    )

    return policy
