from django.db import models


class KYBProviderConfig(models.Model):
    """Singleton config for which KYB provider to use. Managed via Django admin."""

    class KYBProvider(models.TextChoices):
        STRIPE_CONNECT = "STRIPE_CONNECT", "Stripe Connect"
        PERSONA = "PERSONA", "Persona"
        SIMULATED = "SIMULATED", "Simulated (no provider)"

    active_provider = models.CharField(
        max_length=20,
        choices=KYBProvider.choices,
        default=KYBProvider.STRIPE_CONNECT,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "KYB Provider Configuration"
        verbose_name_plural = "KYB Provider Configuration"

    def __str__(self):
        return f"KYB Provider: {self.get_active_provider_display()}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_active_provider(cls):
        config = cls.objects.filter(pk=1).first()
        if config:
            return config.active_provider
        return cls.KYBProvider.STRIPE_CONNECT


class WebhookEvent(models.Model):
    class Provider(models.TextChoices):
        STRIPE = "STRIPE"
        PERSONA = "PERSONA"

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED"
        PROCESSING = "PROCESSING"
        PROCESSED = "PROCESSED"
        FAILED = "FAILED"

    provider = models.CharField(max_length=20, choices=Provider.choices)
    event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=255)
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    idempotency_key = models.CharField(max_length=255, unique=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="unique_provider_event"),
        ]

    def __str__(self):
        return f"{self.provider} {self.event_type} ({self.get_status_display()})"
