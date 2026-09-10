from django.conf import settings
from django.db import models


class Broker(models.Model):
    class Status(models.TextChoices):
        PENDING_KYB = "PENDING_KYB"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="broker_profile")
    company_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_KYB)
    commission_rate_bps = models.PositiveIntegerField(help_text="Basis points, e.g. 1500 = 15%")
    stripe_connect_account_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.company_name} ({self.get_status_display()})"


class KYBVerification(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"

    class Provider(models.TextChoices):
        STRIPE_CONNECT = "STRIPE_CONNECT", "Stripe Connect"
        PERSONA = "PERSONA", "Persona"
        SIMULATED = "SIMULATED", "Simulated"

    broker = models.ForeignKey(Broker, on_delete=models.PROTECT, related_name="kyb_verifications")
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.SIMULATED)
    provider_reference = models.CharField(max_length=255, blank=True)
    persona_inquiry_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    result_payload = models.JSONField(default=dict, blank=True)
    onboarding_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"KYB {self.id} for {self.broker} ({self.provider}: {self.get_status_display()})"
