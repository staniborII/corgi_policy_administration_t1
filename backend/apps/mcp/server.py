"""
Corgi Policy Administration MCP Server.

Provides 3 read tools and 1 write tool for agent interaction.
The write tool creates approval requests — it never moves money directly.

Safety rules:
- Agent cannot approve its own action
- Agent cannot bypass maker-checker
- Agent cannot alter posted ledger entries
- Agent cannot delete financial history
- Every state-changing request enters the normal approval queue
"""

import os
import sys

import django


def _bootstrap_django():
    """Initialize Django settings before importing any models."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


_bootstrap_django()

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("corgi-policy-admin")


@mcp.tool()
def read_policy(policy_id: int) -> dict:
    """Read policy details including status, dates, premium, events, and endorsements."""
    from apps.endorsements.models import Endorsement
    from apps.policies.models import Policy, PolicyEvent

    try:
        policy = Policy.objects.select_related("customer", "broker").get(id=policy_id)
    except Policy.DoesNotExist:
        return {"error": f"Policy {policy_id} not found"}

    events = PolicyEvent.objects.filter(policy=policy).order_by("-effective_at")[:20]
    endorsements = Endorsement.objects.filter(policy=policy).order_by("-effective_date")[:20]

    return {
        "policy": {
            "id": policy.id,
            "policy_number": policy.policy_number,
            "status": policy.status,
            "effective_date": str(policy.effective_date),
            "expiration_date": str(policy.expiration_date),
            "premium_amount_cents": policy.premium_amount_cents,
            "coverage_territory": policy.coverage_territory,
            "customer": policy.customer.username,
            "broker": policy.broker.company_name,
        },
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "effective_at": e.effective_at.isoformat(),
                "data": e.data,
            }
            for e in events
        ],
        "endorsements": [
            {
                "id": e.id,
                "endorsement_number": e.endorsement_number,
                "status": e.status,
                "endorsement_type": e.endorsement_type,
                "effective_date": str(e.effective_date),
                "premium_change_cents": e.premium_change_cents,
            }
            for e in endorsements
        ],
    }


@mcp.tool()
def read_claim(claim_id: int) -> dict:
    """Read claim details including reserve events, payments, and financial summary."""
    from apps.claims.models import Claim, ClaimPayment, ReserveEvent

    try:
        claim = Claim.objects.select_related("policy").get(id=claim_id)
    except Claim.DoesNotExist:
        return {"error": f"Claim {claim_id} not found"}

    reserve_events = ReserveEvent.objects.filter(claim=claim).order_by("-effective_at")[:20]
    payments = ClaimPayment.objects.filter(claim=claim).order_by("-created_at")[:20]

    reserve_balance = sum(e.amount_cents for e in ReserveEvent.objects.filter(claim=claim))
    paid_total = sum(
        p.amount_cents for p in ClaimPayment.objects.filter(claim=claim, status__in=["SETTLED", "APPROVED", "PENDING"])
    )

    return {
        "claim": {
            "id": claim.id,
            "claim_number": claim.claim_number,
            "status": claim.status,
            "policy_number": claim.policy.policy_number,
            "date_of_loss": str(claim.date_of_loss),
            "description": claim.description,
            "estimated_amount_cents": claim.estimated_amount_cents,
        },
        "financials": {
            "reserve_cents": reserve_balance,
            "paid_cents": paid_total,
            "incurred_cents": paid_total + reserve_balance,
        },
        "reserve_events": [
            {
                "id": e.id,
                "amount_cents": e.amount_cents,
                "reserve_type": e.reserve_type,
                "effective_at": e.effective_at.isoformat(),
                "memo": e.memo,
            }
            for e in reserve_events
        ],
        "payments": [
            {
                "id": p.id,
                "amount_cents": p.amount_cents,
                "status": p.status,
                "payee": p.payee,
                "payout_reference": p.payout_reference,
            }
            for p in payments
        ],
    }


@mcp.tool()
def read_reconciliation_breaks(status_filter: str = "OPEN") -> dict:
    """Read reconciliation breaks, optionally filtered by status (OPEN, ACKNOWLEDGED, RESOLVED)."""
    from apps.reconciliation.models import ReconciliationBreak, ReconciliationRun

    breaks = ReconciliationBreak.objects.select_related("run").order_by("-created_at")
    if status_filter:
        breaks = breaks.filter(status=status_filter)
    breaks = breaks[:50]

    latest_run = ReconciliationRun.objects.order_by("-started_at").first()

    return {
        "latest_run": {
            "id": latest_run.id,
            "run_date": str(latest_run.run_date),
            "status": latest_run.status,
            "summary": latest_run.summary,
        }
        if latest_run
        else None,
        "breaks": [
            {
                "id": b.id,
                "break_type": b.break_type,
                "description": b.description,
                "source": b.source,
                "external_reference": b.external_reference,
                "local_reference": b.local_reference,
                "expected_amount_cents": b.expected_amount_cents,
                "actual_amount_cents": b.actual_amount_cents,
                "status": b.status,
                "first_seen_at": b.first_seen_at.isoformat() if b.first_seen_at else None,
            }
            for b in breaks
        ],
        "total_count": ReconciliationBreak.objects.filter(status=status_filter).count()
        if status_filter
        else ReconciliationBreak.objects.count(),
    }


@mcp.tool()
def create_action_request(
    action_type: str,
    target_type: str,
    target_id: int,
    requested_by_username: str,
    description: str,
) -> dict:
    """
    Create a financial action request that enters the human approval queue.

    action_type: CLAIM_PAYMENT, REFUND, or PAYOUT
    target_type: 'claim_payment' or 'refund'
    target_id: ID of the target object
    requested_by_username: username of the staff user making the request
    description: human-readable description of the requested action

    The agent CANNOT approve its own action. All requests enter the normal
    maker-checker approval workflow.
    """
    from django.contrib.contenttypes.models import ContentType

    from apps.accounts.models import User
    from apps.approvals.models import Approval

    valid_actions = [Approval.Action.CLAIM_PAYMENT, Approval.Action.REFUND, Approval.Action.PAYOUT]
    if action_type not in valid_actions:
        return {"error": f"Invalid action_type. Must be one of: {valid_actions}"}

    try:
        user = User.objects.get(username=requested_by_username)
    except User.DoesNotExist:
        return {"error": f"User '{requested_by_username}' not found"}

    if not user.is_staff:
        return {"error": "Only staff users can create action requests"}

    target_model_map = {
        "claim_payment": "claims.ClaimPayment",
        "refund": "payments.Refund",
    }

    if target_type not in target_model_map:
        return {"error": f"Invalid target_type. Must be one of: {list(target_model_map.keys())}"}

    app_label, model_name = target_model_map[target_type].split(".")
    ct = ContentType.objects.get(app_label=app_label, model=model_name.lower())

    target_model = ct.model_class()
    try:
        target_model.objects.get(id=target_id)
    except target_model.DoesNotExist:
        return {"error": f"{target_type} with id {target_id} not found"}

    existing = Approval.objects.filter(
        content_type=ct,
        object_id=target_id,
        action=action_type,
        status=Approval.Status.PENDING,
    ).first()

    if existing:
        return {
            "approval_id": existing.id,
            "status": "ALREADY_PENDING",
            "message": "An approval request already exists for this action",
        }

    approval = Approval.objects.create(
        content_type=ct,
        object_id=target_id,
        action=action_type,
        requested_by=user,
        reason=f"[MCP Agent] {description}",
    )

    return {
        "approval_id": approval.id,
        "status": "PENDING",
        "message": "Action request created and entered human approval queue",
        "action_type": action_type,
        "target": f"{target_type}:{target_id}",
        "requested_by": requested_by_username,
    }
