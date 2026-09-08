from datetime import date

from django.db import models

from apps.policies.models import FeeRule, TaxRule


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
