from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsStaffUser
from apps.policies.models import FeeRule, Policy, TaxRule
from apps.policies.serializers import CreatePolicySerializer, PolicyDetailSerializer, PolicySerializer
from apps.policies.services import PolicyError, issue_policy


class PolicyListView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsStaffUser()]
        return super().get_permissions()

    def get(self, request):
        if request.user.role == "STAFF":
            policies = Policy.objects.select_related("customer", "broker__user").order_by("-created_at")
        else:
            policies = (
                Policy.objects.filter(customer=request.user).select_related("broker__user").order_by("-created_at")
            )
        return Response(PolicySerializer(policies, many=True).data)

    def post(self, request):
        serializer = CreatePolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            customer = User.objects.get(id=serializer.validated_data["customer_id"], role=User.Role.CUSTOMER)
        except User.DoesNotExist:
            return Response({"detail": "Customer not found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            policy, charges = issue_policy(
                customer=customer,
                broker_id=serializer.validated_data["broker_id"],
                effective_date=serializer.validated_data["effective_date"],
                premium_amount_cents=serializer.validated_data["premium_amount_cents"],
                coverage_territory=serializer.validated_data["coverage_territory"],
                created_by=request.user,
            )
        except PolicyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"policy": PolicySerializer(policy).data, "charges": charges},
            status=status.HTTP_201_CREATED,
        )


class JurisdictionListView(APIView):
    """Return jurisdictions that have configured tax or fee rules."""

    def get(self, request):
        tax_jurisdictions = set(TaxRule.objects.values_list("jurisdiction", flat=True).distinct())
        fee_jurisdictions = set(FeeRule.objects.values_list("jurisdiction", flat=True).distinct())
        all_jurisdictions = sorted(tax_jurisdictions | fee_jurisdictions)
        return Response(all_jurisdictions)


class PolicyDetailView(APIView):
    def get(self, request, pk):
        try:
            policy = Policy.objects.select_related("customer", "broker__user").prefetch_related("events").get(pk=pk)
        except Policy.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == "CUSTOMER" and policy.customer_id != request.user.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(PolicyDetailSerializer(policy).data)
