from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffUser
from apps.brokers.models import Broker
from apps.reconciliation.models import BrokerStatement
from apps.reconciliation.serializers import BrokerStatementSerializer, GenerateStatementSerializer
from apps.reconciliation.services import generate_broker_statement


class BrokerStatementListView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        broker_id = request.query_params.get("broker_id")
        qs = BrokerStatement.objects.select_related("broker").order_by("-period_end")
        if broker_id:
            qs = qs.filter(broker_id=broker_id)
        return Response(BrokerStatementSerializer(qs, many=True).data)

    def post(self, request):
        serializer = GenerateStatementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            broker = Broker.objects.get(id=serializer.validated_data["broker_id"])
        except Broker.DoesNotExist:
            return Response({"detail": "Broker not found."}, status=status.HTTP_404_NOT_FOUND)

        statement = generate_broker_statement(
            broker=broker,
            period_start=serializer.validated_data["period_start"],
            period_end=serializer.validated_data["period_end"],
        )

        return Response(BrokerStatementSerializer(statement).data, status=status.HTTP_201_CREATED)


class BrokerStatementDetailView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request, pk):
        try:
            statement = BrokerStatement.objects.select_related("broker").get(pk=pk)
        except BrokerStatement.DoesNotExist:
            return Response({"detail": "Statement not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(BrokerStatementSerializer(statement).data)
