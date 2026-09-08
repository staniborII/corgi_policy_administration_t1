from django.contrib import admin

from apps.claims.models import Claim, ClaimPayment, ReserveEvent


class ReserveEventInline(admin.TabularInline):
    model = ReserveEvent
    extra = 0
    readonly_fields = ("amount_cents", "reserve_type", "effective_at", "recorded_at", "created_by", "memo")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ClaimPaymentInline(admin.TabularInline):
    model = ClaimPayment
    extra = 0
    readonly_fields = ("amount_cents", "status", "payee", "effective_at", "recorded_at", "created_by")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("claim_number", "policy", "status", "date_of_loss", "reported_at")
    list_filter = ("status",)
    search_fields = ("claim_number", "policy__policy_number")
    readonly_fields = ("reported_at", "created_at", "updated_at")
    date_hierarchy = "date_of_loss"
    inlines = [ReserveEventInline, ClaimPaymentInline]


@admin.register(ReserveEvent)
class ReserveEventAdmin(admin.ModelAdmin):
    list_display = ("claim", "reserve_type", "amount_cents", "effective_at", "recorded_at")
    list_filter = ("reserve_type",)
    search_fields = ("claim__claim_number",)
    readonly_fields = ("claim", "amount_cents", "reserve_type", "effective_at", "recorded_at", "created_by", "memo")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ClaimPayment)
class ClaimPaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "claim", "amount_cents", "status", "payee", "effective_at", "recorded_at")
    list_filter = ("status",)
    search_fields = ("claim__claim_number", "payee")
    readonly_fields = ("recorded_at", "created_at", "updated_at")
