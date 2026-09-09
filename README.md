# Corgi Policy Administration — Track 1

A focused policy-administration system for Commercial General Liability insurance.

## Status

Milestone 10 — Demo hardening (seed data, UI polish, observability).

## Structure

- `backend/` — Django + Django REST Framework (Python, managed by uv)
- `frontend/` — Next.js + TypeScript (static export)
- `infra/` — AWS CDK TypeScript (4-stack infrastructure)
- `docs/` — Architecture, domain model, state machines, money flows
- `project_management_docs_and_prompts/` — PRDs, prompts, engineering standards

## Local development

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18+ and npm

### Backend (Django)

```bash
cd backend

# Install dependencies
uv sync

# Copy the example env file and adjust as needed
cp .env.example .env

# Run migrations
uv run python manage.py migrate

# Seed demo data (users, broker, policy, endorsements, claim, reconciliation)
uv run python manage.py seed_demo

# Create a superuser (reads DJANGO_SUPERUSER_USERNAME/PASSWORD from .env)
uv run python manage.py ensure_superuser

# Start the dev server at http://127.0.0.1:8000
uv run python manage.py runserver
```

### Frontend (Next.js)

```bash
cd frontend

# Install dependencies
npm install

# Copy the example env file
cp .env.example .env.local

# Start the dev server at http://localhost:3000
npm run dev
```

### Environment files

Each project has its own `.env.example` with dummy values and comments:

- `backend/.env.example` — Django settings, database, Stripe, Persona, superuser
- `frontend/.env.example` — API URL

Copy them to `.env` (backend) or `.env.local` (frontend) before running.

### Database: SQLite vs PostgreSQL

The `DB_TYPE` env var controls which database backend Django uses. Set it in `backend/.env`:

```bash
# SQLite (default — no setup required for local dev)
DB_TYPE=sqlite
DB_NAME=db.sqlite3

# PostgreSQL (for integration testing and production)
DB_TYPE=postgres
DB_NAME=corgi_dev
DB_USER=corgi_user
DB_PASSWORD=corgi_pass
DB_HOST=localhost
DB_PORT=5432
```

Alternatively, setting `DATABASE_URL` overrides `DB_TYPE` and all `DB_*` vars:

```bash
DATABASE_URL=postgres://corgi_user:corgi_pass@localhost:5432/corgi_dev
```

The `ensure_superuser` management command prints which database it's connected to, so you can verify:

```
$ uv run python manage.py ensure_superuser
Database: SQLite (db.sqlite3)                          # ← when DB_TYPE=sqlite
Database: PostgreSQL (corgi_dev@localhost:5432)         # ← when DB_TYPE=postgres
Connection verified: postgresql
```

Both databases use the same Django ORM — no code changes needed when switching.

### Stripe integration (test mode)

By default, the backend runs in **simulated mode** (no Stripe keys needed) — payments complete instantly without real Stripe. To test with real Stripe checkout and webhooks:

1. **Create a Stripe account** at [dashboard.stripe.com](https://dashboard.stripe.com) (starts in test mode).

2. **Get your test API keys** from **Developers → API keys**:
   - Secret key (`sk_test_...`)
   - Publishable key (`pk_test_...`)

3. **Install the Stripe CLI**:
   ```bash
   # Windows
   winget install Stripe.StripeCLI

   # macOS
   brew install stripe/stripe-cli/stripe

   # Linux — see https://stripe.com/docs/stripe-cli
   ```

4. **Forward webhooks to your local server**:
   ```bash
   stripe login
   stripe listen --forward-to http://localhost:8000/api/integrations/webhooks/stripe/
   ```
   This prints a webhook signing secret (`whsec_...`) — copy it.

5. **Add the keys to `backend/.env`**:
   ```bash
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

6. **Restart the backend** and keep the `stripe listen` terminal running.

**Testing the flow:**
- Log in as `customer1/custpass1` and click **Pay Now** on a pending policy
- You'll be redirected to Stripe's hosted checkout page
- Use test card `4242 4242 4242 4242`, any future expiry, any CVC
- Stripe sends a webhook → `stripe listen` forwards it → backend activates the policy
- You're redirected back to the success page

Without Stripe keys, the **Pay Now** button completes payment instantly via simulation (no redirect).

### VS Code setup

After running `uv sync`, point VS Code at the project's virtual environment so Pylance can resolve imports:

1. `Ctrl+Shift+P` → **Python: Select Interpreter**
2. Click **Enter interpreter path...**
3. Select `backend/.venv/Scripts/python.exe` (Windows) or `backend/.venv/bin/python` (macOS/Linux)

### Docker (optional)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
# Build and start Django + PostgreSQL
docker compose up --build

# Run migrations (one-time, separate from app start)
docker compose run --rm migrate

# Seed demo data inside the container
docker compose exec backend python manage.py seed_demo

# Health check
curl http://localhost:8000/health/
```

The `migrate` service runs as a one-off task (uses `profiles: [migrate]`), not on every container start — matching the ECS deployment model.

### Running tests

```bash
# Backend (188 tests)
cd backend
uv run pytest

# Infrastructure (17 CDK tests)
cd infra
npm test

# Frontend
cd frontend
npm run typecheck
npm run lint
```

## AWS Infrastructure

Infrastructure is defined as CDK TypeScript in `infra/` with a 4-stack architecture (Network, Database, ECS, Frontend). All environment-specific values live in `infra/config.yaml`.

### Quick start

```bash
cd infra
npm install

# Synth CloudFormation templates (no AWS credentials needed)
npx cdk synth -c stage=staging

# Deploy (requires AWS credentials + account in config.yaml)
npx cdk deploy --all -c stage=staging
```

### Configuration

Edit `infra/config.yaml` to set per-environment values:

| Field | Purpose |
|-------|---------|
| `account`, `region` | AWS target (leave empty for environment-agnostic synth) |
| `webDomainName` | Custom domain for CloudFront (e.g., `app.corgi.example.com`) |
| `serverDomainName` | Custom domain for ALB API (e.g., `api.corgi.example.com`) |
| `hostedZoneId`, `hostedZoneName` | Route 53 hosted zone for DNS records |
| `certificateArn` | ACM certificate ARN (must be in us-east-1 for CloudFront) |
| `cpu`, `memory`, `desiredCount` | ECS task sizing |
| `dbInstanceType`, `dbMultiAz`, `dbAllocatedStorage` | RDS sizing |

**Custom domains are optional.** Leave DNS fields empty to use default CloudFront and ALB URLs. When `certificateArn`, `hostedZoneId`, `hostedZoneName`, and domain names are all provided, Route 53 alias records and HTTPS are configured automatically.

### Post-deployment

After the first `cdk deploy`, update the `corgi/app` secret in AWS Secrets Manager with real values for Django secret key, superuser credentials, Stripe keys, and Persona keys.

## Commit conventions

This project follows [Conventional Commits](https://www.conventionalcommits.org/).

Format: `<type>(<scope>): <description>`

| Type | When to use |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `chore` | Build, config, tooling, dependencies |
| `ci` | CI/CD changes |

Scope is optional but encouraged — use the area of the codebase: `backend`, `frontend`, `infra`, `docs`.

Examples:

```
feat(backend): add policy creation endpoint
fix(frontend): correct premium display rounding
docs: update architecture diagram for ledger
chore(backend): upgrade Django to 5.1.16
test(backend): add integration tests for journal entries
```

Rules:
- Use imperative mood (`add`, not `added` or `adds`)
- Keep the subject line under 72 characters
- Use the body for additional context when the subject line isn't enough

### Seeding demo data

After running migrations, seed a complete demo environment:

```bash
cd backend
uv run python manage.py seed_demo
```

This creates:
- **Staff users**: staff1/staffpass1, staff2/staffpass2
- **Customer user**: customer1/custpass1
- **TX tax rules**: Surplus Lines Premium Tax (4.85%), SLTX Stamping Fee (0.04%)
- **Chart of accounts**: 14 ledger accounts (including Stamping Fee Payable)
- **Broker**: Acme Insurance Brokers (KYB approved, 15% commission)
- **Policy**: $120,000 CGL policy (active, paid via simulated Stripe)
- **Endorsements**: Coverage limit increase ($10K/yr, pro-rated) + address correction
- **Claim**: Water damage with $200K reserve, $75K settled payout (maker-checker approved)
- **Reconciliation**: Run with break detection
- **Broker statement**: Annual statement for the broker

The seed is idempotent — re-running it skips the demo scenario if it already exists.

## Key documents

- [DECISIONS.md](DECISIONS.md) — timestamped decision log
- [CUT_LIST.md](CUT_LIST.md) — scope deliberately excluded from v1
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture and app structure
- [docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md) — entity relationships and money representation
- [docs/STATE_MACHINES.md](docs/STATE_MACHINES.md) — state machine diagrams for all entities
- [docs/MONEY_FLOWS.md](docs/MONEY_FLOWS.md) — double-entry ledger and chart of accounts
- [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) — Persona KYB and webhook integration
- [docs/TESTING.md](docs/TESTING.md) — test suite organization and running tests
- [docs/LIVE_FIRE.md](docs/LIVE_FIRE.md) — live-fire testing with Persona sandbox
