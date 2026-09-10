from rest_framework import serializers

from apps.brokers.models import Broker, KYBVerification


class KYBVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYBVerification
        fields = (
            "id",
            "provider",
            "provider_reference",
            "persona_inquiry_id",
            "status",
            "onboarding_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class BrokerSerializer(serializers.ModelSerializer):
    latest_kyb = serializers.SerializerMethodField()

    class Meta:
        model = Broker
        fields = (
            "id",
            "user",
            "company_name",
            "status",
            "commission_rate_bps",
            "stripe_connect_account_id",
            "created_at",
            "updated_at",
            "latest_kyb",
        )
        read_only_fields = (
            "id",
            "user",
            "status",
            "stripe_connect_account_id",
            "created_at",
            "updated_at",
            "latest_kyb",
        )

    def get_latest_kyb(self, obj):
        kyb = obj.kyb_verifications.order_by("-created_at").first()
        if kyb:
            return KYBVerificationSerializer(kyb).data
        return None


class CreateBrokerSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    commission_rate_bps = serializers.IntegerField(min_value=0, max_value=10000)
    contact_email = serializers.EmailField()
    contact_first_name = serializers.CharField(max_length=150)
    contact_last_name = serializers.CharField(max_length=150)
