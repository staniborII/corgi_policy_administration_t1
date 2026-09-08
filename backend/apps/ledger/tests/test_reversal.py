import pytest
from django.utils import timezone

from apps.ledger.models import JournalEntry, LedgerAccount
from apps.ledger.services import (
    LedgerError,
    get_account_balance,
    post_journal_entry,
    reverse_journal_entry,
)


@pytest.fixture
def seed_accounts(db):
    from apps.ledger.management.commands.seed_chart_of_accounts import CHART_OF_ACCOUNTS

    accounts = {}
    for code, name, account_type, normal_balance in CHART_OF_ACCOUNTS:
        accounts[code] = LedgerAccount.objects.create(
            code=code, name=name, account_type=account_type, normal_balance=normal_balance
        )
    return accounts


@pytest.fixture
def posted_entry(seed_accounts):
    return post_journal_entry(
        effective_at=timezone.now(),
        memo="Original charge $300",
        lines=[
            {"account_code": "1100", "amount_cents": 30000, "entry_type": "DEBIT"},
            {"account_code": "4000", "amount_cents": 30000, "entry_type": "CREDIT"},
        ],
    )


class TestReverseJournalEntry:
    def test_reversal_creates_mirror_entry(self, posted_entry):
        reversal = reverse_journal_entry(entry_id=posted_entry.id)
        assert reversal.status == JournalEntry.Status.POSTED
        assert reversal.reversal_of_id == posted_entry.id
        assert reversal.lines.count() == posted_entry.lines.count()

        for orig_line, rev_line in zip(posted_entry.lines.order_by("id"), reversal.lines.order_by("id"), strict=True):
            assert rev_line.amount_cents == orig_line.amount_cents
            assert rev_line.entry_type != orig_line.entry_type
            assert rev_line.account_id == orig_line.account_id

    def test_original_preserved_after_reversal(self, posted_entry):
        original_id = posted_entry.id
        original_memo = posted_entry.memo
        reverse_journal_entry(entry_id=posted_entry.id)

        posted_entry.refresh_from_db()
        assert posted_entry.id == original_id
        assert posted_entry.memo == original_memo
        assert posted_entry.status == JournalEntry.Status.POSTED

    def test_reversal_zeroes_balance(self, posted_entry, seed_accounts):
        assert get_account_balance("1100") == 30000
        reverse_journal_entry(entry_id=posted_entry.id)
        assert get_account_balance("1100") == 0
        assert get_account_balance("4000") == 0

    def test_cannot_reverse_draft_entry(self, seed_accounts):
        entry = JournalEntry.objects.create(effective_at=timezone.now(), status=JournalEntry.Status.DRAFT)
        with pytest.raises(LedgerError, match="only reverse posted"):
            reverse_journal_entry(entry_id=entry.id)

    def test_cannot_reverse_twice(self, posted_entry):
        reverse_journal_entry(entry_id=posted_entry.id)
        with pytest.raises(LedgerError, match="already been reversed"):
            reverse_journal_entry(entry_id=posted_entry.id)

    def test_correction_flow(self, posted_entry, seed_accounts):
        """Original $300, reverse, re-book at $350 — all three entries visible."""
        reverse_journal_entry(entry_id=posted_entry.id, memo="Reversal of incorrect charge")

        post_journal_entry(
            effective_at=timezone.now(),
            memo="Correct charge $350",
            lines=[
                {"account_code": "1100", "amount_cents": 35000, "entry_type": "DEBIT"},
                {"account_code": "4000", "amount_cents": 35000, "entry_type": "CREDIT"},
            ],
        )

        all_entries = JournalEntry.objects.filter(status=JournalEntry.Status.POSTED)
        assert all_entries.count() == 3
        assert get_account_balance("1100") == 35000
        assert get_account_balance("4000") == 35000
