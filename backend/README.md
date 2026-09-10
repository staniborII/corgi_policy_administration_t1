# Corgi Backend

Django REST Framework backend for the Corgi Policy Administration System. Handles policy lifecycle, payments, claims, double-entry ledger, document generation, and third-party integrations (Stripe, Persona).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Django Application                            │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ accounts │  │ brokers  │  │ policies │  │ payments │  │  claims  │ │
│  │          │  │          │  │          │  │          │  │          │ │
│  │ User     │  │ Broker   │  │ Policy   │  │ Payment  │  │ Claim    │ │
│  │ Auth     │  │ KYB      │  │ TaxRule  │  │ Refund   │  │ Reserve  │ │
│  │ Roles    │  │          │  │ FeeRule  │  │          │  │ Payout   │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  ledger  │  │endorsem. │  │documents │  │approvals │  │  recon   │ │
│  │          │  │          │  │          │  │          │  │          │ │
│  │ Account  │  │Endorsem. │  │ Document │  │ Approval │  │ Run      │ │
│  │ Journal  │  │ Correct. │  │ PDF gen  │  │ Maker/   │  │ Break    │ │
│  │ Line     │  │          │  │ S3 store │  │ Checker  │  │ BrkStmt  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                                                                         │
│  ┌──────────────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │  integrations    │  │     mcp      │  │          ws             │   │
│  │                  │  │              │  │                         │   │
│  │ Stripe webhooks  │  │ MCP server   │  │ WebSocket notifications │   │
│  │ Persona webhooks │  │ AI tool use  │  │ Channels + Redis       │   │
│  │ Event log        │  │              │  │                         │   │
│  └──────────────────┘  └──────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Domain Model

```
┌──────────┐       ┌──────────┐       ┌───────────────┐
│   User   │──1:1──│  Broker  │──1:N──│ KYBVerification│
│ (role)   │       │(status,  │       │(persona_id,   │
│          │       │ commission│       │ status)       │
└────┬─────┘       │ rate_bps)│       └───────────────┘
     │             └────┬─────┘
     │ customer         │ broker
     ▼                  ▼
┌────────────────────────────┐
│          Policy            │
│ (number, status, premium,  │
│  coverage, effective_date, │
│  expiration_date)          │
└──┬─────┬─────┬─────┬──────┘
   │     │     │     │
   ▼     │     │     ▼
┌──────┐ │     │  ┌──────────────┐
│Policy│ │     │  │ Endorsement  │
│Event │ │     │  │ (type,status,│
└──────┘ │     │  │  premium_    │
         │     │  │  delta)      │
         ▼     │  └──────────────┘
┌────────────┐ │
│  Payment   │ │    ┌───────────────────────────────┐
│ (stripe_id,│ │    │           Claim               │
│  amount,   │ │    │ (number, status, date_of_loss,│
│  status)   │ │    │  estimated_amount)            │
├────────────┤ │    ├───────────────────────────────┤
│  Refund    │ │    │ ReserveEvent  (amount, type)  │
│ (stripe_id)│ └───►│ ClaimPayment  (payee, status) │
└────────────┘      │ PayoutDest    (account_info)  │
                    └───────────────────────────────┘

                  ┌──────────────────────────┐
                  │    Ledger (double-entry)  │
                  │                          │
                  │ LedgerAccount (code,type) │
                  │         │                │
                  │ JournalEntry (memo,       │
                  │   idempotency_key,status) │
                  │         │                │
                  │ JournalLine (amount_cents,│
                  │   DEBIT/CREDIT)          │
                  └──────────────────────────┘
```

All money values are stored as **integer cents** (no floats). Posted journal entries are append-only — corrections use reversal + re-book.

## App Breakdown

### accounts
User model with `CUSTOMER` / `STAFF` roles. Token-based authentication (DRF `TokenAuthentication`) plus session auth for Django admin.

### brokers
Broker onboarding with Persona KYB (Know Your Business) verification. A broker must pass KYB before binding policies. Commission rate stored in basis points.

### policies
Core policy lifecycle: DRAFT → PENDING_PAYMENT → ACTIVE → CANCELLED/EXPIRED. Includes configurable `TaxRule` and `FeeRule` models per jurisdiction (managed via Django admin). Policy events provide an audit trail. Calendar-anniversary terms (not fixed 365 days).

### ledger
Double-entry accounting ledger. Every financial operation creates balanced journal entries. Chart of accounts seeded via `seed_chart_of_accounts` management command. Posted entries are immutable — corrections create a reversal entry + new entry.

### payments
Stripe Checkout integration for premium collection. Handles checkout sessions, payment confirmation via webhooks, and refunds (full/partial). Charges snapshots preserve the premium/tax/fee breakdown at payment time.

### claims
FNOL (First Notice of Loss) through settlement. Reserve management with initial/adjustment/release events. Claim payments with maker-checker approval. Simulated payout provider for testing.

### endorsements
Mid-term policy changes (coverage limit change, address correction). Pro-rated premium calculation. Endorsement correction flow (reversal + re-book). Generates endorsement schedule PDFs.

### documents
PDF generation via ReportLab (declarations, endorsement schedules, broker statements, claim reports). Uploads to S3 with presigned URL download. Falls back to in-memory when S3 is not configured (local dev).

### approvals
Generic maker-checker approval system (Django content types). Used for claim payments, refunds, and payouts. The maker cannot approve their own action.

### reconciliation
Automated reconciliation runs comparing Stripe transactions against local ledger entries. Detects breaks (missing, duplicate, amount mismatches). Broker commission statements with period-based settlement and clawback tracking.

### integrations
Webhook receivers for Stripe and Persona. All webhooks are signature-verified, idempotent (deduplicated by event ID), and out-of-order tolerant. `WebhookEvent` model logs every inbound event.

### mcp
Model Context Protocol server exposing domain tools for AI agents: `read_policy`, `read_claim`, `read_reconciliation_breaks` (read-only), and `create_action_request` (enters maker-checker queue). Agent writes require human approval.

### ws
WebSocket notifications via Django Channels + Redis. Users join groups by ID and role. Server pushes real-time events (approval requests, payment confirmations, claim updates).

## API Endpoints

All API routes are prefixed per the root URL configuration:

### Authentication (`/api/auth/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login/` | Login, returns auth token |
| POST | `/api/auth/logout/` | Logout, invalidates token |
| GET | `/api/auth/me/` | Current user profile |
| POST | `/api/auth/register/` | Register new user |
| GET | `/api/auth/customers/` | List customers (staff only) |

### Brokers (`/api/brokers/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/brokers/` | List brokers |
| GET | `/api/brokers/<id>/` | Broker detail |
| POST | `/api/brokers/<id>/kyb/` | Initiate Persona KYB verification |

### Policies (`/api/policies/`)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/policies/` | List / create policies |
| GET | `/api/policies/jurisdictions/` | Available jurisdictions with tax/fee rules |
| GET/PATCH | `/api/policies/<id>/` | Policy detail / update |
| GET | `/api/policies/<id>/as-of/` | Point-in-time policy state |
| POST | `/api/policies/<id>/cancel/` | Cancel policy |
| POST | `/api/policies/<id>/decline/` | Decline policy |
| POST | `/api/policies/<id>/update-effective-date/` | Change effective date |

### Payments (`/api/payments/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/payments/checkout/` | Create Stripe Checkout session |
| GET | `/api/payments/verify-session/` | Verify Checkout session status |
| GET | `/api/payments/policy/<id>/` | Payments for a policy |
| GET/POST | `/api/payments/policy/<id>/refunds/` | List / create refunds |
| POST | `/api/payments/<id>/simulate/` | Simulate payment (test) |
| POST | `/api/payments/refunds/<id>/simulate/` | Simulate refund (test) |

### Claims (`/api/claims/`)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/claims/` | List / create claims |
| GET/PATCH | `/api/claims/<id>/` | Claim detail / update |
| GET | `/api/claims/<id>/financials/` | Claim financial summary |
| GET/POST | `/api/claims/<id>/reserves/` | Reserve events |
| GET/POST | `/api/claims/<id>/payments/` | Claim payments |
| POST | `/api/claims/payments/<id>/approve/` | Approve claim payment (checker) |
| POST | `/api/claims/payments/<id>/execute/` | Execute approved payment |
| POST | `/api/claims/payout-callback/` | Payout provider callback |
| GET/POST | `/api/claims/<id>/payout-destination/` | Payout destination |
| POST | `/api/claims/<id>/payout-destination/verify/` | Verify payout destination |

### Endorsements (`/api/endorsements/`)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/endorsements/` | List / create endorsements |
| GET | `/api/endorsements/<id>/` | Endorsement detail |
| POST | `/api/endorsements/<id>/approve/` | Approve endorsement |
| POST | `/api/endorsements/<id>/apply/` | Apply endorsement to policy |
| POST | `/api/endorsements/<id>/correct/` | Correct (reverse + re-book) |

### Documents (`/api/documents/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/documents/policy/<id>/declarations/` | Generate declarations PDF |
| POST | `/api/documents/policy/<id>/endorsement-schedule/` | Generate endorsement schedule PDF |
| GET | `/api/documents/policy/<id>/` | List documents for policy |
| GET | `/api/documents/<id>/download/` | Download document (presigned S3 URL) |

### Integrations (`/api/integrations/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/integrations/webhooks/stripe/` | Stripe webhook receiver |
| POST | `/api/integrations/webhooks/persona/` | Persona webhook receiver |

### Reconciliation (`/api/reconciliation/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/reconciliation/broker-statements/` | List broker statements |
| GET | `/api/reconciliation/broker-statements/<id>/` | Statement detail |
| GET/POST | `/api/reconciliation/runs/` | List / trigger reconciliation runs |
| GET | `/api/reconciliation/runs/<id>/` | Run detail with breaks |
| GET | `/api/reconciliation/breaks/` | List all breaks |
| POST | `/api/reconciliation/breaks/<id>/resolve/` | Resolve a break |

### Other Routes

| Path | Description |
|------|-------------|
| `/health/` | Health check (bypasses ALLOWED_HOSTS via middleware) |
| `/admin/` | Django admin interface |
| `ws/events/` | WebSocket notifications (Channels) |

## Request Flow

```
                    ┌──────────────────────────────────────────┐
                    │              Incoming Request             │
                    └─────────────────┬────────────────────────┘
                                      │
                    ┌─────────────────▼────────────────────────┐
                    │         HealthCheckMiddleware             │
                    │  (short-circuits /health/ before hosts)   │
                    └─────────────────┬────────────────────────┘
                                      │
                    ┌─────────────────▼────────────────────────┐
                    │  SecurityMiddleware → CORS → Session      │
                    │  → CSRF → Auth → Messages → XFrame       │
                    └─────────────────┬────────────────────────┘
                                      │
                    ┌─────────────────▼────────────────────────┐
                    │             URL Router                    │
                    │  /api/auth/ → accounts.views              │
                    │  /api/policies/ → policies.views          │
                    │  /api/payments/ → payments.views          │
                    │  /api/claims/ → claims.views              │
                    │  ...                                      │
                    └─────────────────┬────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
              ▼                       ▼                       ▼
       ┌─────────────┐      ┌──────────────┐      ┌──────────────────┐
       │   Views /    │      │   Services   │      │   Integrations   │
       │  Serializers │─────►│  (business   │─────►│  (Stripe client, │
       │  (DRF)      │      │   logic)     │      │   Persona client)│
       └─────────────┘      └──────┬───────┘      └──────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
             ┌───────────┐  ┌────────────┐  ┌──────────────┐
             │  Models   │  │   Ledger   │  │  Documents   │
             │ (Django   │  │  (journal  │  │  (PDF gen,   │
             │  ORM)     │  │   entries) │  │   S3 upload) │
             └───────────┘  └────────────┘  └──────────────┘
```

## Money Flow

```
Customer pays premium
        │
        ▼
┌─────────────────┐     Stripe webhook     ┌──────────────────┐
│ Stripe Checkout │ ──────────────────────► │ Payment created  │
│ Session         │  checkout.session       │ (SUCCEEDED)      │
└─────────────────┘  .completed             └────────┬─────────┘
                                                     │
                                        ┌────────────▼─────────────┐
                                        │   Ledger Journal Entry   │
                                        │                          │
                                        │  DR Cash          $1000  │
                                        │  CR Premium Revenue $850 │
                                        │  CR Tax Payable    $100  │
                                        │  CR Broker Comm     $50  │
                                        └──────────────────────────┘

Cancellation / Refund
        │
        ▼
┌─────────────────┐     Stripe webhook     ┌──────────────────┐
│ Stripe Refund   │ ──────────────────────► │ Refund recorded  │
│                 │  charge.refunded        │ (SUCCEEDED)      │
└─────────────────┘                         └────────┬─────────┘
                                                     │
                                        ┌────────────▼─────────────┐
                                        │  Reversal Journal Entry  │
                                        │  (mirrors original,      │
                                        │   debits ↔ credits)      │
                                        │                          │
                                        │  + Commission clawback   │
                                        │    if applicable         │
                                        └──────────────────────────┘
```

## Webhook Processing

```
┌──────────┐          ┌────────────────────────────────────────────────┐
│  Stripe  │──POST──► │  1. Verify signature (stripe.Webhook.verify)  │
│  Persona │          │  2. Check idempotency (WebhookEvent.event_id) │
│          │          │  3. Parse event type                           │
│          │          │  4. Dispatch to handler                        │
│          │          │  5. Update WebhookEvent status                 │
└──────────┘          └────────────────────────────────────────────────┘
```

**Stripe events handled:** `checkout.session.completed`, `checkout.session.expired`, `charge.refunded`

**Persona events handled:** `inquiry.completed`

All webhooks are idempotent (duplicate event = one financial effect) and out-of-order tolerant.

## Container Architecture

```
┌─────────────────────────────────────────────────┐
│              Docker Image (multi-stage)          │
│                                                  │
│  Builder: python:3.12-slim + uv                  │
│    → installs dependencies from uv.lock          │
│                                                  │
│  Runtime: python:3.12-slim                       │
│    → non-root user (appuser:1000)                │
│    → collectstatic at build time                 │
│    → entrypoint.sh handles boot sequence         │
│                                                  │
│  ENTRYPOINT: /app/entrypoint.sh                  │
│  CMD: daphne -b 0.0.0.0 -p 8000                 │
│       config.asgi:application                    │
└─────────────────────────────────────────────────┘
```

### Boot Sequence (entrypoint.sh)

```
1. Wait for database (30 retries × 2s)
2. Resolve FRONTEND_URL from SSM parameter (if not already set)
   → Sets CORS_ALLOWED_ORIGINS, CSRF_TRUSTED_ORIGINS, DJANGO_ALLOWED_HOSTS
3. Create superuser (if DJANGO_SUPERUSER_* env vars present)
4. Start Daphne (ASGI server)
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | `insecure-dev-key...` | Django secret key |
| `DJANGO_DEBUG` | `False` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `DATABASE_URL` | — | Full database URL (overrides individual DB_* vars) |
| `DB_TYPE` | `sqlite` | `postgres` or `sqlite` |
| `DB_HOST` | `localhost` | Database host |
| `DB_PORT` | `5432` | Database port |
| `DB_NAME` | `corgi_dev` | Database name |
| `DB_USER` | `corgi_user` | Database user |
| `DB_PASSWORD` | `corgi_pass` | Database password |
| `DB_SSLMODE` | — | PostgreSQL SSL mode (`require` in production) |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | CORS origins |
| `CSRF_TRUSTED_ORIGINS` | — | CSRF trusted origins |
| `FRONTEND_URL` | `http://localhost:3000` | Frontend URL for Stripe redirects |
| `FRONTEND_URL_SSM_PARAM` | — | SSM parameter name for runtime URL resolution |
| `STRIPE_SECRET_KEY` | — | Stripe API secret key |
| `STRIPE_PUBLISHABLE_KEY` | — | Stripe publishable key |
| `STRIPE_WEBHOOK_SECRET` | — | Stripe webhook signing secret |
| `PERSONA_API_KEY` | — | Persona API key |
| `PERSONA_WEBHOOK_SECRET` | — | Persona webhook signing secret |
| `PERSONA_TEMPLATE_ID` | — | Persona KYB template ID |
| `DOCUMENTS_BUCKET_NAME` | — | S3 bucket for document storage |
| `AWS_REGION` | `us-east-1` | AWS region for S3/SSM |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL for Channels |
| `DJANGO_SUPERUSER_USERNAME` | — | Auto-create superuser on boot |
| `DJANGO_SUPERUSER_PASSWORD` | — | Superuser password |
| `DJANGO_SUPERUSER_EMAIL` | — | Superuser email |
| `WEB_CONCURRENCY` | — | Daphne/Gunicorn worker count |
| `LOG_LEVEL` | `INFO` | Root log level |

## Development

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (dependency management)
- PostgreSQL 16 (or use SQLite for quick local dev)
- Redis (for WebSocket support)

### Setup

```bash
cd backend

# Install dependencies
uv sync

# Run migrations
python manage.py migrate

# Seed chart of accounts
python manage.py seed_chart_of_accounts

# Seed demo data (optional)
python manage.py seed_demo

# Start dev server
python manage.py runserver
```

### Docker Compose (full stack)

```bash
# From repo root
docker compose up db -d                          # Start PostgreSQL
docker compose run --rm migrate                  # Run migrations
docker compose up backend                        # Start backend
```

### Running Tests

```bash
# All 205 tests
python -m pytest

# Specific app
python -m pytest apps/ledger/
python -m pytest apps/claims/

# With coverage
python -m pytest --cov=apps
```

### Test Suites

| Module | Tests | Coverage |
|--------|-------|----------|
| `test_auth.py` | Authentication, registration, login/logout |
| `test_broker_kyb.py` | Broker KYB verification flow |
| `test_policy_issuance.py` | Policy creation and activation |
| `test_policy_term.py` | Calendar-anniversary term calculations |
| `test_tax_fee_rules.py` | Jurisdiction-based tax/fee application |
| `test_tx_tax_model.py` | Tax model edge cases |
| `test_payment_flow.py` | Stripe checkout and payment confirmation |
| `test_cancellation_flow.py` | Cancellation with pro-rated refunds |
| `test_claims_flow.py` | Claim lifecycle, reserves, payouts |
| `test_endorsement_flow.py` | Endorsement creation, approval, correction |
| `test_posting.py` | Ledger journal entry posting and balance |
| `test_reversal.py` | Journal entry reversals |
| `test_persona_webhook.py` | Persona webhook signature verification |
| `test_reconciliation.py` | Reconciliation runs and break detection |
| `test_consumers.py` | WebSocket consumer auth and messaging |
| `test_middleware.py` | WebSocket token auth middleware |
| `test_notifications.py` | Notification dispatch to channels |
| `test_smoke.py` | Django system check |

### Linting and Formatting

```bash
# Lint
ruff check .

# Format
ruff format .

# Type-check is not configured (no mypy/pyright) — rely on tests
```

## Management Commands

| Command | Description |
|---------|-------------|
| `seed_chart_of_accounts` | Creates the standard ledger accounts |
| `seed_demo` | Creates demo users, brokers, policies for development |
| `ensure_superuser` | Creates superuser if not exists (used in entrypoint) |

## Project Structure

```
backend/
├── config/
│   ├── settings.py          # Django settings
│   ├── urls.py              # Root URL configuration
│   ├── wsgi.py              # WSGI application
│   ├── asgi.py              # ASGI application (Channels)
│   └── middleware.py         # HealthCheckMiddleware
├── apps/
│   ├── accounts/            # User model, auth, roles
│   ├── brokers/             # Broker onboarding, KYB
│   ├── policies/            # Policy lifecycle, tax/fee rules
│   ├── ledger/              # Double-entry accounting
│   ├── payments/            # Stripe integration, refunds
│   ├── claims/              # Claims, reserves, payouts
│   ├── endorsements/        # Mid-term policy changes
│   ├── documents/           # PDF generation, S3 storage
│   ├── approvals/           # Maker-checker workflow
│   ├── reconciliation/      # Stripe reconciliation, broker statements
│   ├── integrations/        # Webhook receivers (Stripe, Persona)
│   ├── mcp/                 # MCP server for AI agents
│   └── ws/                  # WebSocket consumers, notifications
├── tests/
│   └── test_smoke.py        # Django system check
├── Dockerfile               # Multi-stage production build
├── entrypoint.sh            # Container boot sequence
├── manage.py
├── pyproject.toml           # Dependencies, pytest, ruff config
└── uv.lock                  # Locked dependency versions
```
