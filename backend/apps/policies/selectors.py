from datetime import date, datetime

from django.db import models
from django.utils import timezone

from apps.policies.models import FeeRule, Policy, TaxRule


def get_applicable_tax_rules(jurisdiction: str, as_of: date):
    """Return tax rules effective on `as_of` for the given jurisdiction."""
    return TaxRule.objects.filter(
        jurisdiction=jurisdiction,
        effective_from__lte=as_of,
    ).filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=as_of))


def get_applicable_fee_rules(jurisdiction: str, as_of: date):
    """Return fee rules effective on `as_of` for the given jurisdiction."""
    return FeeRule.objects.filter(
        jurisdiction=jurisdiction,
        effective_from__lte=as_of,
    ).filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=as_of))


def get_policy_as_of(policy_id: int, as_of: datetime | None = None):
    """
    Reconstruct the policy state as of a given datetime.
    Returns a dict with the policy snapshot and applied endorsements up to that point.
    """
    policy = Policy.objects.select_related("customer", "broker__user").get(id=policy_id)

    if as_of is None:
        as_of = timezone.now()

    from apps.endorsements.models import Endorsement

    applied_endorsements = (
        Endorsement.objects.filter(
            policy=policy,
            status=Endorsement.Status.APPLIED,
            recorded_at__lte=as_of,
        )
        .exclude(
            id__in=Endorsement.objects.filter(
                policy=policy,
                status=Endorsement.Status.REVERSED,
                updated_at__lte=as_of,
            ).values_list("id", flat=True)
        )
        .order_by("effective_date", "recorded_at")
    )

    reversed_ids = set(
        Endorsement.objects.filter(
            policy=policy,
            status=Endorsement.Status.REVERSED,
            updated_at__lte=as_of,
        ).values_list("id", flat=True)
    )

    base_premium = policy.premium_amount_cents
    for end in Endorsement.objects.filter(
        policy=policy,
        status__in=[Endorsement.Status.APPLIED, Endorsement.Status.REVERSED],
    ):
        base_premium -= end.annual_premium_delta_cents

    effective_premium = base_premium
    endorsement_list = []
    for end in applied_endorsements:
        if end.id not in reversed_ids:
            effective_premium += end.annual_premium_delta_cents
            endorsement_list.append(
                {
                    "id": end.id,
                    "endorsement_number": end.endorsement_number,
                    "type": end.endorsement_type,
                    "effective_date": str(end.effective_date),
                    "annual_premium_delta_cents": end.annual_premium_delta_cents,
                    "premium_change_cents": end.premium_change_cents,
                    "description": end.description,
                }
            )

    events = list(
        policy.events.filter(recorded_at__lte=as_of)
        .order_by("effective_at", "recorded_at")
        .values("event_type", "effective_at", "recorded_at", "data")
    )

    return {
        "policy_number": policy.policy_number,
        "status": policy.status,
        "effective_date": str(policy.effective_date),
        "expiration_date": str(policy.expiration_date),
        "coverage_territory": policy.coverage_territory,
        "base_premium_cents": base_premium,
        "effective_premium_cents": effective_premium,
        "endorsements": endorsement_list,
        "events": events,
        "as_of": as_of.isoformat(),
        "customer": policy.customer.username,
        "broker": policy.broker.company_name,
    }
