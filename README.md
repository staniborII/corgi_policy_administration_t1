# Corgi Policy Administration — Track 1

A focused policy-administration system for Commercial General Liability insurance.

## Status

Milestone 1 — domain foundation, state machines, double-entry ledger, and schema.

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

# Create a .env file with dev defaults
cat > .env << 'EOF'
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=insecure-dev-key-change-in-production
DATABASE_URL=sqlite:///db.sqlite3
EOF

# Run migrations
uv run python manage.py migrate

# Start the dev server at http://127.0.0.1:8000
uv run python manage.py runserver
```

To use PostgreSQL instead of SQLite, set `DATABASE_URL` in `.env`:

```
DATABASE_URL=postgres://user:password@localhost:5432/corgi_dev
```

### VS Code setup

After running `uv sync`, point VS Code at the project's virtual environment so Pylance can resolve imports:

1. `Ctrl+Shift+P` → **Python: Select Interpreter**
2. Click **Enter interpreter path...**
3. Select `backend/.venv/Scripts/python.exe` (Windows) or `backend/.venv/bin/python` (macOS/Linux)

### Frontend (Next.js)

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server at http://localhost:3000
npm run dev
```

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

### Seeding the chart of accounts

After running migrations, seed the ledger accounts:

```bash
cd backend
uv run python manage.py seed_chart_of_accounts
```

## Key documents

- [DECISIONS.md](DECISIONS.md) — timestamped decision log
- [CUT_LIST.md](CUT_LIST.md) — scope deliberately excluded from v1
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture and app structure
- [docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md) — entity relationships and money representation
- [docs/STATE_MACHINES.md](docs/STATE_MACHINES.md) — state machine diagrams for all entities
- [docs/MONEY_FLOWS.md](docs/MONEY_FLOWS.md) — double-entry ledger and chart of accounts
