import pytest
from django.utils import timezone

from apps.ledger.models import JournalEntry, LedgerAccount
from apps.ledger.services import (
    DuplicateEntryError,
    LedgerError,
    UnbalancedEntryError,
    get_account_balance,
    post_journal_entry,
)


@pytest.fixture
def seed_accounts(db):
    """Seed the standard chart of accounts for testing."""
    from apps.ledger.management.commands.seed_chart_of_accounts import CHART_OF_ACCOUNTS

    accounts = {}
    for code, name, account_type, normal_balance in CHART_OF_ACCOUNTS:
        accounts[code] = LedgerAccount.objects.create(
            code=code, name=name, account_type=account_type, normal_balance=normal_balance
        )
    return accounts


class TestPostJournalEntry:
    def test_balanced_entry_accepted(self, seed_accounts):
        now = timezone.now()
        entry = post_journal_entry(
            effective_at=now,
            memo="Premium collection",
            lines=[
                {"account_code": "1000", "amount_cents": 10000, "entry_type": "DEBIT"},
                {"account_code": "1100", "amount_cents": 10000, "entry_type": "CREDIT"},
            ],
        )
        assert entry.status == JournalEntry.Status.POSTED
        assert entry.posted_at is not None
        assert entry.lines.count() == 2

    def test_unbalanced_entry_rejected(self, seed_accounts):
        now = timezone.now()
        with pytest.raises(UnbalancedEntryError, match="Debits .* != Credits"):
            post_journal_entry(
                effective_at=now,
                lines=[
                    {"account_code": "1000", "amount_cents": 10000, "entry_type": "DEBIT"},
                    {"account_code": "1100", "amount_cents": 9000, "entry_type": "CREDIT"},
                ],
            )

    def test_empty_lines_rejected(self, seed_accounts):
        with pytest.raises(LedgerError, match="at least one line"):
            post_journal_entry(effective_at=timezone.now(), lines=[])

    def test_zero_amount_entry_rejected(self, seed_accounts):
        with pytest.raises(LedgerError, match="non-zero amount"):
            post_journal_entry(
                effective_at=timezone.now(),
                lines=[
                    {"account_code": "1000", "amount_cents": 0, "entry_type": "DEBIT"},
                    {"account_code": "1100", "amount_cents": 0, "entry_type": "CREDIT"},
                ],
            )

    def test_money_stored_as_integer_cents(self, seed_accounts):
        entry = post_journal_entry(
            effective_at=timezone.now(),
            memo="$120.50 premium",
            lines=[
                {"account_code": "1000", "amount_cents": 12050, "entry_type": "DEBIT"},
                {"account_code": "4000", "amount_cents": 12050, "entry_type": "CREDIT"},
            ],
        )
        line = entry.lines.first()
        assert isinstance(line.amount_cents, int)
        assert line.amount_cents == 12050

    def test_multi_line_entry(self, seed_accounts):
        entry = post_journal_entry(
            effective_at=timezone.now(),
            memo="Premium + tax + fee",
            lines=[
                {"account_code": "1000", "amount_cents": 11000, "entry_type": "DEBIT"},
                {"account_code": "4000", "amount_cents": 10000, "entry_type": "CREDIT"},
                {"account_code": "2100", "amount_cents": 500, "entry_type": "CREDIT"},
                {"account_code": "4100", "amount_cents": 500, "entry_type": "CREDIT"},
            ],
        )
        assert entry.lines.count() == 4
        debits = sum(line.amount_cents for line in entry.lines.filter(entry_type="DEBIT"))
        credits = sum(line.amount_cents for line in entry.lines.filter(entry_type="CREDIT"))
        assert debits == credits == 11000

    def test_idempotency_key_prevents_duplicate(self, seed_accounts):
        now = timezone.now()
        lines = [
            {"account_code": "1000", "amount_cents": 5000, "entry_type": "DEBIT"},
            {"account_code": "4000", "amount_cents": 5000, "entry_type": "CREDIT"},
        ]
        post_journal_entry(effective_at=now, lines=lines, idempotency_key="payment-123")

        with pytest.raises(DuplicateEntryError):
            post_journal_entry(effective_at=now, lines=lines, idempotency_key="payment-123")

    def test_inactive_account_rejected(self, seed_accounts):
        account = seed_accounts["1000"]
        account.is_active = False
        account.save()

        with pytest.raises(LedgerError, match="not found"):
            post_journal_entry(
                effective_at=timezone.now(),
                lines=[
                    {"account_code": "1000", "amount_cents": 100, "entry_type": "DEBIT"},
                    {"account_code": "4000", "amount_cents": 100, "entry_type": "CREDIT"},
                ],
            )

    def test_nonexistent_account_rejected(self, seed_accounts):
        with pytest.raises(LedgerError, match="not found"):
            post_journal_entry(
                effective_at=timezone.now(),
                lines=[
                    {"account_code": "9999", "amount_cents": 100, "entry_type": "DEBIT"},
                    {"account_code": "4000", "amount_cents": 100, "entry_type": "CREDIT"},
                ],
            )


class TestAccountBalance:
    def test_balance_after_single_entry(self, seed_accounts):
        post_journal_entry(
            effective_at=timezone.now(),
            lines=[
                {"account_code": "1000", "amount_cents": 10000, "entry_type": "DEBIT"},
                {"account_code": "4000", "amount_cents": 10000, "entry_type": "CREDIT"},
            ],
        )
        assert get_account_balance("1000") == 10000
        assert get_account_balance("4000") == 10000

    def test_balance_after_multiple_entries(self, seed_accounts):
        now = timezone.now()
        post_journal_entry(
            effective_at=now,
            lines=[
                {"account_code": "1000", "amount_cents": 10000, "entry_type": "DEBIT"},
                {"account_code": "4000", "amount_cents": 10000, "entry_type": "CREDIT"},
            ],
        )
        post_journal_entry(
            effective_at=now,
            lines=[
                {"account_code": "1000", "amount_cents": 5000, "entry_type": "DEBIT"},
                {"account_code": "4000", "amount_cents": 5000, "entry_type": "CREDIT"},
            ],
        )
        assert get_account_balance("1000") == 15000
        assert get_account_balance("4000") == 15000

    def test_zero_balance_initially(self, seed_accounts):
        assert get_account_balance("1000") == 0
