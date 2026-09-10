from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffUser
from apps.brokers.models import Broker
from apps.brokers.serializers import BrokerSerializer, CreateBrokerSerializer, KYBVerificationSerializer
from apps.brokers.services import BrokerError, create_broker, initiate_kyb


class BrokerListView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        brokers = Broker.objects.select_related("user").order_by("-created_at")
        return Response(BrokerSerializer(brokers, many=True).data)

    def post(self, request):
        serializer = CreateBrokerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            broker = create_broker(**serializer.validated_data)
        except BrokerError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BrokerSerializer(broker).data, status=status.HTTP_201_CREATED)


class BrokerDetailView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request, pk):
        try:
            broker = Broker.objects.select_related("user").get(pk=pk)
        except Broker.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BrokerSerializer(broker).data)


class BrokerKYBInitiateView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        try:
            kyb = initiate_kyb(broker_id=pk)
        except Broker.DoesNotExist:
            return Response({"detail": "Broker not found."}, status=status.HTTP_404_NOT_FOUND)
        except BrokerError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(KYBVerificationSerializer(kyb).data, status=status.HTTP_201_CREATED)
