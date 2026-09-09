from django.db import models


class ReconciliationRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"

    run_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Recon {self.run_date} ({self.get_status_display()})"


class ReconciliationBreak(models.Model):
    class BreakType(models.TextChoices):
        MISSING_IN_LEDGER = "MISSING_IN_LEDGER"
        MISSING_IN_PROVIDER = "MISSING_IN_PROVIDER"
        AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
        STATUS_MISMATCH = "STATUS_MISMATCH"
        DUPLICATE_MATCH = "DUPLICATE_MATCH"
        STALE_UNRESOLVED = "STALE_UNRESOLVED"

    class Status(models.TextChoices):
        OPEN = "OPEN"
        ACKNOWLEDGED = "ACKNOWLEDGED"
        RESOLVED = "RESOLVED"

    run = models.ForeignKey(ReconciliationRun, on_delete=models.PROTECT, related_name="breaks")
    break_type = models.CharField(max_length=30, choices=BreakType.choices)
    description = models.TextField()
    source = models.CharField(max_length=30, default="STRIPE")
    external_reference = models.CharField(max_length=255, blank=True)
    local_reference = models.CharField(max_length=255, blank=True)
    expected_amount_cents = models.IntegerField(null=True, blank=True)
    actual_amount_cents = models.IntegerField(null=True, blank=True)
    first_seen_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_breaks"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Break: {self.get_break_type_display()} — {self.description[:50]}"


class BrokerStatement(models.Model):
    broker = models.ForeignKey("brokers.Broker", on_delete=models.PROTECT, related_name="statements")
    period_start = models.DateField()
    period_end = models.DateField()
    total_premium_cents = models.PositiveIntegerField(default=0)
    total_commission_cents = models.PositiveIntegerField(default=0)
    total_clawback_cents = models.IntegerField(default=0)
    net_due_cents = models.IntegerField(default=0)
    statement_data = models.JSONField(default=dict, blank=True)
    is_closed = models.BooleanField(default=False)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("broker", "period_start", "period_end")]

    def __str__(self):
        return f"Statement for {self.broker} ({self.period_start} — {self.period_end})"
