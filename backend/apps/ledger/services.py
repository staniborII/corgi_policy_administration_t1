from django.db import models, transaction
from django.utils import timezone

from apps.ledger.models import JournalEntry, JournalLine, LedgerAccount


class LedgerError(Exception):
    pass


class UnbalancedEntryError(LedgerError):
    pass


class DuplicateEntryError(LedgerError):
    pass


class ImmutableEntryError(LedgerError):
    pass


@transaction.atomic
def post_journal_entry(*, effective_at, lines, memo="", idempotency_key=None):
    """
    Post a balanced journal entry atomically.

    Args:
        effective_at: When the financial change applies (business date).
        lines: List of dicts: {account_code, amount_cents, entry_type}.
        memo: Description of the entry.
        idempotency_key: Optional key preventing duplicate posts.

    Returns:
        The created JournalEntry.

    Raises:
        DuplicateEntryError: If idempotency_key already exists.
        UnbalancedEntryError: If debits != credits.
    """
    if idempotency_key:
        existing = JournalEntry.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            raise DuplicateEntryError(f"Journal entry with idempotency key '{idempotency_key}' already exists")

    if not lines:
        raise LedgerError("Journal entry must have at least one line")

    total_debits = sum(line["amount_cents"] for line in lines if line["entry_type"] == JournalLine.EntryType.DEBIT)
    total_credits = sum(line["amount_cents"] for line in lines if line["entry_type"] == JournalLine.EntryType.CREDIT)

    if total_debits != total_credits:
        raise UnbalancedEntryError(f"Debits ({total_debits}) != Credits ({total_credits})")

    if total_debits == 0:
        raise LedgerError("Journal entry must have a non-zero amount")

    now = timezone.now()
    entry = JournalEntry.objects.create(
        effective_at=effective_at,
        memo=memo,
        idempotency_key=idempotency_key,
        status=JournalEntry.Status.POSTED,
        posted_at=now,
    )

    account_cache = {}
    for line_data in lines:
        code = line_data["account_code"]
        if code not in account_cache:
            try:
                account_cache[code] = LedgerAccount.objects.get(code=code, is_active=True)
            except LedgerAccount.DoesNotExist as exc:
                raise LedgerError(f"Active ledger account '{code}' not found") from exc

        JournalLine.objects.create(
            journal_entry=entry,
            account=account_cache[code],
            amount_cents=line_data["amount_cents"],
            entry_type=line_data["entry_type"],
        )

    return entry


@transaction.atomic
def reverse_journal_entry(*, entry_id, memo="", effective_at=None, idempotency_key=None):
    """
    Reverse a posted journal entry by creating a mirror entry with flipped debits/credits.
    The original entry is never modified.
    """
    original = JournalEntry.objects.select_for_update().get(id=entry_id)

    if original.status != JournalEntry.Status.POSTED:
        raise LedgerError("Can only reverse posted entries")

    if JournalEntry.objects.filter(reversal_of=original).exists():
        raise LedgerError("Entry has already been reversed")

    if idempotency_key:
        existing = JournalEntry.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            raise DuplicateEntryError(f"Journal entry with idempotency key '{idempotency_key}' already exists")

    now = timezone.now()
    reversal = JournalEntry.objects.create(
        effective_at=effective_at or now,
        memo=memo or f"Reversal of JE-{original.id}",
        idempotency_key=idempotency_key,
        status=JournalEntry.Status.POSTED,
        posted_at=now,
        reversal_of=original,
    )

    for line in original.lines.all():
        flipped = (
            JournalLine.EntryType.CREDIT
            if line.entry_type == JournalLine.EntryType.DEBIT
            else JournalLine.EntryType.DEBIT
        )
        JournalLine.objects.create(
            journal_entry=reversal,
            account=line.account,
            amount_cents=line.amount_cents,
            entry_type=flipped,
        )

    return reversal


def get_account_balance(account_code):
    """
    Compute the current balance for a ledger account from posted journal lines.
    Returns balance in cents, sign-correct per the account's normal balance.
    """
    account = LedgerAccount.objects.get(code=account_code)
    posted_lines = JournalLine.objects.filter(
        account=account,
        journal_entry__status=JournalEntry.Status.POSTED,
    )

    totals = posted_lines.values("entry_type").annotate(total=models.Sum("amount_cents"))
    debit_total = 0
    credit_total = 0
    for row in totals:
        if row["entry_type"] == JournalLine.EntryType.DEBIT:
            debit_total = row["total"] or 0
        else:
            credit_total = row["total"] or 0

    if account.normal_balance == LedgerAccount.NormalBalance.DEBIT:
        return debit_total - credit_total
    return credit_total - debit_total
