# Money Flows

## Double-Entry Ledger

Every financial transaction is recorded as a journal entry with balanced debit and credit lines. Posted entries are immutable — corrections use reversal + re-book.

### Invariants

- `sum(debits) == sum(credits)` for every posted journal entry
- Posted entries and lines are never updated or deleted
- All amounts in integer cents
- Idempotency keys prevent duplicate postings

## Chart of Accounts

| Code | Name | Type | Normal Balance |
|------|------|------|---------------|
| 1000 | Cash | Asset | Debit |
| 1010 | Stripe Clearing | Asset | Debit |
| 1100 | Premium Receivable | Asset | Debit |
| 2000 | Unearned Premium | Liability | Credit |
| 2100 | State Premium Tax Payable | Liability | Credit |
| 2200 | Broker Commission Payable | Liability | Credit |
| 2300 | Claim Reserve | Liability | Credit |
| 2400 | Refund Payable | Liability | Credit |
| 4000 | Earned Premium | Revenue | Credit |
| 4100 | Fee Revenue | Revenue | Credit |
| 4200 | Commission Clawback | Revenue | Credit |
| 5000 | Claims Expense | Expense | Debit |
| 5100 | Commission Expense | Expense | Debit |

## Key Financial Flows

### Policy Premium Collection

```mermaid
flowchart LR
    A[Customer pays] --> B[Stripe Clearing +]
    B --> C[Premium Receivable -]
    C --> D[Unearned Premium +]
    D --> E[Tax Payable +]
    D --> F[Fee Revenue +]
```

Journal entry (premium = $1,000, tax = $35, fee = $25):
| Line | Account | Debit | Credit |
|------|---------|-------|--------|
| 1 | 1010 Stripe Clearing | 106,000 | |
| 2 | 2000 Unearned Premium | | 100,000 |
| 3 | 2100 Tax Payable | | 3,500 |
| 4 | 4100 Fee Revenue | | 2,500 |

### Correction (Reversal + Re-book)

Original charge of $300 needs to be corrected to $350:

1. **Reversal entry** — mirrors the original with flipped debits/credits
2. **Re-book entry** — posts the correct $350 amount

All three entries remain permanently visible for audit.

### Claim Reserve and Payment

```mermaid
flowchart LR
    A[Reserve set] --> B[Claim Reserve +]
    B --> C[Claims Expense +]
    C --> D[Cash -]
```

### Commission

```mermaid
flowchart LR
    A[Policy bound] --> B[Commission Payable +]
    B --> C[Commission Expense +]
```

On cancellation, commission clawback reverses the commission.

## Tax and Fee Rules

Tax and fee rules are effective-dated per jurisdiction. Rule selection uses the policy's effective date, ensuring:

- Historical policies use the rules that were in effect at their inception
- A later rate change does not retroactively affect existing policies
- Tax/fees remain separate financial components from premium
