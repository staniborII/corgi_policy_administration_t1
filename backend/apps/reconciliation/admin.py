from django.contrib import admin

from apps.reconciliation.models import BrokerStatement, ReconciliationBreak, ReconciliationRun


class BreakInline(admin.TabularInline):
    model = ReconciliationBreak
    extra = 0
    readonly_fields = ("break_type", "description", "expected_amount_cents", "actual_amount_cents", "reference_id")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReconciliationRun)
class ReconciliationRunAdmin(admin.ModelAdmin):
    list_display = ("id", "run_date", "status", "started_at", "completed_at")
    list_filter = ("status",)
    readonly_fields = ("started_at",)
    date_hierarchy = "run_date"
    inlines = [BreakInline]


@admin.register(ReconciliationBreak)
class ReconciliationBreakAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "break_type", "expected_amount_cents", "actual_amount_cents", "resolved")
    list_filter = ("break_type", "resolved")
    search_fields = ("reference_id", "description")
    readonly_fields = ("created_at",)


@admin.register(BrokerStatement)
class BrokerStatementAdmin(admin.ModelAdmin):
    list_display = (
        "broker",
        "period_start",
        "period_end",
        "total_premium_cents",
        "total_commission_cents",
        "total_clawback_cents",
        "net_due_cents",
        "is_closed",
        "generated_at",
    )
    list_filter = ("broker", "is_closed")
    search_fields = ("broker__company_name",)
    readonly_fields = ("generated_at", "statement_data")
