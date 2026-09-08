from datetime import date

import pytest

from apps.policies.models import FeeRule, TaxRule
from apps.policies.selectors import get_applicable_fee_rules, get_applicable_tax_rules


@pytest.mark.django_db
class TestTaxRuleSelection:
    def test_returns_current_rule(self):
        TaxRule.objects.create(
            jurisdiction="CA",
            name="CA Premium Tax",
            component_type="TAX",
            rate_bps=350,
            effective_from=date(2024, 1, 1),
        )
        rules = get_applicable_tax_rules("CA", as_of=date(2025, 6, 1))
        assert rules.count() == 1
        assert rules.first().rate_bps == 350

    def test_excludes_expired_rule(self):
        TaxRule.objects.create(
            jurisdiction="CA",
            name="Old CA Tax",
            component_type="TAX",
            rate_bps=300,
            effective_from=date(2020, 1, 1),
            effective_to=date(2023, 12, 31),
        )
        rules = get_applicable_tax_rules("CA", as_of=date(2025, 1, 1))
        assert rules.count() == 0

    def test_excludes_future_rule(self):
        TaxRule.objects.create(
            jurisdiction="CA",
            name="Future CA Tax",
            component_type="TAX",
            rate_bps=400,
            effective_from=date(2030, 1, 1),
        )
        rules = get_applicable_tax_rules("CA", as_of=date(2025, 1, 1))
        assert rules.count() == 0

    def test_historical_rule_selection(self):
        """Rate change must not retroactively change historical calculations."""
        TaxRule.objects.create(
            jurisdiction="NY",
            name="NY Tax v1",
            component_type="TAX",
            rate_bps=200,
            effective_from=date(2020, 1, 1),
            effective_to=date(2024, 12, 31),
        )
        TaxRule.objects.create(
            jurisdiction="NY",
            name="NY Tax v2",
            component_type="TAX",
            rate_bps=250,
            effective_from=date(2025, 1, 1),
        )
        old_rules = get_applicable_tax_rules("NY", as_of=date(2023, 6, 1))
        assert old_rules.count() == 1
        assert old_rules.first().rate_bps == 200

        new_rules = get_applicable_tax_rules("NY", as_of=date(2025, 6, 1))
        assert new_rules.count() == 1
        assert new_rules.first().rate_bps == 250

    def test_filters_by_jurisdiction(self):
        TaxRule.objects.create(
            jurisdiction="CA",
            name="CA Tax",
            component_type="TAX",
            rate_bps=350,
            effective_from=date(2024, 1, 1),
        )
        TaxRule.objects.create(
            jurisdiction="NY",
            name="NY Tax",
            component_type="TAX",
            rate_bps=200,
            effective_from=date(2024, 1, 1),
        )
        ca_rules = get_applicable_tax_rules("CA", as_of=date(2025, 1, 1))
        assert ca_rules.count() == 1
        assert ca_rules.first().jurisdiction == "CA"

    def test_open_ended_rule(self):
        """Rule with no effective_to applies indefinitely."""
        TaxRule.objects.create(
            jurisdiction="TX",
            name="TX Tax",
            component_type="TAX",
            rate_bps=180,
            effective_from=date(2020, 1, 1),
        )
        rules = get_applicable_tax_rules("TX", as_of=date(2099, 12, 31))
        assert rules.count() == 1


@pytest.mark.django_db
class TestFeeRuleSelection:
    def test_flat_fee_returned(self):
        FeeRule.objects.create(
            jurisdiction="CA",
            name="CA Stamping Fee",
            fee_type="FLAT",
            amount_cents=2500,
            effective_from=date(2024, 1, 1),
        )
        rules = get_applicable_fee_rules("CA", as_of=date(2025, 1, 1))
        assert rules.count() == 1
        assert rules.first().amount_cents == 2500

    def test_rate_fee_returned(self):
        FeeRule.objects.create(
            jurisdiction="CA",
            name="CA Fire Fee",
            fee_type="RATE",
            rate_bps=50,
            effective_from=date(2024, 1, 1),
        )
        rules = get_applicable_fee_rules("CA", as_of=date(2025, 1, 1))
        assert rules.count() == 1
        assert rules.first().rate_bps == 50

    def test_excludes_expired_fee(self):
        FeeRule.objects.create(
            jurisdiction="CA",
            name="Old Fee",
            fee_type="FLAT",
            amount_cents=1000,
            effective_from=date(2020, 1, 1),
            effective_to=date(2023, 12, 31),
        )
        rules = get_applicable_fee_rules("CA", as_of=date(2025, 1, 1))
        assert rules.count() == 0
