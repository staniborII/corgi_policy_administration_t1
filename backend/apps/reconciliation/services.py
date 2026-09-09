from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.payments.models import Payment, Refund
from apps.policies.models import Policy
from apps.policies.services import calculate_rate_amount
from apps.reconciliation.models import BrokerStatement


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
