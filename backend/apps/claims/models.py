import uuid

from django.conf import settings
from django.db import models


class Claim(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN"
        UNDER_REVIEW = "UNDER_REVIEW"
        RESERVED = "RESERVED"
        PAYMENT_PENDING = "PAYMENT_PENDING"
        PARTIALLY_PAID = "PARTIALLY_PAID"
        PAID = "PAID"
        CLOSED = "CLOSED"

    policy = models.ForeignKey("policies.Policy", on_delete=models.PROTECT, related_name="claims")
    claim_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    date_of_loss = models.DateField()
    description = models.TextField()
    estimated_amount_cents = models.PositiveIntegerField(null=True, blank=True)
    reported_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Claim {self.claim_number} ({self.get_status_display()})"


class ReserveEvent(models.Model):
    class ReserveType(models.TextChoices):
        INITIAL = "INITIAL"
        ADJUSTMENT = "ADJUSTMENT"
        RELEASE = "RELEASE"

    claim = models.ForeignKey(Claim, on_delete=models.PROTECT, related_name="reserve_events")
    amount_cents = models.IntegerField(help_text="Positive = increase, negative = decrease")
    reserve_type = models.CharField(max_length=20, choices=ReserveType.choices)
    effective_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    memo = models.TextField(blank=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"Reserve {self.get_reserve_type_display()} {self.amount_cents}¢ on {self.claim}"


class ClaimPayment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        PENDING_APPROVAL = "PENDING_APPROVAL"
        APPROVED = "APPROVED"
        PENDING = "PENDING"
        SETTLED = "SETTLED"
        RETURNED = "RETURNED"
        FAILED = "FAILED"

    claim = models.ForeignKey(Claim, on_delete=models.PROTECT, related_name="claim_payments")
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    payee = models.CharField(max_length=255)
    effective_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    payout_reference = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ClaimPayment {self.id} — {self.amount_cents}¢ ({self.get_status_display()})"


class PayoutDestination(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING"
        VERIFIED = "VERIFIED"
        FAILED = "FAILED"

    claim = models.OneToOneField(Claim, on_delete=models.PROTECT, related_name="payout_destination")
    payee_name = models.CharField(max_length=255)
    account_last_four = models.CharField(max_length=4, help_text="Masked last 4 digits")
    verification_status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )
    provider = models.CharField(max_length=50, default="SIMULATED")
    provider_reference = models.CharField(max_length=255, blank=True, default="")
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PayoutDest {self.payee_name} (****{self.account_last_four}) [{self.verification_status}]"

    def save(self, *args, **kwargs):
        if not self.provider_reference:
            self.provider_reference = f"SIM-BANK-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)
