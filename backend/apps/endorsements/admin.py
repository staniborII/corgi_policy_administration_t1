from django.contrib import admin

from apps.endorsements.models import Endorsement


@admin.register(Endorsement)
class EndorsementAdmin(admin.ModelAdmin):
    list_display = (
        "endorsement_number",
        "policy",
        "endorsement_type",
        "status",
        "effective_date",
        "annual_premium_delta_cents",
        "premium_change_cents",
        "correction_of",
        "created_at",
    )
    list_filter = ("status", "endorsement_type")
    search_fields = ("endorsement_number", "policy__policy_number")
    readonly_fields = ("recorded_at", "created_at", "updated_at", "charges_snapshot")
    date_hierarchy = "effective_date"

    def has_change_permission(self, request, obj=None):
        if obj and obj.status in ("APPLIED", "REVERSED"):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
