import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.endorsements.models import Endorsement
from apps.ledger.models import JournalLine
from apps.ledger.services import post_journal_entry, reverse_journal_entry
from apps.policies.models import Policy, PolicyEvent
from apps.policies.services import calculate_rate_amount, compute_policy_charges
from apps.ws.notifications import notify_policy_change


class EndorsementError(Exception):
    pass


def _days_in_term(policy: Policy) -> int:
    return (policy.expiration_date - policy.effective_date).days


def _remaining_days(policy: Policy, effective_date: date) -> int:
    return (policy.expiration_date - effective_date).days


def prorate_amount(annual_amount_cents: int, remaining_days: int, total_days: int) -> int:
    """Pro-rate an annual amount for the remaining portion of the policy term."""
    if total_days <= 0:
        return 0
    result = Decimal(annual_amount_cents) * Decimal(remaining_days) / Decimal(total_days)
    return int(result.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _compute_endorsement_charges(
    *, annual_premium_delta_cents: int, remaining_days: int, total_days: int, jurisdiction: str, effective_date: date
):
    prorated_premium = prorate_amount(annual_premium_delta_cents, remaining_days, total_days)

    charges = compute_policy_charges(
        premium_cents=abs(annual_premium_delta_cents),
        jurisdiction=jurisdiction,
        effective_date=effective_date,
    )

    sign = 1 if annual_premium_delta_cents >= 0 else -1

    prorated_tax_details = []
    prorated_tax_total = 0
    for td in charges.get("tax_details", []):
        prorated_tax = sign * prorate_amount(td["amount_cents"], remaining_days, total_days)
        prorated_tax_total += prorated_tax
        prorated_tax_details.append({**td, "amount_cents": prorated_tax})

    prorated_fee_details = []
    prorated_fee_total = 0
    for fd in charges.get("fee_details", []):
        prorated_fee = sign * prorate_amount(fd["amount_cents"], remaining_days, total_days)
        prorated_fee_total += prorated_fee
        prorated_fee_details.append({**fd, "amount_cents": prorated_fee})

    return {
        "annual_premium_delta_cents": annual_premium_delta_cents,
        "premium_change_cents": prorated_premium,
        "tax_details": prorated_tax_details,
        "total_tax_cents": prorated_tax_total,
        "fee_details": prorated_fee_details,
        "total_fees_cents": prorated_fee_total,
        "total_cents": prorated_premium + prorated_tax_total + prorated_fee_total,
        "remaining_days": remaining_days,
        "total_days": total_days,
    }


def _generate_endorsement_number():
    return f"END-{uuid.uuid4().hex[:8].upper()}"


@transaction.atomic
def create_endorsement(
    *,
    policy_id: int,
    endorsement_type: str,
    effective_date: date,
    annual_premium_delta_cents: int = 0,
    description: str,
    created_by,
):
    policy = Policy.objects.select_for_update().get(id=policy_id)

    if policy.status != Policy.Status.ACTIVE:
        raise EndorsementError("Can only endorse an active policy")

    if effective_date < policy.effective_date or effective_date >= policy.expiration_date:
        raise EndorsementError("Endorsement effective date must be within the policy term")

    total_days = _days_in_term(policy)
    remaining = _remaining_days(policy, effective_date)

    if endorsement_type == Endorsement.EndorsementType.ADDRESS_CORRECTION:
        annual_premium_delta_cents = 0

    charges = _compute_endorsement_charges(
        annual_premium_delta_cents=annual_premium_delta_cents,
        remaining_days=remaining,
        total_days=total_days,
        jurisdiction=policy.coverage_territory,
        effective_date=policy.effective_date,
    )

    needs_approval = charges["total_cents"] > Endorsement.CUSTOMER_APPROVAL_THRESHOLD_CENTS

    if needs_approval:
        initial_status = Endorsement.Status.PENDING_CUSTOMER_APPROVAL
    elif charges["total_cents"] > 0:
        initial_status = Endorsement.Status.PENDING_PAYMENT
    elif charges["total_cents"] < 0:
        initial_status = Endorsement.Status.APPROVED
    else:
        initial_status = Endorsement.Status.APPROVED

    endorsement = Endorsement.objects.create(
        policy=policy,
        endorsement_number=_generate_endorsement_number(),
        endorsement_type=endorsement_type,
        status=initial_status,
        description=description,
        effective_date=effective_date,
        annual_premium_delta_cents=annual_premium_delta_cents,
        premium_change_cents=charges["premium_change_cents"],
        charges_snapshot=charges,
        created_by=created_by,
    )

    PolicyEvent.objects.create(
        policy=policy,
        event_type=PolicyEvent.EventType.ENDORSED,
        effective_at=timezone.now(),
        created_by=created_by,
        data={
            "endorsement_id": endorsement.id,
            "endorsement_number": endorsement.endorsement_number,
            "type": endorsement_type,
            "charges": charges,
            "status": initial_status,
        },
    )

    transaction.on_commit(lambda: notify_policy_change(policy, "endorsement.created"))

    return endorsement, charges


@transaction.atomic
def approve_endorsement(*, endorsement_id: int, approved_by):
    endorsement = Endorsement.objects.select_for_update().get(id=endorsement_id)

    if endorsement.status != Endorsement.Status.PENDING_CUSTOMER_APPROVAL:
        raise EndorsementError("Endorsement is not pending approval")

    charges = endorsement.charges_snapshot or {}
    total = charges.get("total_cents", 0)

    if total > 0:
        endorsement.status = Endorsement.Status.PENDING_PAYMENT
    else:
        endorsement.status = Endorsement.Status.APPROVED

    endorsement.save(update_fields=["status", "updated_at"])

    policy = endorsement.policy
    transaction.on_commit(lambda: notify_policy_change(policy, "endorsement.approved"))

    return endorsement


@transaction.atomic
def apply_endorsement(*, endorsement_id: int, stripe_payment_intent_id: str = ""):
    endorsement = Endorsement.objects.select_for_update().get(id=endorsement_id)

    if endorsement.status not in (Endorsement.Status.APPROVED, Endorsement.Status.PENDING_PAYMENT):
        raise EndorsementError(f"Cannot apply endorsement in status {endorsement.status}")

    charges = endorsement.charges_snapshot or {}
    total = charges.get("total_cents", 0)
    policy = endorsement.policy
    now = timezone.now()

    if total != 0:
        is_additional = total > 0
        abs_total = abs(total)
        abs_premium = abs(charges.get("premium_change_cents", 0))

        journal_lines = []

        if is_additional:
            journal_lines.append(
                {
                    "account_code": "1010",
                    "amount_cents": abs_total,
                    "entry_type": JournalLine.EntryType.DEBIT,
                }
            )
            if abs_premium > 0:
                journal_lines.append(
                    {
                        "account_code": "2000",
                        "amount_cents": abs_premium,
                        "entry_type": JournalLine.EntryType.CREDIT,
                    }
                )
        else:
            journal_lines.append(
                {
                    "account_code": "1010",
                    "amount_cents": abs_total,
                    "entry_type": JournalLine.EntryType.CREDIT,
                }
            )
            if abs_premium > 0:
                journal_lines.append(
                    {
                        "account_code": "2000",
                        "amount_cents": abs_premium,
                        "entry_type": JournalLine.EntryType.DEBIT,
                    }
                )

        for td in charges.get("tax_details", []):
            amt = abs(td["amount_cents"])
            if amt > 0:
                journal_lines.append(
                    {
                        "account_code": "2100",
                        "amount_cents": amt,
                        "entry_type": JournalLine.EntryType.CREDIT if is_additional else JournalLine.EntryType.DEBIT,
                    }
                )

        for fd in charges.get("fee_details", []):
            amt = abs(fd["amount_cents"])
            if amt > 0:
                journal_lines.append(
                    {
                        "account_code": "2150",
                        "amount_cents": amt,
                        "entry_type": JournalLine.EntryType.CREDIT if is_additional else JournalLine.EntryType.DEBIT,
                    }
                )

        post_journal_entry(
            effective_at=now,
            lines=journal_lines,
            memo=f"Endorsement {endorsement.endorsement_number} for {policy.policy_number}",
            idempotency_key=f"endorsement-{endorsement.id}",
        )

        if is_additional:
            commission_cents = calculate_rate_amount(abs_premium, policy.broker.commission_rate_bps)
            if commission_cents > 0:
                post_journal_entry(
                    effective_at=now,
                    lines=[
                        {
                            "account_code": "5100",
                            "amount_cents": commission_cents,
                            "entry_type": JournalLine.EntryType.DEBIT,
                        },
                        {
                            "account_code": "2200",
                            "amount_cents": commission_cents,
                            "entry_type": JournalLine.EntryType.CREDIT,
                        },
                    ],
                    memo=f"Commission on endorsement {endorsement.endorsement_number}",
                    idempotency_key=f"endorsement-commission-{endorsement.id}",
                )

    policy.premium_amount_cents += endorsement.annual_premium_delta_cents
    policy.save(update_fields=["premium_amount_cents", "updated_at"])

    endorsement.status = Endorsement.Status.APPLIED
    endorsement.save(update_fields=["status", "updated_at"])

    transaction.on_commit(lambda: notify_policy_change(policy, "endorsement.applied"))

    return endorsement


@transaction.atomic
def correct_endorsement(*, endorsement_id: int, corrected_effective_date: date, created_by):
    original = Endorsement.objects.select_for_update().get(id=endorsement_id)

    if original.status != Endorsement.Status.APPLIED:
        raise EndorsementError("Can only correct an applied endorsement")

    policy = original.policy

    if corrected_effective_date < policy.effective_date or corrected_effective_date >= policy.expiration_date:
        raise EndorsementError("Corrected effective date must be within the policy term")

    now = timezone.now()

    from apps.ledger.models import JournalEntry

    original_entry = JournalEntry.objects.filter(idempotency_key=f"endorsement-{original.id}").first()
    if original_entry:
        reverse_journal_entry(
            entry_id=original_entry.id,
            memo=f"Reversal of endorsement {original.endorsement_number} for correction",
            effective_at=now,
            idempotency_key=f"endorsement-reversal-{original.id}",
        )

    original_commission_entry = JournalEntry.objects.filter(
        idempotency_key=f"endorsement-commission-{original.id}"
    ).first()
    if original_commission_entry:
        reverse_journal_entry(
            entry_id=original_commission_entry.id,
            memo=f"Reversal of commission on endorsement {original.endorsement_number}",
            effective_at=now,
            idempotency_key=f"endorsement-commission-reversal-{original.id}",
        )

    policy.premium_amount_cents -= original.annual_premium_delta_cents
    policy.save(update_fields=["premium_amount_cents", "updated_at"])

    original.status = Endorsement.Status.REVERSED
    original.save(update_fields=["status", "updated_at"])

    corrected, charges = create_endorsement(
        policy_id=policy.id,
        endorsement_type=original.endorsement_type,
        effective_date=corrected_effective_date,
        annual_premium_delta_cents=original.annual_premium_delta_cents,
        description=(
            f"Correction of {original.endorsement_number}: effective date changed to {corrected_effective_date}"
        ),
        created_by=created_by,
    )

    corrected.correction_of = original
    corrected.save(update_fields=["correction_of", "updated_at"])

    if corrected.status in (Endorsement.Status.APPROVED, Endorsement.Status.PENDING_PAYMENT):
        apply_endorsement(endorsement_id=corrected.id)
        corrected.refresh_from_db()

    transaction.on_commit(lambda: notify_policy_change(policy, "endorsement.corrected"))

    return corrected
