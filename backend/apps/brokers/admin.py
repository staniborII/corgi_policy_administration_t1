from django.contrib import admin

from apps.brokers.models import Broker, KYBVerification


class KYBInline(admin.TabularInline):
    model = KYBVerification
    extra = 0
    readonly_fields = (
        "provider",
        "provider_reference",
        "persona_inquiry_id",
        "status",
        "result_payload",
        "onboarding_url",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin):
    list_display = ("company_name", "user", "status", "commission_rate_bps", "stripe_connect_account_id", "created_at")
    list_filter = ("status",)
    search_fields = ("company_name", "user__username", "user__email", "stripe_connect_account_id")
    readonly_fields = ("created_at", "updated_at")
    inlines = [KYBInline]


@admin.register(KYBVerification)
class KYBVerificationAdmin(admin.ModelAdmin):
    list_display = ("broker", "provider", "status", "provider_reference", "created_at")
    list_filter = ("status", "provider")
    search_fields = ("broker__company_name", "provider_reference", "persona_inquiry_id")
    readonly_fields = ("created_at", "updated_at")
