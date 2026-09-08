from datetime import date


def calculate_policy_expiration(effective_date: date) -> date:
    """
    Calculate expiration using calendar anniversary (same month/day, next year).
    Feb 29 effective date in a leap year -> Feb 28 in a non-leap year.
    """
    try:
        return effective_date.replace(year=effective_date.year + 1)
    except ValueError:
        return date(effective_date.year + 1, 2, 28)
