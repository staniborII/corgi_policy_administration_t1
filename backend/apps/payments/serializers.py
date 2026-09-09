from rest_framework import serializers

from apps.payments.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "policy",
            "amount_cents",
            "status",
            "stripe_payment_intent_id",
            "stripe_checkout_session_id",
            "charges_snapshot",
            "effective_at",
            "recorded_at",
            "created_at",
        )
        read_only_fields = fields


class CreateCheckoutSerializer(serializers.Serializer):
    policy_id = serializers.IntegerField()
