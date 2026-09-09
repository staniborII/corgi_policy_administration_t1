# Decision Log

Append decisions as they are made. Do not rewrite old entries to make history cleaner.

Format:

## YYYY-MM-DD HH:MM - Decision title
- **Decision:**
- **Reason:**
- **Assumption / evidence:**
- **Alternatives considered:**
- **Impact / follow-up:**

## 2026-09-08 18:00 - M0 technology and tooling choices
- **Decision:** Python 3.12 via uv, Django 5.1, DRF 3.17, psycopg 3, Ruff for Python linting/formatting, ESLint for TypeScript (ships with create-next-app).
- **Reason:** Python 3.12 is the most mature stable release with broad library support. Django 5.1 is latest stable. psycopg 3 is the modern PostgreSQL adapter. Ruff replaces multiple tools (black, isort, flake8) in one fast binary. ESLint is the Next.js default.
- **Assumption / evidence:** All chosen versions are compatible per their docs. uv manages Python installation, removing the system Python dependency.
- **Alternatives considered:** Python 3.13 (newer, less proven), psycopg2 (legacy, harder to install on Windows), Black+isort+flake8 (slower, more config).
- **Impact / follow-up:** These choices are locked for the project duration per the "choose once" rule.

## 2026-09-08 18:00 - Backend project layout
- **Decision:** Django project module named `config`, pyproject.toml in `backend/`, apps directory at `backend/apps/`.
- **Reason:** Follows the recommended structure from 09_ENGINEERING_STACK_RULES_AND_HOOKS.md. Keeps Python config separate from the monorepo root.
- **Assumption / evidence:** Two Scoops of Django convention. The recommended structure diagram shows this layout.
- **Alternatives considered:** Repo-root pyproject.toml (mixes concerns with frontend), Django project named `corgi` (less conventional).
- **Impact / follow-up:** All Django apps will be created under `backend/apps/` starting in M1.

## 2026-09-08 18:00 - SQLite fallback for M0 local development
- **Decision:** Django settings fall back to SQLite when DATABASE_URL is not set.
- **Reason:** Allows Django checks and smoke tests to pass without a running PostgreSQL instance. M0 has no domain models.
- **Assumption / evidence:** SQLite is sufficient for `manage.py check` and the smoke test. PostgreSQL becomes required from M1 when domain models are created.
- **Alternatives considered:** Require PostgreSQL from M0 (unnecessary friction for skeleton verification).
- **Impact / follow-up:** M1 should document PostgreSQL setup and may remove the SQLite fallback.

## 2026-09-08 18:00 - CLAUDE.md and CURSOR.md at repo root
- **Decision:** Copy CLAUDE.md and CURSOR.md from project_management_docs_and_prompts/ to repo root with paths adjusted to reference docs in project_management_docs_and_prompts/.
- **Reason:** Both AI tools expect their configuration files at the repository root.
- **Assumption / evidence:** Claude reads CLAUDE.md from repo root; Cursor reads CURSOR.md from repo root.
- **Alternatives considered:** Symlinks (fragile on Windows), leaving them only in the docs directory (tools won't find them).
- **Impact / follow-up:** If templates are updated, root copies should be synchronized.

## 2026-09-08 18:00 - AI hooks deferred to later milestone
- **Decision:** Do not copy .ai-hooks/ guardrail scripts to repo root in M0. They require `python3` on PATH which is not available (uv manages Python inside backend/.venv/).
- **Reason:** The hooks reference `python3` in their commands. Without system Python, they would fail on every tool invocation.
- **Assumption / evidence:** The hooks can be wired to `uv run` in a later milestone when the Python environment is more established.
- **Alternatives considered:** Rewriting hooks to use `uv run` now (premature, hooks are for infra/container checks not needed in M0).
- **Impact / follow-up:** Revisit when containerization and infrastructure milestones are reached.

## 2026-09-08 18:15 - IaC changed from Terraform to AWS CDK (TypeScript)
- **Decision:** Use AWS CDK with TypeScript instead of Terraform for all infrastructure as code.
- **Reason:** User preference. CDK uses TypeScript (already in the stack for the frontend), state is managed by CloudFormation (no separate state backend needed), and it integrates natively with AWS constructs.
- **Assumption / evidence:** CDK is a first-class AWS IaC tool. TypeScript CDK keeps the infra in the same language family as the frontend.
- **Alternatives considered:** Terraform (original plan — HCL-based, requires separate state management).
- **Impact / follow-up:** All project docs, skills, hooks, and rules updated. The `infra/` directory will contain a CDK TypeScript project. Security review skill renamed from terraform-security-review to cdk-security-review.

## 2026-09-08 20:00 - M1: Custom User model from day one
- **Decision:** Define a custom User model (AbstractUser subclass) with a role field (CUSTOMER/STAFF) in the accounts app from the first migration.
- **Reason:** Django strongly recommends setting AUTH_USER_MODEL before the first migration. Switching later requires complex migration surgery.
- **Assumption / evidence:** Django docs: "If you're starting a new project, it's highly recommended to set up a custom user model." Two roles suffice for the dual-portal design.
- **Alternatives considered:** Default auth.User + separate profile model (more indirection), third-party user package (unnecessary complexity).
- **Impact / follow-up:** All ForeignKey references to users use settings.AUTH_USER_MODEL. Role-based permissions will be built on this in M2.

## 2026-09-08 20:00 - M1: Ledger immutability enforced at service + admin layer
- **Decision:** Immutability of posted journal entries and lines is enforced in the ledger service (no mutation methods) and Django Admin (readonly_fields, has_change_permission=False, has_delete_permission=False). No database triggers.
- **Reason:** SQLite (dev) doesn't support triggers the same way PostgreSQL does. Service-layer enforcement is sufficient for this system and is explicit/testable. Admin safety prevents accidental mutations through the admin panel.
- **Assumption / evidence:** All financial writes go through the ledger service. Direct ORM access is a developer choice, not a user-facing path. Database-level constraints can be added in PostgreSQL for production hardening.
- **Alternatives considered:** PostgreSQL triggers (adds DB dependency for dev), Django model save() override (fragile, can be bypassed).
- **Impact / follow-up:** Tests verify no mutation path exists through the service layer.

## 2026-09-08 20:00 - M1: Commission rate stored as basis points
- **Decision:** Broker commission rates and tax/fee rates stored as integer basis points (e.g., 1500 = 15.00%, 350 = 3.50%).
- **Reason:** Avoids floating-point representation of percentages. Basis points are the industry standard for expressing rates in insurance.
- **Assumption / evidence:** 1 basis point = 0.01%. PositiveIntegerField gives exact integer arithmetic.
- **Alternatives considered:** Decimal field (adds Decimal arithmetic complexity), percentage as integer (less precise).
- **Impact / follow-up:** Pro-rata calculations in later milestones will multiply by bps and divide by 10000 with deterministic rounding.

## 2026-09-08 20:00 - M1: Ruff excludes auto-generated migration files
- **Decision:** Added `extend-exclude = ["*/migrations/*"]` to Ruff config.
- **Reason:** Django's auto-generated migration files have long lines that exceed the 120-character limit. These files are machine-generated and not meant for manual editing.
- **Assumption / evidence:** Standard practice in Django projects using Ruff or Black.
- **Alternatives considered:** Reformatting migrations (risky — can break them), wider line limit (dilutes the rule for hand-written code).
- **Impact / follow-up:** None. Migrations are still validated by Django's migration framework.

## 2026-09-08 22:00 - M2: California chosen as the single modeled US state (SUPERSEDED)
- **Decision:** California (CA) is the single US state modeled for v1 tax/fee implementation. Rules: CA Premium Tax (235 bps, refundable), CA FAIR Plan Surcharge (10 bps, non-refundable), CA Stamping Fee ($25.00 flat, non-refundable).
- **Reason:** California is the largest US insurance market. Modeling a real state's actual regulatory components demonstrates the system's ability to handle jurisdiction-specific rules.
- **Assumption / evidence:** Rates are representative but simplified for v1. The effective-dated TaxRule/FeeRule model supports future rate changes and additional jurisdictions.
- **Alternatives considered:** New York (complex surplus lines rules), Texas (no state income tax complicates modeling), fictional state (less realistic).
- **Impact / follow-up:** **Superseded by the Texas surplus-lines corrective patch below.**

## 2026-09-09 00:00 - Texas surplus-lines tax model replaces California
- **Decision:** Replaced California tax/fee rules with Texas surplus-lines model: TX Surplus Lines Premium Tax (485 bps, 4.85%, refundable) + TX SLTX Stamping Fee (4 bps, 0.04%, RATE fee, refundable). Both effective 2024-01-01.
- **Reason:** Texas surplus-lines is a cleaner, more representative model for CGL insurance. Two components (tax + stamping fee) with authoritative public sources. Both refundable on cancellation simplifies the refund flow.
- **Assumption / evidence:** Rates verified from Texas Comptroller Rule 3.820 and SLTX (Surplus Lines Stamping Office of Texas). 4.85% premium tax + 0.04% stamping fee.
- **Alternatives considered:** Keep California (3 components, mixed refundability, less commonly used for surplus-lines CGL demos).
- **Impact / follow-up:** All seed data, tests, and examples updated. Chart of accounts gained account 2150 (Stamping Fee Payable). Downstream PRDs (Stripe, Endorsements, Cancellation) updated to reference the TX model. Rate arithmetic switched from float to Decimal with ROUND_HALF_UP.

## 2026-09-08 22:00 - M2: Token authentication for static SPA
- **Decision:** Use DRF TokenAuthentication (+ SessionAuthentication for admin) rather than session-based auth.
- **Reason:** The Next.js frontend uses `output: "export"` (static SPA) served from a different origin than Django. Token auth works cross-origin without complex cookie configuration.
- **Assumption / evidence:** Tokens are stored in localStorage and sent as `Authorization: Token <key>` headers. CORS is configured for localhost:3000.
- **Alternatives considered:** JWT (more complex, token refresh needed), session auth with proxy (requires server runtime, violates static export requirement).
- **Impact / follow-up:** Token management in the frontend API client. Logout deletes the token server-side.

## 2026-09-08 22:00 - M2: Persona adapter with graceful degradation
- **Decision:** The Persona integration module (`integrations/persona/`) returns SIMULATED inquiry IDs when API credentials are not configured, rather than failing.
- **Reason:** Allows development and testing of the full KYB flow without requiring Persona sandbox credentials. The SIMULATED prefix is clearly labeled in the UI.
- **Assumption / evidence:** The webhook processing pipeline works identically for simulated and real inquiries. The state machine doesn't differentiate.
- **Alternatives considered:** Require credentials always (blocks development), mock at test level only (doesn't exercise the real code path in dev).
- **Impact / follow-up:** Live-fire testing with real Persona sandbox requires setting PERSONA_API_KEY, PERSONA_WEBHOOK_SECRET, and PERSONA_TEMPLATE_ID.

## 2026-09-08 22:00 - M2: Django 5.1 make_random_password deprecation
- **Decision:** Use `django.utils.crypto.get_random_string(20)` instead of `User.objects.make_random_password()` for generating random broker contact passwords.
- **Reason:** `BaseUserManager.make_random_password()` was removed in Django 5.1. `get_random_string` is the recommended replacement.
- **Assumption / evidence:** Django 5.1 release notes document the removal. Tests confirmed the AttributeError.
- **Alternatives considered:** `User().make_random_password()` (instance method, but requires creating a throw-away User object).
- **Impact / follow-up:** None. The password is random and temporary — broker contacts would use password reset.

## 2026-09-09 00:30 - M3: Stripe Checkout Sessions over Payment Intents
- **Decision:** Use Stripe Checkout Sessions (redirect flow) instead of the Payment Intents API with embedded UI elements.
- **Reason:** The frontend is a static SPA (`output: "export"`). Checkout Sessions let Stripe host the entire payment form — no need for client-side Stripe.js Elements, no PCI scope expansion, no server-side session management. The redirect pattern (success_url / cancel_url) works naturally with static pages.
- **Assumption / evidence:** Checkout Sessions support metadata (policy_id, policy_number), configurable success/cancel URLs, and fire `checkout.session.completed` / `checkout.session.expired` webhooks. This covers the full premium collection lifecycle.
- **Alternatives considered:** Payment Intents with Stripe.js Elements (requires client-side Stripe initialization, more complex state management, PCI considerations), Stripe Payment Links (less programmatic control).
- **Impact / follow-up:** Webhook integration is the primary payment confirmation path. The `checkout.session.completed` webhook triggers ledger posting and policy activation.

## 2026-09-09 00:30 - M3: Stripe adapter with SIMULATED fallback
- **Decision:** The Stripe integration module (`integrations/stripe/`) returns SIMULATED session IDs and checkout URLs when `STRIPE_SECRET_KEY` is not configured, mirroring the Persona adapter pattern.
- **Reason:** Allows the full payment flow (checkout creation → payment completion → ledger posting → policy activation) to be tested locally without Stripe credentials. A dedicated `/payments/<id>/simulate/` endpoint completes simulated payments.
- **Assumption / evidence:** The Persona adapter already established this pattern successfully. Simulated mode is clearly labeled in the UI with SIMULATED badges. All ledger and state machine logic is exercised identically.
- **Alternatives considered:** Require Stripe test keys always (blocks development), mock only in tests (doesn't exercise the real flow in dev).
- **Impact / follow-up:** Live-fire testing with real Stripe requires setting STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, and STRIPE_WEBHOOK_SECRET.

## 2026-09-09 00:30 - M3: Commission posted at payment time on collected premium
- **Decision:** Broker commission is calculated and posted to the ledger when premium payment succeeds, not at policy creation time. Commission is earned on premium only (not on tax or fees).
- **Reason:** Commission should be earned on collected revenue, not on quoted amounts. This aligns with the master plan ("commission on collected premium") and ensures the ledger reflects actual financial obligations.
- **Assumption / evidence:** Commission = `premium_cents × broker.commission_rate_bps / 10000` using Decimal arithmetic with ROUND_HALF_UP. Posted as DR 5100 Commission Expense / CR 2200 Broker Commission Payable.
- **Alternatives considered:** Post commission at policy creation (premature — money not yet collected), post at policy activation separate from payment (unnecessary complexity).
- **Impact / follow-up:** Endorsement premium changes in M4 will need to adjust commission. Cancellation in M6 will need commission clawback.

## 2026-09-09 00:30 - M3: Webhook boolean signature verification pattern
- **Decision:** `verify_stripe_signature()` returns a boolean (True/False) rather than the parsed event object, matching the `verify_persona_signature()` pattern.
- **Reason:** Consistency between provider webhook handlers. The view independently parses the JSON body after signature verification, keeping the verification function single-purpose.
- **Assumption / evidence:** Both Persona and Stripe webhook views follow the same pattern: verify signature → parse body → check idempotency → dispatch.
- **Alternatives considered:** Return the Stripe Event object from verify (couples verification with parsing, inconsistent with Persona handler).
- **Impact / follow-up:** None. The pattern is established for future provider integrations.

## 2026-09-09 02:00 - M4: Pro-rata endorsement pricing with Decimal arithmetic
- **Decision:** Pro-rata endorsement calculation uses `(annual_amount_cents × remaining_days) / total_days_in_term` with `Decimal` and `ROUND_HALF_UP`. Tax and fee adjustments on endorsements use the same effective-dated rates from policy inception.
- **Reason:** Deterministic, auditable rounding. Using inception-date rates ensures endorsement charges are consistent with the original policy charges regardless of any later rate changes.
- **Assumption / evidence:** Policy term uses calendar anniversary (366 days in leap years), matching the `calculate_policy_expiration()` logic. ROUND_HALF_UP is the documented rounding convention from M1.
- **Alternatives considered:** Banker's rounding (ROUND_HALF_EVEN — less intuitive for insurance), fixed 365-day terms (violates calendar-anniversary requirement).
- **Impact / follow-up:** Rounding residuals are deterministic. No ad-hoc penny spreading.

## 2026-09-09 02:00 - M4: Endorsement approval threshold at $500
- **Decision:** Customer approval is required when an endorsement's total charge (premium + tax + fees) exceeds $500 (`CUSTOMER_APPROVAL_THRESHOLD_CENTS = 50000`).
- **Reason:** PRD specifies "$500" as the threshold. Configured as a class constant on the Endorsement model for easy adjustment.
- **Assumption / evidence:** Threshold applies to the pro-rated total, not the annual delta. This is more customer-friendly and reflects the actual out-of-pocket charge.
- **Alternatives considered:** Threshold on annual delta (doesn't reflect pro-rata reality), configurable per-policy (over-engineered for v1).
- **Impact / follow-up:** Threshold can be moved to an admin-configurable setting in a future milestone.

## 2026-09-09 02:00 - M4: Correction auto-applies corrected endorsement
- **Decision:** When correcting an endorsement, the corrected replacement is always auto-applied (regardless of charge amount) since it replaces an already-applied endorsement.
- **Reason:** Corrections are staff-initiated adjustments to existing applied endorsements — the original was already paid and applied. Requiring re-approval or re-payment for a date correction would be incorrect workflow.
- **Assumption / evidence:** Correction = reversal + re-book per master plan. The original journal entries are reversed, policy premium reverted, then the corrected endorsement is created and applied in one atomic transaction.
- **Alternatives considered:** Require payment for corrections with higher pro-rata (adds complexity, poor UX for what is essentially a staff correction).
- **Impact / follow-up:** If the corrected endorsement results in additional premium due, it would need a separate collection mechanism in a future enhancement.

## 2026-09-09 02:00 - M4: PDF generation with reportlab
- **Decision:** Use `reportlab` (v5.0.1) for PDF generation rather than HTML-to-PDF tools.
- **Reason:** reportlab is a pure Python library with no system dependencies (no wkhtmltopdf, no headless browser). Generates PDFs directly from data, supports tables and formatting natively.
- **Assumption / evidence:** Declarations pages and endorsement schedules are data-driven documents, not complex layouts. reportlab handles this well.
- **Alternatives considered:** WeasyPrint (requires system libs), Playwright PDF (heavyweight, already have it for E2E), xhtml2pdf (limited, poorly maintained).
- **Impact / follow-up:** PDF templates can be enhanced with logos and more styling in later milestones.

## 2026-09-09 02:00 - M4: Query-param based detail pages for static export
- **Decision:** Policy detail pages use query params (`/staff/policies/detail?id=X`) instead of dynamic route segments (`/staff/policies/[id]`).
- **Reason:** Next.js with `output: "export"` requires `generateStaticParams` for dynamic segments, which can't enumerate all policy IDs at build time. Query params work universally with static export and `useSearchParams()` wrapped in Suspense.
- **Assumption / evidence:** Static export is a hard requirement per PRD. All existing pages use static routes.
- **Alternatives considered:** Dynamic segments with empty `generateStaticParams` (works for client-side nav but direct URL access 404s without server rewrite rules), hash-based routing (non-standard).
- **Impact / follow-up:** URLs are less clean but work correctly in all scenarios including page refresh.

## 2026-09-09 03:00 - M5: Append-only reserve model with ledger integration
- **Decision:** Reserve events are append-only (INITIAL, ADJUSTMENT, RELEASE). Each event posts balanced journal entries (DR 5000 Claims Expense / CR 2300 Claim Reserve for increases; reversed for decreases). Reserve balance is computed from the sum of all events.
- **Reason:** PRD mandates "never overwrite the reserve amount." Append-only events provide full audit trail and Incurred = Paid + Remaining Reserve identity.
- **Assumption / evidence:** Matches standard actuarial reserve accounting. Each reserve event has its own journal entry with idempotency key.
- **Alternatives considered:** Mutable reserve amount on claim (violates append-only rule), separate reserve ledger (over-engineering).
- **Impact / follow-up:** Reserve balance is always derivable from events. No single mutable field.

## 2026-09-09 03:00 - M5: Maker-checker with $5,000 approval threshold
- **Decision:** Claim payments >= $5,000 (500,000 cents) require approval from a second staff user (created_by != approved_by). Payments below threshold are auto-approved.
- **Reason:** PRD requires maker-checker for payments above a configured threshold. $5,000 is a reasonable operational threshold.
- **Assumption / evidence:** Uses the existing GenericForeignKey-based Approval model. The claims service enforces created_by != approved_by at the business logic level.
- **Alternatives considered:** All payments require approval (operational friction), threshold configurable per-policy (over-engineered for v1).
- **Impact / follow-up:** Threshold is a constant (`APPROVAL_THRESHOLD_CENTS`) that can be moved to admin config later.

## 2026-09-09 03:00 - M5: Bank verification and payout simulators
- **Decision:** Bank account verification and payout execution are SIMULATED, clearly labeled with "SIMULATED" provider tag and "SIM-BANK-" / "SIM-PAY-" reference prefixes.
- **Reason:** PRD requires these to be simulated in v1 behind an adapter for future Plaid/payment processor replacement. No real bank data stored.
- **Assumption / evidence:** Follows the same adapter pattern as Persona (SIM-INQ-) and Stripe (SIMULATED-) integrations from M2/M3.
- **Alternatives considered:** No simulation (blocks testing the payout flow), mock at test level only (doesn't exercise real code paths in dev).
- **Impact / follow-up:** PayoutDestination model stores verification state. Payout callbacks (settled/returned) update ledger entries.

## 2026-09-09 03:00 - M5: Policy coverage_limit_cents with $1M default
- **Decision:** Added `coverage_limit_cents` to Policy with a default of $1,000,000 (100,000,000 cents). Claim payments are validated against this limit including pending payments.
- **Reason:** PRD requires "payments must not exceed the applicable policy limit." $1M per-occurrence is a standard CGL default.
- **Assumption / evidence:** Per-occurrence limit is the standard CGL limit structure. The limit check includes all non-terminal payment statuses to prevent over-commitment.
- **Alternatives considered:** No limit field (can't enforce PRD requirement), separate limit model (over-engineered for v1).
- **Impact / follow-up:** Limit is editable via Django admin. Aggregate limits can be added in a future milestone.

## 2026-09-09 06:00 - M6: Pro-rata cancellation with refund-first ledger timing
- **Decision:** On cancellation, compute pro-rata refund and create a PENDING Refund record with Stripe refund initiated. Ledger entries are only posted when the provider confirms the refund (handle_refund_success), not at cancellation time.
- **Reason:** PRD rule: "Do not create a ledger row that pretends a refund happened before the rail moved." The ledger must reflect actual financial movements, not intent.
- **Assumption / evidence:** The same pattern as payment collection — ledger waits for provider confirmation.
- **Alternatives considered:** Post ledger at cancellation and reverse if refund fails (more complex, violates PRD rule), post refund payable immediately and settle later (overstates obligations).
- **Impact / follow-up:** Refund webhook (charge.refunded) triggers handle_refund_success which posts the balanced entry.

## 2026-09-09 06:00 - M6: Single refund against initial payment for V1
- **Decision:** Cancellation refund targets the initial payment only. Multi-payment scenarios (e.g., endorsement increases paid separately) are documented as a V2 edge case.
- **Reason:** V1 simplicity — the initial payment always covers the full premium. Endorsement premium increases create separate payments, but the vast majority of cancellations occur against the initial payment amount.
- **Assumption / evidence:** Total refund (unearned premium + refundable tax + refundable fees) will not exceed the initial payment amount for a single-endorsement policy.
- **Alternatives considered:** Multi-payment waterfall refund (complex, needed only for edge cases where endorsement increases + early cancellation exceed initial payment).
- **Impact / follow-up:** Document the limitation. If a refund exceeds the initial payment, the system will error — staff must handle manually or V2 implements multi-payment refund.

## 2026-09-09 06:00 - M6: Commission clawback as separate journal entry
- **Decision:** Commission clawback posts as a separate journal entry (DR 2200 Broker Commission Payable / CR 4200 Commission Clawback) with its own idempotency key, rather than as part of the refund entry.
- **Reason:** Clawback is a distinct financial event from the premium refund. Separate entries provide clearer audit trail and allow independent verification. Commission Clawback (4200) is a distinct revenue account from Commission Expense (5100).
- **Assumption / evidence:** Standard insurance accounting separates premium refunds from commission adjustments.
- **Alternatives considered:** Combined entry (harder to audit), DR 5100 CR 2200 reversal (would net out original commission, less clear).
- **Impact / follow-up:** Broker statements report clawback and commission separately.

## 2026-09-09 06:00 - M6: Broker statement reproducibility via unique_together
- **Decision:** BrokerStatement has unique_together on (broker, period_start, period_end). Re-running generation for the same period returns the existing statement unchanged.
- **Reason:** PRD requires statements to be reproducible. Once generated, the numbers are frozen — even if later refunds occur, they appear in the next period's statement.
- **Assumption / evidence:** Monthly statements are point-in-time snapshots of the ledger. This matches standard insurance billing cycles.
- **Alternatives considered:** Regenerate and overwrite (violates reproducibility), version-based (over-engineered for V1).
- **Impact / follow-up:** If a correction is needed, generate a new statement for a different period.

## 2026-09-09 00:00 - M7: Reconciliation run non-atomic outer to persist FAILED runs
- **Decision:** `run_reconciliation()` is NOT decorated with `@transaction.atomic`. The ReconciliationRun is created outside any transaction, reconciliation logic runs inside an inner `transaction.atomic()` block, and failure handling saves the FAILED status outside the rolled-back atomic block.
- **Reason:** If the entire function is atomic, a provider outage exception rolls back both the break records AND the FAILED-status save, leaving no trace of the failed run. The run record must persist for audit even when reconciliation fails.
- **Assumption / evidence:** Test `test_provider_outage_leaves_consistent_state` confirms FAILED run persists with error summary. Inner atomic ensures no partial breaks on failure.
- **Alternatives considered:** Savepoint with partial rollback (more complex), post-exception re-save outside transaction (fragile).
- **Impact / follow-up:** Staff can see failed runs in the UI and investigate provider issues.

## 2026-09-09 00:00 - M7: MCP server safety — write tool creates approval only
- **Decision:** The MCP `create_action_request` tool creates an Approval record in PENDING status with reason tagged `[MCP Agent]`. It never auto-approves, never mutates the ledger, and cannot bypass maker-checker.
- **Reason:** PRD rule: "Agent writes enter human approval" and "Maker cannot approve own action." The MCP surface must be safe by construction.
- **Assumption / evidence:** Tests verify: agent-created approvals are PENDING, `[MCP Agent]` tag in reason, no ledger mutation tools exposed, requesting user cannot approve own request.
- **Alternatives considered:** Allow agent to auto-approve small amounts (violates maker-checker invariant), expose ledger reads only (too restrictive for useful agent workflows).
- **Impact / follow-up:** All agent actions go through the normal staff approval queue.

## 2026-09-09 00:00 - M7: Stripe-side idempotency keys on outbound API calls
- **Decision:** Added `idempotency_key` parameter to `create_checkout_session()` and `create_stripe_refund()` outbound calls. Keys are passed via metadata and (for refunds) as Stripe's native idempotency_key parameter.
- **Reason:** Stripe's server-side idempotency ensures that network retries or duplicate calls from our side don't create duplicate charges or refunds.
- **Assumption / evidence:** Stripe caches the response for idempotency keys within 24 hours. This complements our webhook idempotency (inbound) with call-site idempotency (outbound).
- **Alternatives considered:** Rely only on webhook idempotency (doesn't prevent duplicate Stripe-side objects), generate keys at the Stripe client library level (less control over key semantics).
- **Impact / follow-up:** Cancellation refunds use `cancel-refund-{policy_id}` ensuring one refund per policy cancellation.

## 2026-09-09 00:00 - M7: SIMULATED records skipped in provider comparison
- **Decision:** Reconciliation skips records with SIMULATED-prefixed Stripe IDs when comparing against provider truth.
- **Reason:** SIMULATED records were never sent to Stripe, so they cannot appear in provider API responses. Comparing them would create false MISSING_IN_PROVIDER breaks.
- **Assumption / evidence:** All SIMULATED records are generated locally when `STRIPE_SECRET_KEY` is not set. In SIMULATED mode, `_get_provider_payments()` returns local records as provider truth, ensuring clean runs.
- **Alternatives considered:** Include SIMULATED in comparison (would require mock provider to return matching records), separate reconciliation mode for SIMULATED (over-engineering).
- **Impact / follow-up:** Live-fire with real Stripe will compare real PI IDs against real provider records.

## 2026-09-09 01:00 - M8: Multi-stage Docker build with uv
- **Decision:** Use a multi-stage Dockerfile: build stage installs deps with `uv sync --frozen --no-dev`, runtime stage copies only the venv and app code. Base image is pinned `python:3.12.12-slim`.
- **Reason:** Multi-stage reduces runtime image size (no build tools, no dev dependencies). Pinned base ensures reproducible builds. `uv` is faster than pip and respects the lockfile.
- **Assumption / evidence:** `uv.lock` provides deterministic dependency resolution. `--frozen` ensures the lockfile is authoritative.
- **Alternatives considered:** Single-stage with pip (larger image, slower), Alpine base (musl compatibility issues with some Python packages).
- **Impact / follow-up:** Image is ready for ECR push in M9.

## 2026-09-09 01:00 - M8: Gunicorn as production WSGI server
- **Decision:** Use Gunicorn (v23) as the production WSGI server. Workers default to `2 * CPU + 1`. Graceful timeout matches ECS SIGTERM behavior (30s).
- **Reason:** PRD mandates "never use Django runserver in the deployed image." Gunicorn is the standard Django production server, handles SIGTERM gracefully for ECS rolling deployments.
- **Assumption / evidence:** Sync workers are sufficient for this workload (no long-polling/websockets). ASGI not required.
- **Alternatives considered:** uWSGI (more complex config), Daphne/Uvicorn (ASGI not needed).
- **Impact / follow-up:** Worker count tunable via `WEB_CONCURRENCY` env var.

## 2026-09-09 01:00 - M8: Migrations as separate one-off task
- **Decision:** Migrations are NOT run on container startup. A separate `migrate` service in docker-compose (with `profiles: [migrate]`) runs migrations as a controlled one-off. In ECS, this becomes a separate ECS task.
- **Reason:** PRD requires: "Do not run database migrations automatically on every application container startup." Avoids race conditions with multiple containers and keeps the deployment model explicit.
- **Assumption / evidence:** ECS deployment model: build → push ECR → controlled migration task → deploy/update service.
- **Alternatives considered:** Entrypoint script with migration (violates PRD), init container (ECS Fargate doesn't support init containers natively).
- **Impact / follow-up:** M9 CDK will define a separate ECS task definition for migrations.

## 2026-09-09 01:00 - M8: Health endpoint at /health/
- **Decision:** Simple `GET /health/` endpoint returning `{"status": "ok"}` with no authentication required. Does not disclose secrets, environment details, or database status.
- **Reason:** PRD requires ALB-compatible health check. Minimal response avoids leaking operational details.
- **Assumption / evidence:** ALB health checks need a simple 200 response. Database connectivity is implicitly verified by the Django middleware stack.
- **Alternatives considered:** Include DB ping (adds latency, could cause health flapping), include version info (marginal value, potential info leak).
- **Impact / follow-up:** M9 ALB target group will point health checks at this endpoint.

## 2026-09-08 18:00 - Milestone reorder: infra and containerization moved to end
- **Decision:** Moved Django containerization from milestone 2 to milestone 8, and AWS infrastructure from milestone 3 to milestone 9. All feature milestones (2-7) are built and tested locally first.
- **Reason:** Build all domain features locally before dealing with deployment complexity. Faster iteration during the core build.
- **Assumption / evidence:** Local development with SQLite/PostgreSQL is sufficient for feature validation. T+24 gate shifts to after deployment milestones.
- **Alternatives considered:** Original order (containerize early, deploy early for T+24 gate mid-build).
- **Impact / follow-up:** T+24 deployed proof happens after milestone 9 instead of mid-build. Updated in 00_MASTER_PLAN.md.
