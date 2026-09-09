# Corgi Policy Administration — Track 1

A focused policy-administration system for Commercial General Liability insurance.

## Status

Milestone 4 — Endorsements, corrections, as-of reconstruction, PDF documents.

## Structure

- `backend/` — Django + Django REST Framework (Python, managed by uv)
- `frontend/` — Next.js + TypeScript (static export)
- `infra/` — AWS CDK (infrastructure, added in later milestones)
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

# Seed demo data (users, chart of accounts, TX tax rules)
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

### VS Code setup

After running `uv sync`, point VS Code at the project's virtual environment so Pylance can resolve imports:

1. `Ctrl+Shift+P` → **Python: Select Interpreter**
2. Click **Enter interpreter path...**
3. Select `backend/.venv/Scripts/python.exe` (Windows) or `backend/.venv/bin/python` (macOS/Linux)

### Running tests

```bash
# Backend
cd backend
uv run pytest

# Frontend
cd frontend
npm run typecheck
npm run lint
```

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

After running migrations, seed the chart of accounts, demo users, and Texas surplus-lines tax/fee rules:

```bash
cd backend
uv run python manage.py seed_demo
```

This creates:
- **Staff users**: staff1/staffpass1, staff2/staffpass2
- **Customer user**: customer1/custpass1
- **TX tax rules**: Surplus Lines Premium Tax (4.85%), SLTX Stamping Fee (0.04%)
- **Chart of accounts**: 14 ledger accounts (including Stamping Fee Payable)

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
