from django.contrib import admin

from apps.integrations.models import KYBProviderConfig, WebhookEvent


@admin.register(KYBProviderConfig)
class KYBProviderConfigAdmin(admin.ModelAdmin):
    list_display = ("active_provider", "updated_at")
    fields = ("active_provider",)

    def has_add_permission(self, request):
        return not KYBProviderConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "event_type", "event_id", "status", "received_at", "processed_at")
    list_filter = ("provider", "status", "event_type")
    search_fields = ("event_id", "idempotency_key")
    readonly_fields = (
        "provider",
        "event_id",
        "event_type",
        "payload",
        "idempotency_key",
        "received_at",
        "processed_at",
        "error_message",
    )

    def has_change_permission(self, request, obj=None):
        if obj and obj.status == "PROCESSED":
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
