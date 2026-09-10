from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document
from apps.documents.services import generate_declarations_pdf, generate_endorsement_schedule_pdf
from apps.documents.storage import generate_presigned_url
from apps.policies.models import Policy


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ("id", "document_type", "file_name", "file_path", "generated_at")


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


class PolicyDocumentsListView(APIView):
    def get(self, request, policy_id):
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == "CUSTOMER" and policy.customer_id != request.user.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        ct = ContentType.objects.get_for_model(Policy)
        docs = Document.objects.filter(content_type=ct, object_id=policy_id).order_by("-generated_at")
        return Response(DocumentSerializer(docs, many=True).data)


class DocumentDownloadView(APIView):
    def get(self, request, document_id):
        try:
            doc = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == "CUSTOMER":
            policy = doc.content_object
            if policy and hasattr(policy, "customer_id") and policy.customer_id != request.user.id:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        url = generate_presigned_url(doc.file_path, filename=doc.file_name)
        if not url:
            return Response(
                {"detail": "Document storage not available."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"url": url, "file_name": doc.file_name})
