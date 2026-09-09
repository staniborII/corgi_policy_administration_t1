from django.contrib import admin

from apps.payments.models import Payment, Refund


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "policy",
        "amount_cents",
        "status",
        "stripe_checkout_session_id",
        "stripe_payment_intent_id",
        "effective_at",
        "recorded_at",
    )
    list_filter = ("status",)
    search_fields = (
        "policy__policy_number",
        "stripe_payment_intent_id",
        "stripe_checkout_session_id",
        "idempotency_key",
    )
    readonly_fields = ("recorded_at", "created_at", "updated_at", "charges_snapshot", "idempotency_key")

    def has_change_permission(self, request, obj=None):
        if obj and obj.status == "SUCCEEDED":
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "amount_cents", "status", "stripe_refund_id", "effective_at", "recorded_at")
    list_filter = ("status",)
    search_fields = ("payment__policy__policy_number", "stripe_refund_id")
    readonly_fields = ("recorded_at", "created_at", "updated_at")
