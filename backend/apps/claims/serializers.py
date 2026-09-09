from rest_framework import serializers

from apps.claims.models import Claim, ClaimPayment, PayoutDestination, ReserveEvent


class ClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = [
            "id",
            "policy",
            "claim_number",
            "status",
            "date_of_loss",
            "description",
            "estimated_amount_cents",
            "reported_at",
            "created_by",
            "created_at",
            "updated_at",
        ]


class ReserveEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReserveEvent
        fields = [
            "id",
            "claim",
            "amount_cents",
            "reserve_type",
            "effective_at",
            "recorded_at",
            "created_by",
            "memo",
        ]


class ClaimPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaimPayment
        fields = [
            "id",
            "claim",
            "amount_cents",
            "status",
            "payee",
            "effective_at",
            "recorded_at",
            "created_by",
            "approved_by",
            "payout_reference",
            "created_at",
            "updated_at",
        ]


class PayoutDestinationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutDestination
        fields = [
            "id",
            "claim",
            "payee_name",
            "account_last_four",
            "verification_status",
            "provider",
            "provider_reference",
            "verified_at",
            "created_at",
            "updated_at",
        ]


class SubmitClaimSerializer(serializers.Serializer):
    policy_id = serializers.IntegerField()
    date_of_loss = serializers.DateField()
    description = serializers.CharField()
    estimated_amount_cents = serializers.IntegerField(required=False)


class SetReserveSerializer(serializers.Serializer):
    amount_cents = serializers.IntegerField()
    reserve_type = serializers.ChoiceField(choices=ReserveEvent.ReserveType.choices)
    memo = serializers.CharField(required=False, default="")


class CreateClaimPaymentSerializer(serializers.Serializer):
    amount_cents = serializers.IntegerField(min_value=1)
    payee = serializers.CharField()


class SetPayoutDestinationSerializer(serializers.Serializer):
    payee_name = serializers.CharField()
    account_last_four = serializers.CharField(max_length=4, min_length=4)


class VerifyPayoutDestinationSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["VERIFIED", "FAILED"])
