from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsStaffUser
from apps.payments.serializers import CancelPolicySerializer, RefundSerializer
from apps.policies.models import FeeRule, Policy, TaxRule
from apps.policies.selectors import get_policy_as_of
from apps.policies.serializers import (
    CreatePolicySerializer,
    PolicyDetailSerializer,
    PolicySerializer,
    UpdateEffectiveDateSerializer,
)
from apps.policies.services import (
    PolicyError,
    cancel_policy,
    decline_policy,
    issue_policy,
    update_policy_effective_date,
)


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


class PolicyAsOfView(APIView):
    """Reconstruct policy state at a historical point in time."""

    def get(self, request, pk):
        as_of_str = request.query_params.get("as_of")
        as_of = None
        if as_of_str:
            as_of = parse_datetime(as_of_str)
            if as_of is None:
                return Response({"detail": "Invalid as_of datetime."}, status=status.HTTP_400_BAD_REQUEST)
            if timezone.is_naive(as_of):
                as_of = timezone.make_aware(as_of)

        try:
            policy = Policy.objects.get(pk=pk)
        except Policy.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == "CUSTOMER" and policy.customer_id != request.user.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        snapshot = get_policy_as_of(pk, as_of=as_of)
        return Response(snapshot)


class CancelPolicyView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        serializer = CancelPolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = cancel_policy(
                policy_id=pk,
                cancelled_by=request.user,
                cancellation_date=serializer.validated_data.get("cancellation_date"),
            )
        except Policy.DoesNotExist:
            return Response({"detail": "Policy not found."}, status=status.HTTP_404_NOT_FOUND)
        except PolicyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        response_data = {
            "policy": PolicySerializer(result["policy"]).data,
            "unearned_premium_cents": result["unearned_premium_cents"],
            "total_refundable_tax_cents": result["total_refundable_tax_cents"],
            "total_refundable_fees_cents": result["total_refundable_fees_cents"],
            "total_refund_cents": result["total_refund_cents"],
            "commission_clawback_cents": result["commission_clawback_cents"],
        }
        if result["refund"]:
            response_data["refund"] = RefundSerializer(result["refund"]).data

        return Response(response_data)


class UpdateEffectiveDateView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        serializer = UpdateEffectiveDateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            policy = update_policy_effective_date(
                policy_id=pk,
                new_effective_date=serializer.validated_data["effective_date"],
                updated_by=request.user,
            )
        except Policy.DoesNotExist:
            return Response({"detail": "Policy not found."}, status=status.HTTP_404_NOT_FOUND)
        except PolicyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PolicySerializer(policy).data)


class DeclinePolicyView(APIView):
    def post(self, request, pk):
        try:
            policy = decline_policy(policy_id=pk, declined_by=request.user)
        except Policy.DoesNotExist:
            return Response({"detail": "Policy not found."}, status=status.HTTP_404_NOT_FOUND)
        except PolicyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PolicySerializer(policy).data)
