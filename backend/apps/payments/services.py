import logging
import uuid
from datetime import date

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.integrations.stripe.client import create_checkout_session
from apps.ledger.models import JournalLine
from apps.ledger.services import post_journal_entry
from apps.payments.models import Payment, Refund
from apps.policies.models import Policy, PolicyEvent
from apps.policies.services import calculate_rate_amount, compute_policy_charges

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    pass


@transaction.atomic
def create_checkout_for_policy(*, policy_id, requested_by):
    """
    Create a Stripe Checkout Session for a policy's initial premium payment.
    Transitions policy DRAFT -> PENDING_PAYMENT and creates a Payment record.
    """
    policy = Policy.objects.select_for_update().get(id=policy_id)

    if policy.status not in (Policy.Status.DRAFT, Policy.Status.PENDING_PAYMENT):
        raise PaymentError(f"Policy {policy.policy_number} is not in a payable state (status: {policy.status})")

    if policy.effective_date < date.today():
        raise PaymentError(
            f"Policy {policy.policy_number} effective date ({policy.effective_date}) has passed. "
            "Staff must re-issue with a new effective date."
        )

    if policy.status == Policy.Status.PENDING_PAYMENT:
        existing = Payment.objects.filter(policy=policy, status=Payment.Status.PENDING).first()
        if existing and existing.stripe_checkout_session_id:
            raise PaymentError("A payment is already pending for this policy")

    charges = compute_policy_charges(
        premium_cents=policy.premium_amount_cents,
        jurisdiction=policy.coverage_territory,
        effective_date=policy.effective_date,
    )

    total_cents = charges["total_cents"]

    frontend_url = settings.FRONTEND_URL
    success_url = f"{frontend_url}/customer/payment-success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{frontend_url}/customer/payment-cancel"

    checkout = create_checkout_session(
        amount_cents=total_cents,
        metadata={
            "policy_id": str(policy.id),
            "policy_number": policy.policy_number,
        },
        success_url=success_url,
        cancel_url=cancel_url,
    )

    idempotency_key = f"policy-initial-{policy.id}-{uuid.uuid4().hex[:8]}"
    now = timezone.now()

    payment = Payment.objects.create(
        policy=policy,
        amount_cents=total_cents,
        status=Payment.Status.PENDING,
        stripe_checkout_session_id=checkout["session_id"],
        charges_snapshot=charges,
        idempotency_key=idempotency_key,
        effective_at=now,
    )

    if policy.status == Policy.Status.DRAFT:
        policy.status = Policy.Status.PENDING_PAYMENT
        policy.save(update_fields=["status", "updated_at"])

        PolicyEvent.objects.create(
            policy=policy,
            event_type=PolicyEvent.EventType.PAYMENT_REQUESTED,
            effective_at=now,
            created_by=requested_by,
            data={
                "payment_id": payment.id,
                "charges": charges,
                "checkout_session_id": checkout["session_id"],
                "simulated": checkout["simulated"],
            },
        )

    logger.info(
        "Checkout created: policy_id=%s, amount=%s, ref=%s",
        policy_id,
        total_cents,
        checkout["session_id"],
    )

    return {
        "payment_id": payment.id,
        "checkout_url": checkout["checkout_url"],
        "session_id": checkout["session_id"],
        "simulated": checkout["simulated"],
        "charges": charges,
    }


@transaction.atomic
def handle_payment_success(*, payment_id, stripe_payment_intent_id=""):
    """
    Process a successful payment: update Payment, post ledger entries,
    activate policy, book commission.
    """
    payment = Payment.objects.select_for_update().get(id=payment_id)

    if payment.status == Payment.Status.SUCCEEDED:
        logger.info("Payment %s already succeeded — idempotent skip", payment_id)
        return payment

    if payment.status != Payment.Status.PENDING:
        raise PaymentError(f"Payment {payment_id} is not in PENDING state (status: {payment.status})")

    payment.status = Payment.Status.SUCCEEDED
    payment.stripe_payment_intent_id = stripe_payment_intent_id
    payment.save(update_fields=["status", "stripe_payment_intent_id", "updated_at"])

    charges = payment.charges_snapshot
    policy = payment.policy
    now = timezone.now()

    journal_lines = [
        {
            "account_code": "1010",
            "amount_cents": charges["total_cents"],
            "entry_type": JournalLine.EntryType.DEBIT,
        },
        {
            "account_code": "2000",
            "amount_cents": charges["premium_cents"],
            "entry_type": JournalLine.EntryType.CREDIT,
        },
    ]

    for tax_detail in charges.get("tax_details", []):
        journal_lines.append(
            {
                "account_code": "2100",
                "amount_cents": tax_detail["amount_cents"],
                "entry_type": JournalLine.EntryType.CREDIT,
            }
        )

    for fee_detail in charges.get("fee_details", []):
        journal_lines.append(
            {
                "account_code": "2150",
                "amount_cents": fee_detail["amount_cents"],
                "entry_type": JournalLine.EntryType.CREDIT,
            }
        )

    post_journal_entry(
        effective_at=now,
        lines=journal_lines,
        memo=f"Premium collection for {policy.policy_number}",
        idempotency_key=f"premium-collection-{payment.id}",
    )

    commission_cents = calculate_rate_amount(charges["premium_cents"], policy.broker.commission_rate_bps)

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
            memo=f"Broker commission for {policy.policy_number}",
            idempotency_key=f"commission-{payment.id}",
        )

    policy.status = Policy.Status.ACTIVE
    policy.save(update_fields=["status", "updated_at"])

    PolicyEvent.objects.create(
        policy=policy,
        event_type=PolicyEvent.EventType.ACTIVATED,
        effective_at=now,
        data={
            "payment_id": payment.id,
            "commission_cents": commission_cents,
            "stripe_payment_intent_id": stripe_payment_intent_id,
        },
    )

    logger.info(
        "Payment success: payment_id=%s, policy_id=%s, ref=%s",
        payment_id,
        policy.id,
        stripe_payment_intent_id,
    )

    return payment


@transaction.atomic
def handle_payment_failure(*, payment_id, reason=""):
    """Mark a payment as failed. Policy stays in PENDING_PAYMENT for retry."""
    payment = Payment.objects.select_for_update().get(id=payment_id)

    if payment.status in (Payment.Status.SUCCEEDED, Payment.Status.FAILED):
        return payment

    payment.status = Payment.Status.FAILED
    payment.save(update_fields=["status", "updated_at"])

    return payment


@transaction.atomic
def simulate_payment_success(*, payment_id):
    """
    For SIMULATED mode only: directly complete a payment without Stripe.
    Only works when STRIPE_SECRET_KEY is not configured.
    """
    if settings.STRIPE_SECRET_KEY:
        raise PaymentError("Cannot simulate payment when Stripe is configured — use real Stripe flow")

    payment = Payment.objects.get(id=payment_id)

    if not payment.stripe_checkout_session_id.startswith("SIMULATED"):
        raise PaymentError("Cannot simulate a real Stripe payment")

    return handle_payment_success(
        payment_id=payment_id,
        stripe_payment_intent_id=f"SIMULATED-pi-{uuid.uuid4().hex[:12]}",
    )


@transaction.atomic
def handle_refund_success(*, refund_id):
    """
    Process a confirmed refund: post ledger entries for the premium refund,
    tax/fee refunds, and commission clawback.
    """
    refund = Refund.objects.select_for_update().get(id=refund_id)

    if refund.status == Refund.Status.SUCCEEDED:
        logger.info("Refund %s already succeeded — idempotent skip", refund_id)
        return refund

    if refund.status != Refund.Status.PENDING:
        raise PaymentError(f"Refund {refund_id} is not in PENDING state (status: {refund.status})")

    refund.status = Refund.Status.SUCCEEDED
    refund.save(update_fields=["status", "updated_at"])

    charges = refund.charges_snapshot or {}
    policy = refund.payment.policy
    now = timezone.now()

    unearned_premium = charges.get("unearned_premium_cents", 0)
    total_refundable_tax = charges.get("total_refundable_tax_cents", 0)
    total_refundable_fees = charges.get("total_refundable_fees_cents", 0)

    journal_lines = []

    if unearned_premium > 0:
        journal_lines.append(
            {"account_code": "2000", "amount_cents": unearned_premium, "entry_type": JournalLine.EntryType.DEBIT}
        )

    if total_refundable_tax > 0:
        journal_lines.append(
            {"account_code": "2100", "amount_cents": total_refundable_tax, "entry_type": JournalLine.EntryType.DEBIT}
        )

    if total_refundable_fees > 0:
        journal_lines.append(
            {"account_code": "2150", "amount_cents": total_refundable_fees, "entry_type": JournalLine.EntryType.DEBIT}
        )

    total_refund = unearned_premium + total_refundable_tax + total_refundable_fees
    if total_refund > 0:
        journal_lines.append(
            {"account_code": "2400", "amount_cents": total_refund, "entry_type": JournalLine.EntryType.CREDIT}
        )

        post_journal_entry(
            effective_at=now,
            lines=journal_lines,
            memo=f"Cancellation refund for {policy.policy_number}",
            idempotency_key=f"cancellation-refund-{refund.id}",
        )

    logger.info(f"Refund success handled: refund_id={refund_id}, provider_reference={refund.stripe_refund_id}")

    commission_clawback = charges.get("commission_clawback_cents", 0)
    if commission_clawback > 0:
        post_journal_entry(
            effective_at=now,
            lines=[
                {
                    "account_code": "2200",
                    "amount_cents": commission_clawback,
                    "entry_type": JournalLine.EntryType.DEBIT,
                },
                {
                    "account_code": "4200",
                    "amount_cents": commission_clawback,
                    "entry_type": JournalLine.EntryType.CREDIT,
                },
            ],
            memo=f"Commission clawback for {policy.policy_number}",
            idempotency_key=f"commission-clawback-{refund.id}",
        )

    return refund


@transaction.atomic
def handle_refund_failure(*, refund_id, reason=""):
    """Mark a refund as failed."""
    refund = Refund.objects.select_for_update().get(id=refund_id)

    if refund.status in (Refund.Status.SUCCEEDED, Refund.Status.FAILED):
        return refund

    refund.status = Refund.Status.FAILED
    refund.save(update_fields=["status", "updated_at"])
    return refund


@transaction.atomic
def simulate_refund_success(*, refund_id):
    """For SIMULATED mode only: directly complete a refund without Stripe."""
    if settings.STRIPE_SECRET_KEY:
        raise PaymentError("Cannot simulate refund when Stripe is configured")

    refund = Refund.objects.get(id=refund_id)

    if not refund.stripe_refund_id.startswith("SIMULATED"):
        raise PaymentError("Cannot simulate a real Stripe refund")

    return handle_refund_success(refund_id=refund_id)
