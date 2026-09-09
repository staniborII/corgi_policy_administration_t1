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
│   │   ├── test_payment_flow.py   # Checkout, success, failure, ledger, commission, webhook, API
│   │   └── test_cancellation_flow.py # Pro-rata, refund, clawback, ledger, broker statement
│   ├── endorsements/tests/
│   │   └── test_endorsement_flow.py # Pro-rata, approval, correction, as-of, PDF, API
│   ├── claims/tests/
│   │   └── test_claims_flow.py    # Claim intake, reserves, payments, maker-checker, payout
│   ├── reconciliation/tests/
│   │   └── test_reconciliation.py  # Reconciliation runs, breaks, resolution, MCP safety
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
| Claims | 22 | Claim submission (active policy, outside-coverage rejection, pre-cancellation validity), reserves (initial sets status, adjustments append not mutate, incurred = paid + reserve, journal entries, negative adjustment, no double initial), payments (over limit rejected, small auto-approved, large needs approval), maker-checker (self-approval blocked, second staff approves), payout flow (execute sets pending, settled creates ledger entries, duplicate settled idempotent, returned compensating entries), payout destination (unverified blocks, no destination blocks, SIMULATED label, failed verification blocks) |
| Cancellation & Refunds | 19 | Pro-rata (mid-term unearned, refundable tax on unearned, commission clawback match, last-day zero refund, before-effective error), leap year (366-day term), cancel flow (creates pending refund, records event, non-active raises, open claim survives), refund ledger (posts on success, balanced entry, clawback posted, idempotent, posts once), broker statement (ties to ledger, with clawback, rerun identical, data contains details) |
| Reconciliation & MCP | 10 | Clean run (no breaks), missing in provider, missing in ledger, amount mismatch, duplicate webhook harmless, out-of-order webhook tolerated, provider outage (FAILED run), break resolution, MCP agent cannot approve own action, MCP tools no ledger mutation |

**Total: 188 tests**

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

## Docker / Container Testing

```bash
# Build the image
docker compose build backend

# Start services (Django + PostgreSQL)
docker compose up -d

# Run migrations (one-off task)
docker compose run --rm migrate

# Verify health endpoint
curl http://localhost:8000/health/
# Expected: {"status": "ok"}

# Verify SIGTERM graceful shutdown
docker compose stop backend
# Expected: clean exit, no error logs

# Verify non-root runtime
docker compose exec backend whoami
# Expected: appuser

# Verify no secrets in image
docker compose exec backend env | grep -iE '(sk_live|AKIA|password)' || echo "No secrets"

# Clean up
docker compose down -v
```

## Infrastructure Tests (CDK)

```bash
cd infra
npm test            # Jest CDK assertions
npx cdk synth       # CloudFormation template generation
```

### CDK Test Coverage

| Stack | Tests | Key Assertions |
|-------|-------|----------------|
| NetworkStack | 3 | VPC CIDR 10.0.0.0/16, 1 NAT gateway (trial trade-off), 5 VPC endpoints |
| DatabaseStack | 4 | PostgreSQL engine + encryption + single-AZ, RDS Proxy with TLS, DB secret with auto-gen password, instance type from config |
| EcsStack | 6 | Cluster exists, configured Fargate task count, ECR repo with scan-on-push, public-facing ALB, app secrets, Route 53 record when domain configured |
| FrontendStack | 4 | S3 private bucket (all public access blocked), CloudFront distribution, WAF CLOUDFRONT scope, Route 53 record when domain configured |

**Total: 17 CDK tests + 188 backend tests = 205 tests**

## Linting & Formatting

```bash
cd backend
uv run ruff format --check .   # Format check
uv run ruff check .            # Lint check
uv run python manage.py check  # Django system check
```
