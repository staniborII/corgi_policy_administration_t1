from django.contrib import admin

from apps.ledger.models import JournalEntry, JournalLine, LedgerAccount


@admin.register(LedgerAccount)
class LedgerAccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "account_type", "normal_balance", "is_active")
    list_filter = ("account_type", "is_active")
    search_fields = ("code", "name")
    ordering = ("code",)


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    readonly_fields = ("account", "amount_cents", "entry_type")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "memo_short", "effective_at", "recorded_at", "posted_at", "reversal_of")
    list_filter = ("status",)
    search_fields = ("memo", "idempotency_key")
    readonly_fields = (
        "effective_at",
        "recorded_at",
        "memo",
        "idempotency_key",
        "status",
        "reversal_of",
        "posted_at",
    )
    inlines = [JournalLineInline]

    def memo_short(self, obj):
        return obj.memo[:60] if obj.memo else ""

    memo_short.short_description = "Memo"

    def has_change_permission(self, request, obj=None):
        if obj and obj.status == "POSTED":
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(JournalLine)
class JournalLineAdmin(admin.ModelAdmin):
    list_display = ("id", "journal_entry", "account", "entry_type", "amount_cents")
    list_filter = ("entry_type",)
    search_fields = ("journal_entry__memo", "account__code", "account__name")
    readonly_fields = ("journal_entry", "account", "amount_cents", "entry_type")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
