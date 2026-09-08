from django.contrib import admin

from apps.approvals.models import Approval


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display = ("id", "action", "status", "requested_by", "decided_by", "created_at", "decided_at")
    list_filter = ("action", "status")
    search_fields = ("requested_by__username", "decided_by__username", "reason")
    readonly_fields = ("content_type", "object_id", "action", "requested_by", "created_at")
