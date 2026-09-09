from rest_framework import serializers

from apps.reconciliation.models import BrokerStatement, ReconciliationBreak, ReconciliationRun


class BrokerStatementSerializer(serializers.ModelSerializer):
    broker_name = serializers.CharField(source="broker.company_name", read_only=True)

    class Meta:
        model = BrokerStatement
        fields = (
            "id",
            "broker",
            "broker_name",
            "period_start",
            "period_end",
            "total_premium_cents",
            "total_commission_cents",
            "total_clawback_cents",
            "net_due_cents",
            "statement_data",
            "is_closed",
            "generated_at",
        )
        read_only_fields = fields


class GenerateStatementSerializer(serializers.Serializer):
    broker_id = serializers.IntegerField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()


class ReconciliationBreakSerializer(serializers.ModelSerializer):
    age_seconds = serializers.SerializerMethodField()

    class Meta:
        model = ReconciliationBreak
        fields = (
            "id",
            "run",
            "break_type",
            "description",
            "source",
            "external_reference",
            "local_reference",
            "expected_amount_cents",
            "actual_amount_cents",
            "first_seen_at",
            "status",
            "resolved",
            "resolution_notes",
            "resolved_at",
            "age_seconds",
            "created_at",
        )
        read_only_fields = fields

    def get_age_seconds(self, obj):
        if obj.first_seen_at:
            from django.utils import timezone

            return int((timezone.now() - obj.first_seen_at).total_seconds())
        return None


class ReconciliationRunSerializer(serializers.ModelSerializer):
    breaks_count = serializers.SerializerMethodField()

    class Meta:
        model = ReconciliationRun
        fields = (
            "id",
            "run_date",
            "status",
            "started_at",
            "completed_at",
            "summary",
            "breaks_count",
        )
        read_only_fields = fields

    def get_breaks_count(self, obj):
        return obj.breaks.count()


class ResolveBreakSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, default="")
