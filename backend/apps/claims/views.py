from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffUser
from apps.claims.models import Claim, ClaimPayment, PayoutDestination, ReserveEvent
from apps.claims.serializers import (
    ClaimPaymentSerializer,
    ClaimSerializer,
    CreateClaimPaymentSerializer,
    PayoutDestinationSerializer,
    ReserveEventSerializer,
    SetPayoutDestinationSerializer,
    SetReserveSerializer,
    SubmitClaimSerializer,
    VerifyPayoutDestinationSerializer,
)
from apps.claims.services import (
    ClaimError,
    approve_claim_payment,
    create_claim_payment,
    execute_payout,
    get_claim_financials,
    handle_payout_returned,
    handle_payout_settled,
    set_payout_destination,
    set_reserve,
    submit_claim,
    verify_payout_destination,
)
from apps.policies.models import Policy


class ClaimListView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return super().get_permissions()
        return super().get_permissions()

    def get(self, request):
        qs = Claim.objects.select_related("policy").order_by("-created_at")

        policy_id = request.query_params.get("policy_id")
        if policy_id:
            qs = qs.filter(policy_id=policy_id)

        if request.user.role == "CUSTOMER":
            qs = qs.filter(policy__customer=request.user)

        return Response(ClaimSerializer(qs, many=True).data)

    def post(self, request):
        serializer = SubmitClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            claim = submit_claim(
                policy_id=serializer.validated_data["policy_id"],
                date_of_loss=serializer.validated_data["date_of_loss"],
                description=serializer.validated_data["description"],
                estimated_amount_cents=serializer.validated_data.get("estimated_amount_cents"),
                user=request.user,
            )
        except Policy.DoesNotExist:
            return Response({"detail": "Policy not found."}, status=status.HTTP_404_NOT_FOUND)
        except ClaimError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ClaimSerializer(claim).data, status=status.HTTP_201_CREATED)


class ClaimDetailView(APIView):
    def get(self, request, pk):
        try:
            claim = Claim.objects.select_related("policy").get(pk=pk)
        except Claim.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == "CUSTOMER" and claim.policy.customer_id != request.user.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        financials = get_claim_financials(claim.id)

        dest = None
        try:
            dest = PayoutDestinationSerializer(claim.payout_destination).data
        except PayoutDestination.DoesNotExist:
            pass

        return Response(
            {
                "claim": ClaimSerializer(claim).data,
                "financials": financials,
                "payout_destination": dest,
            }
        )


class ReserveEventListView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request, claim_pk):
        events = ReserveEvent.objects.filter(claim_id=claim_pk).order_by("-recorded_at")
        return Response(ReserveEventSerializer(events, many=True).data)

    def post(self, request, claim_pk):
        serializer = SetReserveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            event = set_reserve(
                claim_id=claim_pk,
                amount_cents=serializer.validated_data["amount_cents"],
                reserve_type=serializer.validated_data["reserve_type"],
                memo=serializer.validated_data.get("memo", ""),
                user=request.user,
            )
        except Claim.DoesNotExist:
            return Response({"detail": "Claim not found."}, status=status.HTTP_404_NOT_FOUND)
        except ClaimError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ReserveEventSerializer(event).data, status=status.HTTP_201_CREATED)


class ClaimPaymentListView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request, claim_pk):
        payments = ClaimPayment.objects.filter(claim_id=claim_pk).order_by("-created_at")
        return Response(ClaimPaymentSerializer(payments, many=True).data)

    def post(self, request, claim_pk):
        serializer = CreateClaimPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payment = create_claim_payment(
                claim_id=claim_pk,
                amount_cents=serializer.validated_data["amount_cents"],
                payee=serializer.validated_data["payee"],
                user=request.user,
            )
        except Claim.DoesNotExist:
            return Response({"detail": "Claim not found."}, status=status.HTTP_404_NOT_FOUND)
        except ClaimError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ClaimPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class ApproveClaimPaymentView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        try:
            payment = approve_claim_payment(payment_id=pk, user=request.user)
        except ClaimPayment.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        except ClaimError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ClaimPaymentSerializer(payment).data)


class ExecutePayoutView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        try:
            payment = execute_payout(payment_id=pk, user=request.user)
        except ClaimPayment.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        except ClaimError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ClaimPaymentSerializer(payment).data)


class PayoutCallbackView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request):
        payout_reference = request.data.get("payout_reference")
        event_type = request.data.get("event_type")
        amount_cents = request.data.get("amount_cents")

        if not payout_reference or not event_type:
            return Response({"detail": "payout_reference and event_type required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if event_type == "SETTLED":
                payment = handle_payout_settled(payout_reference=payout_reference, amount_cents=amount_cents)
            elif event_type == "RETURNED":
                payment = handle_payout_returned(
                    payout_reference=payout_reference, reason=request.data.get("reason", "")
                )
            else:
                return Response({"detail": f"Unknown event_type: {event_type}"}, status=status.HTTP_400_BAD_REQUEST)
        except ClaimPayment.DoesNotExist:
            return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
        except ClaimError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ClaimPaymentSerializer(payment).data)


class PayoutDestinationView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request, claim_pk):
        try:
            dest = PayoutDestination.objects.get(claim_id=claim_pk)
        except PayoutDestination.DoesNotExist:
            return Response({"detail": "No payout destination set."}, status=status.HTTP_404_NOT_FOUND)
        return Response(PayoutDestinationSerializer(dest).data)

    def post(self, request, claim_pk):
        serializer = SetPayoutDestinationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            dest = set_payout_destination(
                claim_id=claim_pk,
                payee_name=serializer.validated_data["payee_name"],
                account_last_four=serializer.validated_data["account_last_four"],
            )
        except Claim.DoesNotExist:
            return Response({"detail": "Claim not found."}, status=status.HTTP_404_NOT_FOUND)
        except ClaimError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PayoutDestinationSerializer(dest).data, status=status.HTTP_201_CREATED)


class VerifyPayoutDestinationView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, claim_pk):
        serializer = VerifyPayoutDestinationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            dest = verify_payout_destination(
                claim_id=claim_pk,
                outcome=serializer.validated_data["outcome"],
            )
        except PayoutDestination.DoesNotExist:
            return Response({"detail": "No payout destination set."}, status=status.HTTP_404_NOT_FOUND)
        except ClaimError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PayoutDestinationSerializer(dest).data)


class ClaimFinancialsView(APIView):
    def get(self, request, pk):
        try:
            claim = Claim.objects.get(pk=pk)
        except Claim.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == "CUSTOMER" and claim.policy.customer_id != request.user.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(get_claim_financials(claim.id))
