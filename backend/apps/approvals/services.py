from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.approvals.models import Approval


class ApprovalError(Exception):
    pass


def create_approval(*, content_object, action, requested_by):
    ct = ContentType.objects.get_for_model(content_object)

    existing = Approval.objects.filter(
        content_type=ct, object_id=content_object.pk, action=action, status=Approval.Status.PENDING
    ).first()
    if existing:
        return existing

    return Approval.objects.create(
        content_type=ct,
        object_id=content_object.pk,
        action=action,
        requested_by=requested_by,
    )


def approve_approval(*, content_object, decided_by):
    ct = ContentType.objects.get_for_model(content_object)
    approval = Approval.objects.get(content_type=ct, object_id=content_object.pk, status=Approval.Status.PENDING)

    if approval.requested_by_id == decided_by.id:
        raise ApprovalError("Maker cannot approve their own request")

    approval.status = Approval.Status.APPROVED
    approval.decided_by = decided_by
    approval.decided_at = timezone.now()
    approval.save(update_fields=["status", "decided_by", "decided_at"])

    return approval


def reject_approval(*, content_object, decided_by, reason=""):
    ct = ContentType.objects.get_for_model(content_object)
    approval = Approval.objects.get(content_type=ct, object_id=content_object.pk, status=Approval.Status.PENDING)

    approval.status = Approval.Status.REJECTED
    approval.decided_by = decided_by
    approval.decided_at = timezone.now()
    approval.reason = reason
    approval.save(update_fields=["status", "decided_by", "decided_at", "reason"])

    return approval
