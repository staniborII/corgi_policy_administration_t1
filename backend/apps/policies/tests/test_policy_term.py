from datetime import date

from apps.policies.services import calculate_policy_expiration


class TestPolicyExpiration:
    def test_normal_date(self):
        assert calculate_policy_expiration(date(2025, 6, 15)) == date(2026, 6, 15)

    def test_jan_1(self):
        assert calculate_policy_expiration(date(2025, 1, 1)) == date(2026, 1, 1)

    def test_dec_31(self):
        assert calculate_policy_expiration(date(2025, 12, 31)) == date(2026, 12, 31)

    def test_leap_year_feb_29_to_non_leap(self):
        """Feb 29 in leap year -> Feb 28 in non-leap year."""
        assert calculate_policy_expiration(date(2024, 2, 29)) == date(2025, 2, 28)

    def test_leap_year_feb_29_to_leap(self):
        """Feb 29 2024 -> Feb 28 2025 (2025 is not a leap year)."""
        assert calculate_policy_expiration(date(2024, 2, 29)) == date(2025, 2, 28)

    def test_non_leap_feb_28(self):
        """Feb 28 in non-leap year -> Feb 28 in next year."""
        assert calculate_policy_expiration(date(2025, 2, 28)) == date(2026, 2, 28)

    def test_feb_28_to_leap_year(self):
        """Feb 28 2023 -> Feb 28 2024 (stays Feb 28, not Feb 29)."""
        assert calculate_policy_expiration(date(2023, 2, 28)) == date(2024, 2, 28)

    def test_calendar_anniversary_not_365_days(self):
        """Verify we use calendar anniversary, not +365 days (which would land on wrong date in leap years)."""
        effective = date(2023, 3, 1)
        expiration = calculate_policy_expiration(effective)
        assert expiration == date(2024, 3, 1)
        assert expiration.month == effective.month
        assert expiration.day == effective.day
