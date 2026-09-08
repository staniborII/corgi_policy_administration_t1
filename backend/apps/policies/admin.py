from django.contrib import admin

from apps.policies.models import FeeRule, Policy, PolicyEvent, TaxRule


class PolicyEventInline(admin.TabularInline):
    model = PolicyEvent
    extra = 0
    readonly_fields = ("event_type", "effective_at", "recorded_at", "data", "created_by")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = (
        "policy_number",
        "customer",
        "broker",
        "status",
        "effective_date",
        "expiration_date",
        "premium_amount_cents",
    )
    list_filter = ("status", "coverage_territory")
    search_fields = ("policy_number", "customer__username", "customer__email", "broker__company_name")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "effective_date"
    inlines = [PolicyEventInline]


@admin.register(PolicyEvent)
class PolicyEventAdmin(admin.ModelAdmin):
    list_display = ("policy", "event_type", "effective_at", "recorded_at")
    list_filter = ("event_type",)
    search_fields = ("policy__policy_number",)
    readonly_fields = ("policy", "event_type", "effective_at", "recorded_at", "data", "created_by")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TaxRule)
class TaxRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "jurisdiction",
        "component_type",
        "rate_bps",
        "effective_from",
        "effective_to",
        "is_refundable",
    )
    list_filter = ("jurisdiction", "component_type", "is_refundable")
    search_fields = ("name", "jurisdiction")


@admin.register(FeeRule)
class FeeRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "jurisdiction",
        "fee_type",
        "amount_cents",
        "rate_bps",
        "effective_from",
        "effective_to",
        "is_refundable",
    )
    list_filter = ("jurisdiction", "fee_type", "is_refundable")
    search_fields = ("name", "jurisdiction")
