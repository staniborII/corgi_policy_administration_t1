from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffUser
from apps.brokers.models import Broker
from apps.reconciliation.models import BrokerStatement, ReconciliationBreak, ReconciliationRun
from apps.reconciliation.serializers import (
    BrokerStatementSerializer,
    GenerateStatementSerializer,
    ReconciliationBreakSerializer,
    ReconciliationRunSerializer,
    ResolveBreakSerializer,
)
from apps.reconciliation.services import generate_broker_statement, resolve_break, run_reconciliation


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


class ReconciliationRunListView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        qs = ReconciliationRun.objects.order_by("-started_at")[:50]
        return Response(ReconciliationRunSerializer(qs, many=True).data)

    def post(self, request):
        recon_run = run_reconciliation()
        return Response(ReconciliationRunSerializer(recon_run).data, status=status.HTTP_201_CREATED)


class ReconciliationRunDetailView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request, pk):
        try:
            recon_run = ReconciliationRun.objects.get(pk=pk)
        except ReconciliationRun.DoesNotExist:
            return Response({"detail": "Run not found."}, status=status.HTTP_404_NOT_FOUND)

        run_data = ReconciliationRunSerializer(recon_run).data
        breaks = ReconciliationBreak.objects.filter(run=recon_run).order_by("-created_at")
        run_data["breaks"] = ReconciliationBreakSerializer(breaks, many=True).data
        return Response(run_data)


class ReconciliationBreakListView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        qs = ReconciliationBreak.objects.select_related("run").order_by("-created_at")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(ReconciliationBreakSerializer(qs[:100], many=True).data)


class ResolveBreakView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        serializer = ResolveBreakSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            brk = resolve_break(
                break_id=pk,
                resolved_by=request.user,
                notes=serializer.validated_data.get("notes", ""),
            )
        except ReconciliationBreak.DoesNotExist:
            return Response({"detail": "Break not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(ReconciliationBreakSerializer(brk).data)
