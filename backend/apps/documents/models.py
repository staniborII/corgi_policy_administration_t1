from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Document(models.Model):
    class DocumentType(models.TextChoices):
        DECLARATION = "DECLARATION"
        ENDORSEMENT_SCHEDULE = "ENDORSEMENT_SCHEDULE"
        BROKER_STATEMENT = "BROKER_STATEMENT"
        CLAIM_REPORT = "CLAIM_REPORT"

    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    file_path = models.CharField(max_length=500, blank=True)
    file_name = models.CharField(max_length=255)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.get_document_type_display()} — {self.file_name}"
