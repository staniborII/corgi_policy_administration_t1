from rest_framework import serializers

from apps.endorsements.models import Endorsement


class EndorsementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Endorsement
        fields = [
            "id",
            "policy",
            "endorsement_number",
            "endorsement_type",
            "status",
            "description",
            "effective_date",
            "annual_premium_delta_cents",
            "premium_change_cents",
            "charges_snapshot",
            "correction_of",
            "created_at",
            "recorded_at",
        ]


class CreateEndorsementSerializer(serializers.Serializer):
    policy_id = serializers.IntegerField()
    endorsement_type = serializers.ChoiceField(choices=Endorsement.EndorsementType.choices)
    effective_date = serializers.DateField()
    annual_premium_delta_cents = serializers.IntegerField(default=0)
    description = serializers.CharField()


class CorrectEndorsementSerializer(serializers.Serializer):
    corrected_effective_date = serializers.DateField()
