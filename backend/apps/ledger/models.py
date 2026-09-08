from django.db import models


class LedgerAccount(models.Model):
    class AccountType(models.TextChoices):
        ASSET = "ASSET"
        LIABILITY = "LIABILITY"
        EQUITY = "EQUITY"
        REVENUE = "REVENUE"
        EXPENSE = "EXPENSE"

    class NormalBalance(models.TextChoices):
        DEBIT = "DEBIT"
        CREDIT = "CREDIT"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    normal_balance = models.CharField(max_length=10, choices=NormalBalance.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} — {self.name}"


class JournalEntry(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        POSTED = "POSTED"

    effective_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    memo = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    reversal_of = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "journal entries"
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"JE-{self.id} ({self.get_status_display()}) {self.memo[:50]}"


class JournalLine(models.Model):
    class EntryType(models.TextChoices):
        DEBIT = "DEBIT"
        CREDIT = "CREDIT"

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="lines")
    amount_cents = models.PositiveIntegerField()
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.get_entry_type_display()} {self.account.code} {self.amount_cents}¢"
