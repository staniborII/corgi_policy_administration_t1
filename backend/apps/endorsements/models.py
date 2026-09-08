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

    policy = models.ForeignKey("policies.Policy", on_delete=models.PROTECT, related_name="endorsements")
    endorsement_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    description = models.TextField()
    effective_date = models.DateField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    premium_change_cents = models.IntegerField(default=0, help_text="Positive = additional premium, negative = return")
    data = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Endorsement {self.endorsement_number} ({self.get_status_display()})"
