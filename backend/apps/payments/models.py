from django.db import models


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        PROCESSING = "PROCESSING"
        SUCCEEDED = "SUCCEEDED"
        FAILED = "FAILED"

    policy = models.ForeignKey("policies.Policy", on_delete=models.PROTECT, related_name="payments")
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True)
    charges_snapshot = models.JSONField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True, null=True, blank=True)
    effective_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment {self.id} — {self.amount_cents}¢ ({self.get_status_display()})"


class Refund(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED"
        PENDING = "PENDING"
        SUCCEEDED = "SUCCEEDED"
        FAILED = "FAILED"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    stripe_refund_id = models.CharField(max_length=255, blank=True)
    reason = models.TextField(blank=True)
    charges_snapshot = models.JSONField(null=True, blank=True)
    effective_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Refund {self.id} — {self.amount_cents}¢ ({self.get_status_display()})"
