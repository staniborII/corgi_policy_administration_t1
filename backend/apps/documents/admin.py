from django.contrib import admin

from apps.documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "document_type", "file_name", "generated_at")
    list_filter = ("document_type",)
    search_fields = ("file_name",)
    readonly_fields = ("generated_at",)
