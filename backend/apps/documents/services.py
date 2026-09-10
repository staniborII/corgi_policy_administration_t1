import io
import logging
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.documents.models import Document
from apps.documents.storage import is_s3_configured, upload_document
from apps.policies.models import Policy
from apps.policies.selectors import get_policy_as_of

logger = logging.getLogger(__name__)


def _fmt_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def _s3_key(policy_id: int, document_type: str, as_of: datetime | None = None) -> str:
    if as_of:
        ts = as_of.strftime("%Y-%m-%dT%H%M%S")
        return f"policies/{policy_id}/{document_type}/as-of-{ts}.pdf"
    ts = timezone.now().strftime("%Y-%m-%dT%H%M%S")
    return f"policies/{policy_id}/{document_type}/{ts}.pdf"


def _persist_to_s3(
    policy: Policy,
    document_type: str,
    file_name: str,
    pdf_bytes: bytes,
    as_of: datetime | None = None,
) -> Document | None:
    if not is_s3_configured():
        return None

    key = _s3_key(policy.id, document_type, as_of)
    if not upload_document(key, pdf_bytes):
        return None

    ct = ContentType.objects.get_for_model(Policy)
    doc = Document.objects.create(
        content_type=ct,
        object_id=policy.id,
        document_type=document_type,
        file_path=key,
        file_name=file_name,
    )
    logger.info("Persisted Document id=%d for policy %d at %s", doc.id, policy.id, key)
    return doc


def generate_declarations_pdf(policy_id: int, as_of: datetime | None = None) -> bytes:
    """Generate a declarations page PDF for a policy at a given point in time."""
    snapshot = get_policy_as_of(policy_id, as_of=as_of)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title2", parent=styles["Title"], fontSize=16, spaceAfter=12)
    heading_style = ParagraphStyle("Heading", parent=styles["Heading2"], fontSize=12, spaceAfter=6)

    elements = []

    elements.append(Paragraph("COMMERCIAL GENERAL LIABILITY", title_style))
    elements.append(Paragraph("DECLARATIONS PAGE", styles["Heading2"]))
    elements.append(Spacer(1, 12))

    if as_of:
        elements.append(Paragraph(f"<i>Policy state as of: {snapshot['as_of']}</i>", styles["Normal"]))
        elements.append(Spacer(1, 8))

    policy_data = [
        ["Policy Number:", snapshot["policy_number"]],
        ["Status:", snapshot["status"]],
        ["Named Insured:", snapshot["customer"]],
        ["Broker:", snapshot["broker"]],
        ["Effective Date:", snapshot["effective_date"]],
        ["Expiration Date:", snapshot["expiration_date"]],
        ["Coverage Territory:", snapshot["coverage_territory"]],
        ["Annual Premium:", _fmt_cents(snapshot["effective_premium_cents"])],
    ]

    t = Table(policy_data, colWidths=[2.5 * inch, 4 * inch])
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
            ]
        )
    )
    elements.append(t)
    elements.append(Spacer(1, 16))

    if snapshot["endorsements"]:
        elements.append(Paragraph("Endorsement History", heading_style))
        end_data = [["#", "Type", "Effective", "Premium Change"]]
        for e in snapshot["endorsements"]:
            end_data.append(
                [
                    e["endorsement_number"],
                    e["type"],
                    e["effective_date"],
                    _fmt_cents(e["premium_change_cents"]),
                ]
            )

        et = Table(end_data, colWidths=[1.5 * inch, 2 * inch, 1.5 * inch, 1.5 * inch])
        et.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e0e0")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        elements.append(et)

    elements.append(Spacer(1, 24))
    elements.append(
        Paragraph(
            "<i>This declarations page is generated from system records and reflects "
            "the policy state at the time indicated above.</i>",
            styles["Normal"],
        )
    )

    doc.build(elements)
    pdf_bytes = buf.getvalue()

    policy = Policy.objects.get(id=policy_id)
    file_name = f"declarations_{policy.policy_number}.pdf"
    _persist_to_s3(policy, Document.DocumentType.DECLARATION, file_name, pdf_bytes, as_of)

    return pdf_bytes


def generate_endorsement_schedule_pdf(policy_id: int, as_of: datetime | None = None) -> bytes:
    """Generate an endorsement schedule PDF listing all endorsements for a policy."""
    snapshot = get_policy_as_of(policy_id, as_of=as_of)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title2", parent=styles["Title"], fontSize=16, spaceAfter=12)

    elements = []

    elements.append(Paragraph("ENDORSEMENT SCHEDULE", title_style))
    elements.append(Paragraph(f"Policy: {snapshot['policy_number']}", styles["Heading2"]))
    elements.append(Spacer(1, 8))

    if as_of:
        elements.append(Paragraph(f"<i>As of: {snapshot['as_of']}</i>", styles["Normal"]))
        elements.append(Spacer(1, 8))

    if not snapshot["endorsements"]:
        elements.append(Paragraph("No endorsements on record.", styles["Normal"]))
    else:
        for e in snapshot["endorsements"]:
            elements.append(Paragraph(f"<b>{e['endorsement_number']}</b>", styles["Heading3"]))
            detail_data = [
                ["Type:", e["type"]],
                ["Effective Date:", e["effective_date"]],
                ["Annual Premium Change:", _fmt_cents(e["annual_premium_delta_cents"])],
                ["Pro-Rated Change:", _fmt_cents(e["premium_change_cents"])],
                ["Description:", e["description"]],
            ]
            dt = Table(detail_data, colWidths=[2 * inch, 4.5 * inch])
            dt.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            elements.append(dt)
            elements.append(Spacer(1, 12))

    elements.append(Spacer(1, 16))
    elements.append(
        Paragraph(
            f"<b>Current Annual Premium:</b> {_fmt_cents(snapshot['effective_premium_cents'])}",
            styles["Normal"],
        )
    )

    doc.build(elements)
    pdf_bytes = buf.getvalue()

    policy = Policy.objects.get(id=policy_id)
    file_name = f"endorsement_schedule_{policy.policy_number}.pdf"
    _persist_to_s3(policy, Document.DocumentType.ENDORSEMENT_SCHEDULE, file_name, pdf_bytes, as_of)

    return pdf_bytes
