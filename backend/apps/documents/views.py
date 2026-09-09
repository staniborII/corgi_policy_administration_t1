from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.services import generate_declarations_pdf, generate_endorsement_schedule_pdf
from apps.policies.models import Policy


class DeclarationsDownloadView(APIView):
    def get(self, request, policy_id):
        as_of = self._parse_as_of(request)
        if as_of is False:
            return Response({"detail": "Invalid as_of datetime."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == "CUSTOMER" and policy.customer_id != request.user.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        pdf_bytes = generate_declarations_pdf(policy_id, as_of=as_of)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="declarations_{policy.policy_number}.pdf"'
        return response

    def _parse_as_of(self, request):
        as_of_str = request.query_params.get("as_of")
        if not as_of_str:
            return None
        parsed = parse_datetime(as_of_str)
        if parsed is None:
            return False
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)
        return parsed


class EndorsementScheduleDownloadView(APIView):
    def get(self, request, policy_id):
        as_of = self._parse_as_of(request)
        if as_of is False:
            return Response({"detail": "Invalid as_of datetime."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == "CUSTOMER" and policy.customer_id != request.user.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        pdf_bytes = generate_endorsement_schedule_pdf(policy_id, as_of=as_of)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="endorsement_schedule_{policy.policy_number}.pdf"'
        return response

    def _parse_as_of(self, request):
        as_of_str = request.query_params.get("as_of")
        if not as_of_str:
            return None
        parsed = parse_datetime(as_of_str)
        if parsed is None:
            return False
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)
        return parsed
