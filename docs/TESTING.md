# Testing

## Backend Test Suite

### Framework
- **pytest** + **pytest-django**
- Django settings: `config.settings`
- Database: SQLite in-memory (test isolation per test)

### Running Tests

```bash
cd backend
uv run pytest -v           # all tests
uv run pytest apps/ledger/ # specific app
```

### Test Organization

```
backend/
├── tests/
│   └── test_smoke.py              # Django system check
├── apps/
│   ├── accounts/tests/
│   │   └── test_auth.py           # Login, registration, permissions
│   ├── brokers/tests/
│   │   └── test_broker_kyb.py     # Broker creation, KYB webhooks, state machine
│   ├── integrations/tests/
│   │   └── test_persona_webhook.py # Webhook signature, idempotency, rejection
│   ├── ledger/tests/
│   │   ├── test_posting.py        # Journal entry posting, balance, idempotency
│   │   └── test_reversal.py       # Reversal, correction flow
│   ├── payments/tests/
│   │   └── test_payment_flow.py   # Checkout, success, failure, ledger, commission, webhook, API
│   ├── endorsements/tests/
│   │   └── test_endorsement_flow.py # Pro-rata, approval, correction, as-of, PDF, API
│   └── policies/tests/
│       ├── test_policy_issuance.py # Issuance, approved broker guard, charges, API
│       ├── test_policy_term.py     # Calendar anniversary logic
│       ├── test_tx_tax_model.py    # TX tax calculations, rounding, historical rules
│       └── test_tax_fee_rules.py   # Rule selection by date/jurisdiction
```

### Test Coverage by Domain

| Domain | Tests | Key Scenarios |
|--------|-------|---------------|
| Auth | 8 | Login (staff/customer), invalid credentials, me endpoint, registration, duplicate prevention, role-based permissions |
| Brokers | 7 | API creation, service creation, KYB approval/rejection, duplicate webhook, no regression from final states |
| Webhook | 4 | Valid processing, duplicate idempotency, invalid signature rejection, missing signature rejection |
| Ledger | 11 | Balanced/unbalanced entries, zero amounts, integer cents, idempotency, inactive accounts, balance queries, reversals, corrections |
| Policies | 16 | Approved/non-approved broker guard, anniversary dates (including Feb 29), charge breakdown, tax/fee rule selection by date/jurisdiction, API creation, customer access control |
| Payments | 23 | Checkout creation (state transitions, payment record, events, active-policy guard), success (activation, balanced ledger, charge total, commission, events), idempotency (duplicate success posts ledger once), failure (no activation, no ledger), simulated mode, ledger balances, commission rounding, Stripe webhook API (signature rejection, invalid JSON, full flow, duplicate idempotency), payment API (create checkout, list, simulate, access control) |
| Endorsements | 35 | Pro-rata math (half-year, full-year, one-day, zero-day, negative, leap-year), creation (below/above threshold, address correction, draft-policy guard, out-of-term guard), customer approval, apply (balanced ledger, policy premium update, commission posting, tax/fee rates), correction (reversal creates new entry, original untouched, reversal entry posted, different pro-rata), leap-year 366-day term, as-of reconstruction (before/after/between endorsements), PDF generation (declarations, endorsement schedule, with as-of), API (create, list, approve, correct, as-of, PDFs, access control) |

**Total: 137 tests**

## Frontend

### Type Checking

```bash
cd frontend
npm run typecheck    # tsc --noEmit
npm run lint         # ESLint
npm run build        # Static export (verifies all pages)
```

### E2E Tests

Not yet implemented. Playwright will be added for critical flows in later milestones.

## Linting & Formatting

```bash
cd backend
uv run ruff format --check .   # Format check
uv run ruff check .            # Lint check
uv run python manage.py check  # Django system check
```
