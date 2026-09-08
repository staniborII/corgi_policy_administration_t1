from django.db import models


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
