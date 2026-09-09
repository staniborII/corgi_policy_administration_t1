# State Machines

## Broker Status

```mermaid
stateDiagram-v2
    [*] --> PENDING_KYB
    PENDING_KYB --> APPROVED : KYB passes
    PENDING_KYB --> REJECTED : KYB fails
    REJECTED --> PENDING_KYB : resubmit
```

A broker must be APPROVED before binding new business (writing policies).

## Policy Status

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_PAYMENT : quote accepted
    PENDING_PAYMENT --> ACTIVE : payment succeeded
    PENDING_PAYMENT --> DRAFT : payment failed
    ACTIVE --> CANCELLED : cancellation
    ACTIVE --> EXPIRED : term ends
```

Policy status represents the lifecycle of the policy itself. Payment and refund states are tracked separately on their own models.

## Endorsement Status

```mermaid
stateDiagram-v2
    [*] --> PENDING_CUSTOMER_APPROVAL : total > $500 threshold
    [*] --> PENDING_PAYMENT : total > $0, within threshold
    [*] --> APPROVED : total ≤ $0 or address correction
    PENDING_CUSTOMER_APPROVAL --> PENDING_PAYMENT : customer approves (additional premium due)
    PENDING_CUSTOMER_APPROVAL --> APPROVED : customer approves (no additional premium)
    PENDING_PAYMENT --> APPLIED : apply_endorsement
    APPROVED --> APPLIED : apply_endorsement
    APPLIED --> REVERSED : correction (reversal + re-book)
```

Endorsements skip DRAFT — they enter the state machine at creation based on the pro-rated charge amount and type:

- **Address corrections**: Always APPROVED (no premium change, `annual_premium_delta_cents` forced to 0)
- **Coverage limit changes**: PENDING_CUSTOMER_APPROVAL if total > $500 threshold, PENDING_PAYMENT if positive charge within threshold, APPROVED if zero or negative

Corrections always apply the corrected endorsement immediately since the original was already applied and paid.

## Claim Status

```mermaid
stateDiagram-v2
    [*] --> OPEN : customer submits claim
    OPEN --> RESERVED : reserve set (set_reserve)
    OPEN --> PAYMENT_PENDING : payment created (create_claim_payment)
    RESERVED --> PAYMENT_PENDING : payment created
    PAYMENT_PENDING --> PARTIALLY_PAID : partial payout settled
    PAYMENT_PENDING --> PAID : full payout settled (reserve = 0)
    PARTIALLY_PAID --> PAID : remaining reserve settled
    PAID --> CLOSED : finalized
    RESERVED --> CLOSED : denied/withdrawn
```

- Claims can be filed on ACTIVE, CANCELLED, or EXPIRED policies (date of loss must be within coverage dates)
- Claims remain valid after later policy cancellation if incident occurred while active

## Claim Payment Status

```mermaid
stateDiagram-v2
    [*] --> APPROVED : amount < $5,000 (auto-approved)
    [*] --> PENDING_APPROVAL : amount >= $5,000
    PENDING_APPROVAL --> APPROVED : second staff approves (maker ≠ checker)
    APPROVED --> PENDING : execute_payout (bank verified)
    PENDING --> SETTLED : payout callback (settled)
    PENDING --> RETURNED : payout callback (returned)
    PENDING --> FAILED : payout callback (failed)
    SETTLED --> RETURNED : payout callback (returned after settle)
```

**Maker-checker invariant**: `created_by != approved_by`. The person who creates a claim payment cannot approve it.

**Payout prerequisites**: PayoutDestination must exist and have `verification_status = VERIFIED` before payout execution.

## Payout Destination Status

```mermaid
stateDiagram-v2
    [*] --> PENDING : set_payout_destination
    PENDING --> VERIFIED : bank verification succeeds (SIMULATED)
    PENDING --> FAILED : bank verification fails (SIMULATED)
```

Bank verification is SIMULATED in v1, labelled with provider="SIMULATED" and SIM-BANK- reference prefix.

## Refund Status

```mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> PENDING : refund initiated
    PENDING --> SUCCEEDED : Stripe confirms
    PENDING --> FAILED : Stripe fails
```

## Payment Status

```mermaid
stateDiagram-v2
    [*] --> PENDING : Checkout Session created
    PENDING --> SUCCEEDED : checkout.session.completed webhook
    PENDING --> FAILED : checkout.session.expired or decline
```

Payment uses Stripe Checkout Sessions (redirect flow). The PENDING state represents a Checkout Session that the customer has been redirected to. Success is confirmed via the `checkout.session.completed` webhook, which triggers ledger posting and policy activation.

### Payment + Policy Interaction

```mermaid
sequenceDiagram
    participant Policy
    participant Payment
    participant Ledger

    Note over Policy: DRAFT
    Policy->>Payment: create_checkout_for_policy
    Note over Payment: PENDING
    Note over Policy: PENDING_PAYMENT
    Payment->>Ledger: handle_payment_success
    Note over Ledger: DR 1010 / CR 2000,2100,2150
    Note over Ledger: DR 5100 / CR 2200 (commission)
    Note over Payment: SUCCEEDED
    Note over Policy: ACTIVE
```
