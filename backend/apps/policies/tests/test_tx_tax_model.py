"""
Texas surplus-lines tax and fee model tests.

Rates (effective 2024-01-01, per SLTX / Texas Comptroller):
  - Surplus Lines Premium Tax: 4.85% (485 bps)
  - SLTX Stamping Fee: 0.04% (4 bps)

Both are refundable on cancellation via reversal.
"""

from datetime import date

import pytest

from apps.policies.models import FeeRule, TaxRule
from apps.policies.selectors import get_applicable_tax_rules
from apps.policies.services import calculate_rate_amount, compute_policy_charges


@pytest.fixture
def tx_rules(db):
    tax = TaxRule.objects.create(
        jurisdiction="TX",
        name="TX Surplus Lines Premium Tax",
        component_type="TAX",
        rate_bps=485,
        effective_from=date(2024, 1, 1),
        is_refundable=True,
    )
    fee = FeeRule.objects.create(
        jurisdiction="TX",
        name="TX SLTX Stamping Fee",
        fee_type="RATE",
        rate_bps=4,
        effective_from=date(2024, 1, 1),
        is_refundable=True,
    )
    return tax, fee


class TestCorrectCalculation:
    def test_exact_cents_1000_premium(self, tx_rules):
        """$1,000.00 premium -> tax $48.50, fee $0.40, total $1,048.90."""
        charges = compute_policy_charges(
            premium_cents=100000,
            jurisdiction="TX",
            effective_date=date(2025, 6, 1),
        )
        assert charges["premium_cents"] == 100000
        assert charges["total_tax_cents"] == 4850
        assert charges["total_fees_cents"] == 40
        assert charges["total_cents"] == 104890

    def test_exact_cents_5000_premium(self, tx_rules):
        """$5,000.00 premium -> tax $242.50, fee $2.00, total $5,244.50."""
        charges = compute_policy_charges(
            premium_cents=500000,
            jurisdiction="TX",
            effective_date=date(2025, 6, 1),
        )
        assert charges["total_tax_cents"] == 24250
        assert charges["total_fees_cents"] == 200
        assert charges["total_cents"] == 524450

    def test_small_premium(self, tx_rules):
        """$100.00 premium -> tax $4.85, fee $0.04, total $104.89."""
        charges = compute_policy_charges(
            premium_cents=10000,
            jurisdiction="TX",
            effective_date=date(2025, 6, 1),
        )
        assert charges["total_tax_cents"] == 485
        assert charges["total_fees_cents"] == 4
        assert charges["total_cents"] == 10489


class TestPremiumSeparation:
    def test_tax_does_not_change_premium(self, tx_rules):
        charges = compute_policy_charges(
            premium_cents=100000,
            jurisdiction="TX",
            effective_date=date(2025, 6, 1),
        )
        assert charges["premium_cents"] == 100000

    def test_components_are_additive(self, tx_rules):
        charges = compute_policy_charges(
            premium_cents=100000,
            jurisdiction="TX",
            effective_date=date(2025, 6, 1),
        )
        component_total = charges["premium_cents"] + charges["total_tax_cents"] + charges["total_fees_cents"]
        assert charges["total_cents"] == component_total

    def test_refundable_flags_preserved(self, tx_rules):
        charges = compute_policy_charges(
            premium_cents=100000,
            jurisdiction="TX",
            effective_date=date(2025, 6, 1),
        )
        for detail in charges["tax_details"]:
            assert detail["is_refundable"] is True
        for detail in charges["fee_details"]:
            assert detail["is_refundable"] is True


class TestEffectiveDateLookup:
    def test_selects_rule_by_effective_date(self, db):
        TaxRule.objects.create(
            jurisdiction="TX",
            name="TX Tax v1",
            component_type="TAX",
            rate_bps=400,
            effective_from=date(2020, 1, 1),
            effective_to=date(2023, 12, 31),
            is_refundable=True,
        )
        TaxRule.objects.create(
            jurisdiction="TX",
            name="TX Tax v2",
            component_type="TAX",
            rate_bps=485,
            effective_from=date(2024, 1, 1),
            is_refundable=True,
        )
        old = get_applicable_tax_rules("TX", as_of=date(2023, 6, 1))
        assert old.count() == 1
        assert old.first().rate_bps == 400

        new = get_applicable_tax_rules("TX", as_of=date(2025, 6, 1))
        assert new.count() == 1
        assert new.first().rate_bps == 485

    def test_boundary_date_exact_transition(self, db):
        """Dec 31 picks old rule, Jan 1 picks new rule."""
        TaxRule.objects.create(
            jurisdiction="TX",
            name="TX Tax old",
            component_type="TAX",
            rate_bps=400,
            effective_from=date(2020, 1, 1),
            effective_to=date(2023, 12, 31),
            is_refundable=True,
        )
        TaxRule.objects.create(
            jurisdiction="TX",
            name="TX Tax new",
            component_type="TAX",
            rate_bps=485,
            effective_from=date(2024, 1, 1),
            is_refundable=True,
        )
        last_day_old = get_applicable_tax_rules("TX", as_of=date(2023, 12, 31))
        assert last_day_old.count() == 1
        assert last_day_old.first().rate_bps == 400

        first_day_new = get_applicable_tax_rules("TX", as_of=date(2024, 1, 1))
        assert first_day_new.count() == 1
        assert first_day_new.first().rate_bps == 485


class TestDeterministicRounding:
    def test_fractional_cent_rounds_half_up(self, db):
        """$123.45 premium at 485 bps -> 123.45 * 0.0485 = 5.987325 -> rounds to 599 cents."""
        TaxRule.objects.create(
            jurisdiction="TX",
            name="TX Tax",
            component_type="TAX",
            rate_bps=485,
            effective_from=date(2024, 1, 1),
            is_refundable=True,
        )
        result = calculate_rate_amount(12345, 485)
        assert result == 599

    def test_exact_half_cent_rounds_up(self, db):
        """Verify half-up: 10000 * 5 / 10000 = 5.0 (exact) -> 5."""
        assert calculate_rate_amount(10000, 5) == 5

    def test_just_below_half_rounds_down(self, db):
        """4999/10000 = 0.4999 -> rounds to 0."""
        assert calculate_rate_amount(1, 4999) == 0

    def test_just_at_half_rounds_up(self, db):
        """5000/10000 = 0.5 -> rounds up to 1."""
        assert calculate_rate_amount(1, 5000) == 1

    def test_rounding_consistency_with_compute(self, db):
        """compute_policy_charges uses the same Decimal rounding."""
        TaxRule.objects.create(
            jurisdiction="TX",
            name="TX Tax",
            component_type="TAX",
            rate_bps=485,
            effective_from=date(2024, 1, 1),
            is_refundable=True,
        )
        FeeRule.objects.create(
            jurisdiction="TX",
            name="TX Fee",
            fee_type="RATE",
            rate_bps=4,
            effective_from=date(2024, 1, 1),
            is_refundable=True,
        )
        charges = compute_policy_charges(
            premium_cents=12345,
            jurisdiction="TX",
            effective_date=date(2025, 1, 1),
        )
        assert charges["total_tax_cents"] == 599
        assert charges["total_fees_cents"] == 5
        assert charges["total_cents"] == 12345 + 599 + 5


class TestHistoricalReproducibility:
    def test_adding_later_rule_does_not_change_historical(self, db):
        TaxRule.objects.create(
            jurisdiction="TX",
            name="TX Tax 2024",
            component_type="TAX",
            rate_bps=485,
            effective_from=date(2024, 1, 1),
            is_refundable=True,
        )
        FeeRule.objects.create(
            jurisdiction="TX",
            name="TX Fee 2024",
            fee_type="RATE",
            rate_bps=4,
            effective_from=date(2024, 1, 1),
            is_refundable=True,
        )
        original = compute_policy_charges(
            premium_cents=100000,
            jurisdiction="TX",
            effective_date=date(2024, 6, 1),
        )

        TaxRule.objects.create(
            jurisdiction="TX",
            name="TX Tax 2027",
            component_type="TAX",
            rate_bps=550,
            effective_from=date(2027, 1, 1),
            is_refundable=True,
        )

        replayed = compute_policy_charges(
            premium_cents=100000,
            jurisdiction="TX",
            effective_date=date(2024, 6, 1),
        )
        assert replayed["total_tax_cents"] == original["total_tax_cents"]
        assert replayed["total_fees_cents"] == original["total_fees_cents"]
        assert replayed["total_cents"] == original["total_cents"]
