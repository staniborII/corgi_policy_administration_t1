from django.conf import settings
from django.db import models


class Policy(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        PENDING_PAYMENT = "PENDING_PAYMENT"
        ACTIVE = "ACTIVE"
        CANCELLED = "CANCELLED"
        EXPIRED = "EXPIRED"

    policy_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="policies")
    broker = models.ForeignKey("brokers.Broker", on_delete=models.PROTECT, related_name="policies")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    effective_date = models.DateField()
    expiration_date = models.DateField()
    premium_amount_cents = models.PositiveIntegerField()
    coverage_limit_cents = models.PositiveIntegerField(default=100_000_000, help_text="Per-occurrence limit in cents")
    coverage_territory = models.CharField(max_length=2, help_text="US state code")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "policies"

    def __str__(self):
        return f"Policy {self.policy_number} ({self.get_status_display()})"


class PolicyEvent(models.Model):
    class EventType(models.TextChoices):
        CREATED = "CREATED"
        PAYMENT_REQUESTED = "PAYMENT_REQUESTED"
        ACTIVATED = "ACTIVATED"
        ENDORSED = "ENDORSED"
        CANCELLED = "CANCELLED"
        EXPIRED = "EXPIRED"
        RENEWED = "RENEWED"

    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    effective_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    data = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-effective_at", "-recorded_at"]

    def __str__(self):
        return f"{self.get_event_type_display()} on {self.policy.policy_number}"


class TaxRule(models.Model):
    class ComponentType(models.TextChoices):
        TAX = "TAX"
        SURCHARGE = "SURCHARGE"

    jurisdiction = models.CharField(max_length=2, help_text="US state code")
    name = models.CharField(max_length=255)
    component_type = models.CharField(max_length=20, choices=ComponentType.choices)
    rate_bps = models.PositiveIntegerField(help_text="Basis points, e.g. 350 = 3.50%")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_refundable = models.BooleanField(default=False)

    class Meta:
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.name} ({self.jurisdiction}) {self.rate_bps}bps"


class FeeRule(models.Model):
    class FeeType(models.TextChoices):
        FLAT = "FLAT"
        RATE = "RATE"

    jurisdiction = models.CharField(max_length=2, help_text="US state code")
    name = models.CharField(max_length=255)
    fee_type = models.CharField(max_length=10, choices=FeeType.choices)
    amount_cents = models.PositiveIntegerField(null=True, blank=True, help_text="For FLAT fees")
    rate_bps = models.PositiveIntegerField(null=True, blank=True, help_text="For RATE fees, basis points")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_refundable = models.BooleanField(default=False)

    class Meta:
        ordering = ["-effective_from"]

    def __str__(self):
        if self.fee_type == self.FeeType.FLAT:
            return f"{self.name} ({self.jurisdiction}) ${self.amount_cents / 100:.2f}"
        return f"{self.name} ({self.jurisdiction}) {self.rate_bps}bps"
