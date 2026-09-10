from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.brokers.serializers import BrokerSerializer
from apps.policies.models import Policy, PolicyEvent


class PolicyEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyEvent
        fields = ("id", "event_type", "effective_at", "recorded_at", "data")
        read_only_fields = fields


class PolicySerializer(serializers.ModelSerializer):
    customer_detail = UserSerializer(source="customer", read_only=True)
    broker_detail = BrokerSerializer(source="broker", read_only=True)

    class Meta:
        model = Policy
        fields = (
            "id",
            "policy_number",
            "customer",
            "customer_detail",
            "broker",
            "broker_detail",
            "status",
            "effective_date",
            "expiration_date",
            "premium_amount_cents",
            "coverage_territory",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "policy_number",
            "status",
            "expiration_date",
            "created_at",
            "updated_at",
            "customer_detail",
            "broker_detail",
        )


class PolicyDetailSerializer(PolicySerializer):
    events = PolicyEventSerializer(many=True, read_only=True)

    class Meta(PolicySerializer.Meta):
        fields = PolicySerializer.Meta.fields + ("events",)


class CreatePolicySerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    broker_id = serializers.IntegerField()
    effective_date = serializers.DateField()
    premium_amount_cents = serializers.IntegerField(min_value=1)
    coverage_territory = serializers.CharField(max_length=2)


class UpdateEffectiveDateSerializer(serializers.Serializer):
    effective_date = serializers.DateField()
