# Live-Fire Testing

## Provider Status

| Provider | Mode | Status |
|----------|------|--------|
| Persona | Sandbox | Ready (set `PERSONA_API_KEY`, `PERSONA_WEBHOOK_SECRET`, `PERSONA_TEMPLATE_ID`) |
| Stripe | Test mode | Ready (set `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`) |
| Bank verification | SIMULATED | Adapter-based, labelled SIMULATED |
| Payout rail | SIMULATED | Adapter-based, labelled SIMULATED |

## Persona Sandbox Testing

### Prerequisites
1. Set environment variables:
   - `PERSONA_API_KEY` — sandbox API key from Persona dashboard
   - `PERSONA_WEBHOOK_SECRET` — webhook signing secret
   - `PERSONA_TEMPLATE_ID` — business verification template ID

2. Configure Persona webhook endpoint:
   - URL: `{your_base_url}/api/integrations/webhooks/persona/`
   - For local development, use ngrok or similar tunnel

### Test Flow
1. Staff creates a broker via `/staff/brokers`
2. Staff clicks "Initiate KYB" — creates Persona inquiry
3. Complete the Persona verification flow in the sandbox
4. Persona sends webhook to `/api/integrations/webhooks/persona/`
5. Broker status transitions to APPROVED or REJECTED
6. Staff can now create policies through the approved broker

### Simulated Mode
When credentials are not configured:
- KYB initiation returns a `SIMULATED-{uuid}` inquiry ID
- UI displays a "SIMULATED" warning
- Broker state can be advanced manually via webhook testing tools

## Stripe Live-Fire Testing

### Prerequisites
```bash
export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_PUBLISHABLE_KEY=pk_test_...
export STRIPE_WEBHOOK_SECRET=whsec_...
```

Forward webhooks locally:
```bash
stripe listen --forward-to localhost:8000/api/integrations/webhooks/stripe/
```

### Payment Flow
1. Create a policy and checkout session
2. Complete payment using Stripe test card `4242424242424242`
3. Verify `checkout.session.completed` webhook arrives
4. Verify ledger posts (DR 1010 / CR 2000, 2100, 2150 + commission)
5. Verify policy activates (PENDING_PAYMENT → ACTIVE)

### Refund Flow
1. Cancel an active policy
2. Verify refund created at Stripe
3. Verify `charge.refunded` webhook arrives
4. Verify refund ledger posts (DR 2000, 2100, 2150 / CR 2400)
5. Verify commission clawback posts (DR 2200 / CR 4200)

### Idempotency Keys
Outbound Stripe API calls include idempotency keys:
- Checkout Session: `metadata.idempotency_key` passed to Stripe
- Refund: `metadata.idempotency_key` = `cancel-refund-{policy_id}`

Stripe-side idempotency ensures duplicate API calls return the same result.

## Live-Fire Scenarios

### Scenario 1: Payment Webhook Replay

**Action:** Replay a Stripe `checkout.session.completed` webhook twice.

**Expected:** One financial effect. Second delivery returns 200 with no duplicate ledger entries.

**Automated test:** `test_duplicate_webhook_harmless` in `test_reconciliation.py`

### Scenario 2: Backdated Endorsement Correction

**Action:** Create, apply, then correct an endorsement with different effective date.

**Expected:** Original preserved, reversal + re-book, as-of reconstruction correct.

**Automated test:** `TestCorrectionFlow` in `test_endorsement_flow.py`

### Scenario 3: Cancellation with Open Claim

**Action:** Create policy, submit claim, set reserve, cancel policy.

**Expected:** Refund + clawback computed; open claim remains OPEN.

**Automated test:** `test_open_claim_remains_after_cancellation` in `test_cancellation_flow.py`

### Scenario 4: As-Of Policy Query

**Action:** Apply two endorsements at different dates, query as-of between them.

**Expected:** Correct premium and endorsement list for the as-of timestamp.

**Automated test:** `TestAsOfReconstruction` in `test_endorsement_flow.py`

### Scenario 5: Mismatched Payout (Reconciliation Break)

**Action:** Provider truth amount differs from local record.

**Expected:** AMOUNT_MISMATCH break detected, visible in Staff Portal.

**Automated test:** `test_amount_mismatch_detected` in `test_reconciliation.py`

### Scenario 6: Provider Outage

**Action:** Simulate provider API failure during reconciliation.

**Expected:** Run marked FAILED, no partial state, clear error in summary.

**Automated test:** `test_provider_outage_leaves_consistent_state` in `test_reconciliation.py`

## Running All Live-Fire Tests

```bash
cd backend

# Reconciliation + break detection + provider outage
uv run pytest apps/reconciliation/tests/ -v

# Cancellation + refund + clawback + open claim
uv run pytest apps/payments/tests/test_cancellation_flow.py -v

# Endorsement correction + as-of
uv run pytest apps/endorsements/tests/ -v

# Payment idempotency
uv run pytest apps/payments/tests/test_payment_flow.py -v

# All tests
uv run pytest -v
```

## MCP Agent Safety Verification

The MCP surface exposes 3 read tools + 1 write tool:

| Tool | Type | Purpose |
|------|------|---------|
| `read_policy` | Read | Policy details, events, endorsements |
| `read_claim` | Read | Claim details, reserves, payments, financials |
| `read_reconciliation_breaks` | Read | Break listing with filtering |
| `create_action_request` | Write | Creates approval request (enters human queue) |

**Safety invariants:**
- Agent-created requests are PENDING (never auto-approved)
- Reason tagged with `[MCP Agent]` for audit trail
- No MCP tool exposes ledger mutation
- Maker-checker enforced — requesting user cannot approve their own request
- Agent cannot change KYB outcomes
- Agent cannot delete financial history

**Automated test:** `TestMCPSafety` in `test_reconciliation.py`
