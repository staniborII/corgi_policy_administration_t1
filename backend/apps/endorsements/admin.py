from django.contrib import admin

from apps.endorsements.models import Endorsement


@admin.register(Endorsement)
class EndorsementAdmin(admin.ModelAdmin):
    list_display = ("endorsement_number", "policy", "status", "effective_date", "premium_change_cents", "created_at")
    list_filter = ("status",)
    search_fields = ("endorsement_number", "policy__policy_number")
    readonly_fields = ("recorded_at", "created_at", "updated_at")
    date_hierarchy = "effective_date"
