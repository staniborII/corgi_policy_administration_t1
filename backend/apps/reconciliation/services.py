import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.payments.models import Payment, Refund
from apps.policies.models import Policy
from apps.policies.services import calculate_rate_amount
from apps.reconciliation.models import BrokerStatement, ReconciliationBreak, ReconciliationRun

logger = logging.getLogger(__name__)


class StatementError(Exception):
    pass


@transaction.atomic
def generate_broker_statement(*, broker, period_start: date, period_end: date):
    """
    Generate a monthly broker statement.
    If a statement already exists for this broker/period, return it unchanged (reproducible).
    """
    existing = BrokerStatement.objects.filter(broker=broker, period_start=period_start, period_end=period_end).first()

    if existing:
        return existing

    policies = Policy.objects.filter(broker=broker)
    policy_ids = list(policies.values_list("id", flat=True))

    succeeded_payments = Payment.objects.filter(
        policy_id__in=policy_ids,
        status=Payment.Status.SUCCEEDED,
        effective_at__date__gte=period_start,
        effective_at__date__lte=period_end,
    )

    succeeded_refunds = Refund.objects.filter(
        payment__policy_id__in=policy_ids,
        status=Refund.Status.SUCCEEDED,
        effective_at__date__gte=period_start,
        effective_at__date__lte=period_end,
    ).select_related("payment__policy__broker")

    payment_details = []
    total_premium = 0
    total_commission = 0

    for payment in succeeded_payments.select_related("policy__broker"):
        charges = payment.charges_snapshot or {}
        premium = charges.get("premium_cents", 0)
        commission = calculate_rate_amount(premium, payment.policy.broker.commission_rate_bps)
        total_premium += premium
        total_commission += commission
        payment_details.append(
            {
                "payment_id": payment.id,
                "policy_number": payment.policy.policy_number,
                "premium_cents": premium,
                "total_cents": payment.amount_cents,
                "commission_cents": commission,
                "effective_at": payment.effective_at.isoformat(),
            }
        )

    refund_details = []
    total_clawback = 0

    for refund in succeeded_refunds:
        charges = refund.charges_snapshot or {}
        clawback = charges.get("commission_clawback_cents", 0)
        total_clawback += clawback
        refund_details.append(
            {
                "refund_id": refund.id,
                "policy_number": refund.payment.policy.policy_number,
                "refund_cents": refund.amount_cents,
                "clawback_cents": clawback,
                "effective_at": refund.effective_at.isoformat(),
            }
        )

    net_due = total_commission - total_clawback

    statement = BrokerStatement.objects.create(
        broker=broker,
        period_start=period_start,
        period_end=period_end,
        total_premium_cents=total_premium,
        total_commission_cents=total_commission,
        total_clawback_cents=total_clawback,
        net_due_cents=net_due,
        statement_data={
            "payments": payment_details,
            "refunds": refund_details,
            "generated_at": timezone.now().isoformat(),
        },
    )

    return statement


def _get_provider_payments():
    """
    Fetch provider truth for payments.
    In SIMULATED mode, returns local records as the "provider" truth.
    With real Stripe, would call stripe.PaymentIntent.list().
    """
    from django.conf import settings

    if not settings.STRIPE_SECRET_KEY:
        return {
            p.stripe_payment_intent_id: {
                "id": p.stripe_payment_intent_id,
                "amount": p.amount_cents,
                "status": "succeeded",
            }
            for p in Payment.objects.filter(status=Payment.Status.SUCCEEDED)
        }

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    provider_map = {}
    payment_intents = stripe.PaymentIntent.list(limit=100)
    for pi in payment_intents.auto_paging_iter():
        provider_map[pi.id] = {"id": pi.id, "amount": pi.amount, "status": pi.status}
    return provider_map


def _get_provider_refunds():
    """
    Fetch provider truth for refunds.
    In SIMULATED mode, returns local succeeded refunds as "provider" truth.
    """
    from django.conf import settings

    if not settings.STRIPE_SECRET_KEY:
        return {
            r.stripe_refund_id: {"id": r.stripe_refund_id, "amount": r.amount_cents, "status": "succeeded"}
            for r in Refund.objects.filter(status=Refund.Status.SUCCEEDED)
        }

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    provider_map = {}
    refunds = stripe.Refund.list(limit=100)
    for rf in refunds.auto_paging_iter():
        provider_map[rf.id] = {"id": rf.id, "amount": rf.amount, "status": rf.status}
    return provider_map


def run_reconciliation(*, run_date=None):
    """
    Run a reconciliation comparing local payment/refund records against provider truth.
    Creates a ReconciliationRun and any detected breaks.
    Run record persists even on failure (not wrapped in outer atomic).
    """
    if run_date is None:
        run_date = date.today()

    now = timezone.now()
    recon_run = ReconciliationRun.objects.create(run_date=run_date, status=ReconciliationRun.Status.RUNNING)

    logger.info(f"Reconciliation run started: run_id={recon_run.id}")

    try:
        with transaction.atomic():
            breaks_found = _reconcile_records(recon_run, now)

        recon_run.status = ReconciliationRun.Status.COMPLETED
        recon_run.completed_at = now
        recon_run.summary = {
            "breaks_found": breaks_found,
        }
        recon_run.save(update_fields=["status", "completed_at", "summary"])

        logger.info(
            "Reconciliation completed: run_id=%s, breaks=%s",
            recon_run.id,
            breaks_found,
        )

    except Exception as exc:
        logger.exception("Reconciliation run %s failed", recon_run.id)
        recon_run.status = ReconciliationRun.Status.FAILED
        recon_run.completed_at = timezone.now()
        recon_run.summary = {"error": str(exc)}
        recon_run.save(update_fields=["status", "completed_at", "summary"])
        raise

    return recon_run


def _reconcile_records(recon_run, now):
    """Core reconciliation logic, runs inside an atomic block."""
    breaks_found = 0
    provider_payments = _get_provider_payments()
    provider_refunds = _get_provider_refunds()

    local_payments = Payment.objects.filter(
        status__in=[Payment.Status.SUCCEEDED, Payment.Status.PENDING],
    ).exclude(stripe_payment_intent_id="")

    local_seen_pi_ids = set()

    for payment in local_payments:
        pi_id = payment.stripe_payment_intent_id
        local_seen_pi_ids.add(pi_id)

        if pi_id.startswith("SIMULATED"):
            continue

        if pi_id not in provider_payments:
            ReconciliationBreak.objects.create(
                run=recon_run,
                break_type=ReconciliationBreak.BreakType.MISSING_IN_PROVIDER,
                description=f"Local payment {payment.id} ({pi_id}) not found at Stripe",
                source="STRIPE",
                local_reference=str(payment.id),
                external_reference=pi_id,
                expected_amount_cents=payment.amount_cents,
                first_seen_at=now,
            )
            logger.warning(
                "Break: MISSING_IN_PROVIDER amount=%s ref=%s",
                payment.amount_cents,
                pi_id,
            )
            breaks_found += 1
            continue

        provider_data = provider_payments[pi_id]

        if payment.status == Payment.Status.SUCCEEDED and provider_data["status"] != "succeeded":
            ReconciliationBreak.objects.create(
                run=recon_run,
                break_type=ReconciliationBreak.BreakType.STATUS_MISMATCH,
                description=(f"Payment {payment.id}: local=SUCCEEDED, provider={provider_data['status']}"),
                source="STRIPE",
                local_reference=str(payment.id),
                external_reference=pi_id,
                first_seen_at=now,
            )
            logger.warning("Break: STATUS_MISMATCH ref=%s", pi_id)
            breaks_found += 1

        if payment.amount_cents != provider_data["amount"]:
            ReconciliationBreak.objects.create(
                run=recon_run,
                break_type=ReconciliationBreak.BreakType.AMOUNT_MISMATCH,
                description=(
                    f"Payment {payment.id}: local={payment.amount_cents}¢, provider={provider_data['amount']}¢"
                ),
                source="STRIPE",
                local_reference=str(payment.id),
                external_reference=pi_id,
                expected_amount_cents=payment.amount_cents,
                actual_amount_cents=provider_data["amount"],
                first_seen_at=now,
            )
            logger.warning(
                "Break: AMOUNT_MISMATCH amount=%s ref=%s",
                payment.amount_cents,
                pi_id,
            )
            breaks_found += 1

    for pi_id, provider_data in provider_payments.items():
        if pi_id not in local_seen_pi_ids and provider_data["status"] == "succeeded":
            ReconciliationBreak.objects.create(
                run=recon_run,
                break_type=ReconciliationBreak.BreakType.MISSING_IN_LEDGER,
                description=f"Provider payment {pi_id} not found locally",
                source="STRIPE",
                external_reference=pi_id,
                actual_amount_cents=provider_data["amount"],
                first_seen_at=now,
            )
            logger.warning(
                "Break: MISSING_IN_LEDGER amount=%s ref=%s",
                provider_data["amount"],
                pi_id,
            )
            breaks_found += 1

    local_refunds = Refund.objects.filter(
        status__in=[Refund.Status.SUCCEEDED, Refund.Status.PENDING],
    ).exclude(stripe_refund_id="")

    local_seen_rf_ids = set()

    for refund in local_refunds:
        rf_id = refund.stripe_refund_id
        local_seen_rf_ids.add(rf_id)

        if rf_id.startswith("SIMULATED"):
            continue

        if rf_id not in provider_refunds:
            ReconciliationBreak.objects.create(
                run=recon_run,
                break_type=ReconciliationBreak.BreakType.MISSING_IN_PROVIDER,
                description=f"Local refund {refund.id} ({rf_id}) not found at Stripe",
                source="STRIPE",
                local_reference=str(refund.id),
                external_reference=rf_id,
                expected_amount_cents=refund.amount_cents,
                first_seen_at=now,
            )
            logger.warning(
                "Break: MISSING_IN_PROVIDER amount=%s ref=%s",
                refund.amount_cents,
                rf_id,
            )
            breaks_found += 1

        elif refund.amount_cents != provider_refunds[rf_id]["amount"]:
            ReconciliationBreak.objects.create(
                run=recon_run,
                break_type=ReconciliationBreak.BreakType.AMOUNT_MISMATCH,
                description=(
                    f"Refund {refund.id}: local={refund.amount_cents}¢, provider={provider_refunds[rf_id]['amount']}¢"
                ),
                source="STRIPE",
                local_reference=str(refund.id),
                external_reference=rf_id,
                expected_amount_cents=refund.amount_cents,
                actual_amount_cents=provider_refunds[rf_id]["amount"],
                first_seen_at=now,
            )
            logger.warning(
                "Break: AMOUNT_MISMATCH amount=%s ref=%s",
                refund.amount_cents,
                rf_id,
            )
            breaks_found += 1

    for rf_id, provider_data in provider_refunds.items():
        if rf_id not in local_seen_rf_ids and provider_data["status"] == "succeeded":
            ReconciliationBreak.objects.create(
                run=recon_run,
                break_type=ReconciliationBreak.BreakType.MISSING_IN_LEDGER,
                description=f"Provider refund {rf_id} not found locally",
                source="STRIPE",
                external_reference=rf_id,
                actual_amount_cents=provider_data["amount"],
                first_seen_at=now,
            )
            logger.warning(
                "Break: MISSING_IN_LEDGER amount=%s ref=%s",
                provider_data["amount"],
                rf_id,
            )
            breaks_found += 1

    return breaks_found


def resolve_break(*, break_id, resolved_by, notes=""):
    """Mark a reconciliation break as resolved."""
    brk = ReconciliationBreak.objects.get(id=break_id)
    brk.status = ReconciliationBreak.Status.RESOLVED
    brk.resolved = True
    brk.resolution_notes = notes
    brk.resolved_by = resolved_by
    brk.resolved_at = timezone.now()
    brk.save(update_fields=["status", "resolved", "resolution_notes", "resolved_by", "resolved_at"])
    return brk
