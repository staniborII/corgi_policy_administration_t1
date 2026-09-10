import logging

from django.db import models, transaction
from django.utils import timezone

from apps.claims.models import Claim, ClaimPayment, PayoutDestination, ReserveEvent
from apps.ledger.models import JournalLine
from apps.ledger.services import post_journal_entry
from apps.policies.models import Policy
from apps.ws.notifications import notify_claim_change

logger = logging.getLogger(__name__)

APPROVAL_THRESHOLD_CENTS = 500_000


class ClaimError(Exception):
    pass


def _next_claim_number():
    last = Claim.objects.order_by("-id").values_list("claim_number", flat=True).first()
    if last:
        seq = int(last.replace("CLM-", "")) + 1
    else:
        seq = 1
    return f"CLM-{seq:06d}"


@transaction.atomic
def submit_claim(*, policy_id, date_of_loss, description, estimated_amount_cents=None, user=None):
    policy = Policy.objects.select_for_update().get(id=policy_id)

    if date_of_loss < policy.effective_date or date_of_loss > policy.expiration_date:
        raise ClaimError("Date of loss must be within policy coverage dates")

    if policy.status not in (Policy.Status.ACTIVE, Policy.Status.CANCELLED, Policy.Status.EXPIRED):
        raise ClaimError(f"Cannot file claim against policy in {policy.status} status")

    claim = Claim.objects.create(
        policy=policy,
        claim_number=_next_claim_number(),
        date_of_loss=date_of_loss,
        description=description,
        estimated_amount_cents=estimated_amount_cents,
        created_by=user,
    )
    logger.info(f"Claim created: claim_id={claim.id}, policy_id={policy_id}")

    transaction.on_commit(lambda: notify_claim_change(claim, "claim.created"))

    return claim


@transaction.atomic
def set_reserve(*, claim_id, amount_cents, reserve_type, memo="", user=None):
    claim = Claim.objects.select_for_update().get(id=claim_id)

    if claim.status == Claim.Status.CLOSED:
        raise ClaimError("Cannot set reserve on a closed claim")

    if reserve_type == ReserveEvent.ReserveType.INITIAL:
        if claim.reserve_events.exists():
            raise ClaimError("Initial reserve already exists; use ADJUSTMENT")

    event = ReserveEvent.objects.create(
        claim=claim,
        amount_cents=amount_cents,
        reserve_type=reserve_type,
        effective_at=timezone.now(),
        created_by=user,
        memo=memo,
    )

    now = timezone.now()
    if amount_cents > 0:
        post_journal_entry(
            effective_at=now,
            lines=[
                {"account_code": "5000", "amount_cents": amount_cents, "entry_type": JournalLine.EntryType.DEBIT},
                {"account_code": "2300", "amount_cents": amount_cents, "entry_type": JournalLine.EntryType.CREDIT},
            ],
            memo=f"Reserve {reserve_type} for {claim.claim_number}: +{amount_cents}¢",
            idempotency_key=f"reserve-{event.id}",
        )
    elif amount_cents < 0:
        release_amount = abs(amount_cents)
        post_journal_entry(
            effective_at=now,
            lines=[
                {"account_code": "2300", "amount_cents": release_amount, "entry_type": JournalLine.EntryType.DEBIT},
                {"account_code": "5000", "amount_cents": release_amount, "entry_type": JournalLine.EntryType.CREDIT},
            ],
            memo=f"Reserve {reserve_type} for {claim.claim_number}: -{release_amount}¢",
            idempotency_key=f"reserve-{event.id}",
        )

    logger.info(f"Reserve event added: claim_id={claim_id}, type={reserve_type}, amount={amount_cents}")

    if claim.status == Claim.Status.OPEN:
        claim.status = Claim.Status.RESERVED
        claim.save(update_fields=["status", "updated_at"])

    transaction.on_commit(lambda: notify_claim_change(claim, "claim.reserve_set"))

    return event


def get_reserve_balance(claim_id):
    result = ReserveEvent.objects.filter(claim_id=claim_id).aggregate(total=models.Sum("amount_cents"))
    return result["total"] or 0


def get_paid_total(claim_id):
    result = ClaimPayment.objects.filter(claim_id=claim_id, status=ClaimPayment.Status.SETTLED).aggregate(
        total=models.Sum("amount_cents")
    )
    return result["total"] or 0


def get_claim_financials(claim_id):
    reserve = get_reserve_balance(claim_id)
    paid = get_paid_total(claim_id)
    return {
        "reserve_cents": reserve,
        "paid_cents": paid,
        "incurred_cents": paid + reserve,
    }


@transaction.atomic
def create_claim_payment(*, claim_id, amount_cents, payee, user=None):
    claim = Claim.objects.select_for_update().get(id=claim_id)
    policy = claim.policy

    if claim.status == Claim.Status.CLOSED:
        raise ClaimError("Cannot create payment on a closed claim")

    existing_paid = get_paid_total(claim_id)
    pending_amount = (
        ClaimPayment.objects.filter(
            claim_id=claim_id,
            status__in=[
                ClaimPayment.Status.DRAFT,
                ClaimPayment.Status.PENDING_APPROVAL,
                ClaimPayment.Status.APPROVED,
                ClaimPayment.Status.PENDING,
            ],
        ).aggregate(total=models.Sum("amount_cents"))["total"]
        or 0
    )

    if existing_paid + pending_amount + amount_cents > policy.coverage_limit_cents:
        raise ClaimError(
            f"Payment of {amount_cents}¢ would exceed policy limit of {policy.coverage_limit_cents}¢ "
            f"(already paid/pending: {existing_paid + pending_amount}¢)"
        )

    needs_approval = amount_cents >= APPROVAL_THRESHOLD_CENTS

    payment = ClaimPayment.objects.create(
        claim=claim,
        amount_cents=amount_cents,
        status=ClaimPayment.Status.PENDING_APPROVAL if needs_approval else ClaimPayment.Status.APPROVED,
        payee=payee,
        effective_at=timezone.now(),
        created_by=user,
    )

    if needs_approval:
        from apps.approvals.services import create_approval

        create_approval(content_object=payment, action="CLAIM_PAYMENT", requested_by=user)

    approval_status = "pending_approval" if needs_approval else "auto_approved"
    logger.info(
        "Claim payment created: payment_id=%s, claim_id=%s, amount=%s, status=%s",
        payment.id,
        claim_id,
        amount_cents,
        approval_status,
    )

    if claim.status in (Claim.Status.OPEN, Claim.Status.RESERVED):
        claim.status = Claim.Status.PAYMENT_PENDING
        claim.save(update_fields=["status", "updated_at"])

    transaction.on_commit(lambda: notify_claim_change(claim, "claim.payment_created"))

    return payment


@transaction.atomic
def approve_claim_payment(*, payment_id, user):
    payment = ClaimPayment.objects.select_for_update().get(id=payment_id)

    if payment.status != ClaimPayment.Status.PENDING_APPROVAL:
        raise ClaimError(f"Payment is in {payment.status} status, not PENDING_APPROVAL")

    if payment.created_by_id == user.id:
        raise ClaimError("Maker cannot approve their own payment")

    from apps.approvals.services import approve_approval

    approve_approval(content_object=payment, decided_by=user)

    payment.status = ClaimPayment.Status.APPROVED
    payment.approved_by = user
    payment.save(update_fields=["status", "approved_by", "updated_at"])

    logger.info(f"Claim payment approved: payment_id={payment_id}, approved_by={user.id}")

    transaction.on_commit(lambda: notify_claim_change(payment.claim, "claim.payment_approved"))

    return payment


@transaction.atomic
def execute_payout(*, payment_id, user=None):
    payment = ClaimPayment.objects.select_for_update().get(id=payment_id)

    if payment.status != ClaimPayment.Status.APPROVED:
        raise ClaimError(f"Payment must be APPROVED to execute payout, currently {payment.status}")

    claim = payment.claim

    try:
        dest = claim.payout_destination
    except PayoutDestination.DoesNotExist as exc:
        raise ClaimError("No payout destination set for this claim") from exc

    if dest.verification_status != PayoutDestination.VerificationStatus.VERIFIED:
        raise ClaimError(f"Payout destination is {dest.verification_status}, must be VERIFIED")

    from apps.claims.simulators import simulate_payout

    payout_ref = simulate_payout(payment)

    payment.status = ClaimPayment.Status.PENDING
    payment.payout_reference = payout_ref
    payment.save(update_fields=["status", "payout_reference", "updated_at"])

    logger.info(f"Payout executed: payment_id={payment_id}, provider_reference={payout_ref}")

    transaction.on_commit(lambda: notify_claim_change(claim, "claim.payout_executed"))

    return payment


@transaction.atomic
def handle_payout_settled(*, payout_reference, amount_cents):
    payment = ClaimPayment.objects.select_for_update().get(payout_reference=payout_reference)

    if payment.status == ClaimPayment.Status.SETTLED:
        return payment

    if payment.status != ClaimPayment.Status.PENDING:
        raise ClaimError(f"Cannot settle payment in {payment.status} status")

    now = timezone.now()
    post_journal_entry(
        effective_at=now,
        lines=[
            {"account_code": "2300", "amount_cents": payment.amount_cents, "entry_type": JournalLine.EntryType.DEBIT},
            {"account_code": "1000", "amount_cents": payment.amount_cents, "entry_type": JournalLine.EntryType.CREDIT},
        ],
        memo=f"Claim payout settled: {payment.claim.claim_number} ref={payout_reference}",
        idempotency_key=f"payout-settled-{payout_reference}",
    )

    payment.status = ClaimPayment.Status.SETTLED
    payment.save(update_fields=["status", "updated_at"])

    logger.info(f"Payout settled: payment_id={payment.id}, provider_reference={payout_reference}")

    _update_claim_status_after_payment(payment.claim)

    transaction.on_commit(lambda: notify_claim_change(payment.claim, "claim.payout_settled"))

    return payment


@transaction.atomic
def handle_payout_returned(*, payout_reference, reason=""):
    payment = ClaimPayment.objects.select_for_update().get(payout_reference=payout_reference)

    if payment.status == ClaimPayment.Status.RETURNED:
        return payment

    if payment.status not in (ClaimPayment.Status.PENDING, ClaimPayment.Status.SETTLED):
        raise ClaimError(f"Cannot return payment in {payment.status} status")

    was_settled = payment.status == ClaimPayment.Status.SETTLED

    if was_settled:
        now = timezone.now()
        post_journal_entry(
            effective_at=now,
            lines=[
                {
                    "account_code": "1000",
                    "amount_cents": payment.amount_cents,
                    "entry_type": JournalLine.EntryType.DEBIT,
                },
                {
                    "account_code": "2300",
                    "amount_cents": payment.amount_cents,
                    "entry_type": JournalLine.EntryType.CREDIT,
                },
            ],
            memo=f"Payout returned: {payment.claim.claim_number} ref={payout_reference} reason={reason}",
            idempotency_key=f"payout-returned-{payout_reference}",
        )

    payment.status = ClaimPayment.Status.RETURNED
    payment.save(update_fields=["status", "updated_at"])

    logger.warning(f"Payout returned: payment_id={payment.id}, provider_reference={payout_reference}, reason={reason}")

    _update_claim_status_after_payment(payment.claim)

    transaction.on_commit(lambda: notify_claim_change(payment.claim, "claim.payout_returned"))

    return payment


@transaction.atomic
def handle_payout_failed(*, payout_reference, reason=""):
    payment = ClaimPayment.objects.select_for_update().get(payout_reference=payout_reference)

    if payment.status == ClaimPayment.Status.FAILED:
        return payment

    if payment.status != ClaimPayment.Status.PENDING:
        raise ClaimError(f"Cannot fail payment in {payment.status} status")

    payment.status = ClaimPayment.Status.FAILED
    payment.save(update_fields=["status", "updated_at"])

    transaction.on_commit(lambda: notify_claim_change(payment.claim, "claim.payout_failed"))

    return payment


def _update_claim_status_after_payment(claim):
    payments = claim.claim_payments.all()
    settled_total = sum(p.amount_cents for p in payments if p.status == ClaimPayment.Status.SETTLED)
    reserve = get_reserve_balance(claim.id)

    if settled_total > 0 and settled_total >= reserve:
        claim.status = Claim.Status.PAID
    elif settled_total > 0:
        claim.status = Claim.Status.PARTIALLY_PAID
    else:
        claim.status = Claim.Status.PAYMENT_PENDING

    claim.save(update_fields=["status", "updated_at"])


@transaction.atomic
def set_payout_destination(*, claim_id, payee_name, account_last_four):
    claim = Claim.objects.get(id=claim_id)

    dest, created = PayoutDestination.objects.update_or_create(
        claim=claim,
        defaults={
            "payee_name": payee_name,
            "account_last_four": account_last_four,
            "verification_status": PayoutDestination.VerificationStatus.PENDING,
            "provider": "SIMULATED",
        },
    )
    return dest


@transaction.atomic
def verify_payout_destination(*, claim_id, outcome="VERIFIED"):
    dest = PayoutDestination.objects.select_for_update().get(claim_id=claim_id)

    if outcome not in ("VERIFIED", "FAILED"):
        raise ClaimError(f"Invalid verification outcome: {outcome}")

    dest.verification_status = outcome
    if outcome == "VERIFIED":
        dest.verified_at = timezone.now()
    dest.save(update_fields=["verification_status", "verified_at", "updated_at"])

    claim = dest.claim
    transaction.on_commit(lambda: notify_claim_change(claim, "claim.destination_verified"))

    return dest
