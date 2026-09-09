from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payments.models import Payment
from apps.payments.serializers import CreateCheckoutSerializer, PaymentSerializer
from apps.payments.services import PaymentError, create_checkout_for_policy, simulate_payment_success
from apps.policies.models import Policy


class PolicyPaymentsView(APIView):
    """List payments for a specific policy."""

    def get(self, request, policy_id):
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return Response({"detail": "Policy not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == "CUSTOMER" and policy.customer_id != request.user.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        payments = Payment.objects.filter(policy=policy).order_by("-created_at")
        return Response(PaymentSerializer(payments, many=True).data)


class CreateCheckoutView(APIView):
    """Create a Stripe Checkout Session for a policy."""

    def post(self, request):
        serializer = CreateCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = create_checkout_for_policy(
                policy_id=serializer.validated_data["policy_id"],
                requested_by=request.user,
            )
        except Policy.DoesNotExist:
            return Response({"detail": "Policy not found."}, status=status.HTTP_404_NOT_FOUND)
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_201_CREATED)


class SimulatePaymentView(APIView):
    """Simulate a successful payment (only when Stripe is not configured)."""

    def post(self, request, payment_id):
        try:
            payment = simulate_payment_success(payment_id=payment_id)
        except Payment.DoesNotExist:
            return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PaymentSerializer(payment).data)
