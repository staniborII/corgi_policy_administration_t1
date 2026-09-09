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
    [*] --> DRAFT
    DRAFT --> PENDING_CUSTOMER_APPROVAL : submitted
    PENDING_CUSTOMER_APPROVAL --> APPROVED : customer accepts
    APPROVED --> PENDING_PAYMENT : additional premium
    APPROVED --> APPLIED : no premium change
    PENDING_PAYMENT --> APPLIED : payment succeeded
    APPLIED --> REVERSED : correction needed
```

## Claim Status

```mermaid
stateDiagram-v2
    [*] --> OPEN
    OPEN --> UNDER_REVIEW : investigation starts
    UNDER_REVIEW --> RESERVED : reserve set
    RESERVED --> PAYMENT_PENDING : payment initiated
    PAYMENT_PENDING --> PARTIALLY_PAID : partial payment
    PAYMENT_PENDING --> PAID : full payment
    PARTIALLY_PAID --> PAID : remaining paid
    PAID --> CLOSED : finalized
    RESERVED --> CLOSED : denied/withdrawn
    UNDER_REVIEW --> CLOSED : denied/withdrawn
```

## Claim Payment Status

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_APPROVAL : submitted
    PENDING_APPROVAL --> APPROVED : approved (not by creator)
    PENDING_APPROVAL --> DRAFT : rejected
    APPROVED --> PENDING : payout initiated
    PENDING --> SETTLED : payout confirmed
    PENDING --> RETURNED : payout returned
    PENDING --> FAILED : payout failed
```

The maker-checker rule applies: the person who creates a claim payment cannot approve it.

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
