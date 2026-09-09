from django.conf import settings
from django.db import models


class Endorsement(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        PENDING_CUSTOMER_APPROVAL = "PENDING_CUSTOMER_APPROVAL"
        APPROVED = "APPROVED"
        PENDING_PAYMENT = "PENDING_PAYMENT"
        APPLIED = "APPLIED"
        REVERSED = "REVERSED"

    class EndorsementType(models.TextChoices):
        COVERAGE_LIMIT_CHANGE = "COVERAGE_LIMIT_CHANGE"
        ADDRESS_CORRECTION = "ADDRESS_CORRECTION"

    CUSTOMER_APPROVAL_THRESHOLD_CENTS = 50000

    policy = models.ForeignKey("policies.Policy", on_delete=models.PROTECT, related_name="endorsements")
    endorsement_number = models.CharField(max_length=50, unique=True)
    endorsement_type = models.CharField(
        max_length=30, choices=EndorsementType.choices, default=EndorsementType.COVERAGE_LIMIT_CHANGE
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    description = models.TextField()
    effective_date = models.DateField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    annual_premium_delta_cents = models.IntegerField(default=0, help_text="Full annual premium change before pro-rata")
    premium_change_cents = models.IntegerField(
        default=0, help_text="Pro-rated premium change (positive = additional, negative = return)"
    )
    charges_snapshot = models.JSONField(null=True, blank=True, help_text="Pro-rated charge breakdown")

    correction_of = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrections"
    )

    data = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective_date", "-created_at"]

    def __str__(self):
        return f"Endorsement {self.endorsement_number} ({self.get_status_display()})"
