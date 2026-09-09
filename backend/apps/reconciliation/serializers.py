from rest_framework import serializers

from apps.reconciliation.models import BrokerStatement


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
