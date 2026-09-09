from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffUser
from apps.endorsements.models import Endorsement
from apps.endorsements.serializers import (
    CorrectEndorsementSerializer,
    CreateEndorsementSerializer,
    EndorsementSerializer,
)
from apps.endorsements.services import (
    EndorsementError,
    apply_endorsement,
    approve_endorsement,
    correct_endorsement,
    create_endorsement,
)
from apps.policies.models import Policy


class EndorsementListView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsStaffUser()]
        return super().get_permissions()

    def get(self, request):
        policy_id = request.query_params.get("policy_id")
        qs = Endorsement.objects.select_related("policy").order_by("-created_at")

        if policy_id:
            qs = qs.filter(policy_id=policy_id)

        if request.user.role == "CUSTOMER":
            qs = qs.filter(policy__customer=request.user)

        return Response(EndorsementSerializer(qs, many=True).data)

    def post(self, request):
        serializer = CreateEndorsementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            endorsement, charges = create_endorsement(
                policy_id=serializer.validated_data["policy_id"],
                endorsement_type=serializer.validated_data["endorsement_type"],
                effective_date=serializer.validated_data["effective_date"],
                annual_premium_delta_cents=serializer.validated_data.get("annual_premium_delta_cents", 0),
                description=serializer.validated_data["description"],
                created_by=request.user,
            )
        except Policy.DoesNotExist:
            return Response({"detail": "Policy not found."}, status=status.HTTP_404_NOT_FOUND)
        except EndorsementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"endorsement": EndorsementSerializer(endorsement).data, "charges": charges},
            status=status.HTTP_201_CREATED,
        )


class EndorsementDetailView(APIView):
    def get(self, request, pk):
        try:
            endorsement = Endorsement.objects.select_related("policy").get(pk=pk)
        except Endorsement.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == "CUSTOMER" and endorsement.policy.customer_id != request.user.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(EndorsementSerializer(endorsement).data)


class ApproveEndorsementView(APIView):
    def post(self, request, pk):
        try:
            endorsement = approve_endorsement(endorsement_id=pk, approved_by=request.user)
        except Endorsement.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        except EndorsementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(EndorsementSerializer(endorsement).data)


class ApplyEndorsementView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        try:
            endorsement = apply_endorsement(endorsement_id=pk)
        except Endorsement.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        except EndorsementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(EndorsementSerializer(endorsement).data)


class CorrectEndorsementView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        serializer = CorrectEndorsementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            corrected = correct_endorsement(
                endorsement_id=pk,
                corrected_effective_date=serializer.validated_data["corrected_effective_date"],
                created_by=request.user,
            )
        except Endorsement.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        except EndorsementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(EndorsementSerializer(corrected).data, status=status.HTTP_201_CREATED)
