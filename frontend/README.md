# Corgi Frontend

Next.js static SPA for the Corgi Policy Administration System. Serves two user roles (Staff and Customer) with real-time updates via WebSocket.

## Architecture

```
                    Static Export (next build --output export)
                    ┌─────────────────────────────────────────────┐
                    │           S3 + CloudFront (prod)            │
                    │           localhost:3000 (dev)               │
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────────────┐
                    │              Next.js App Router              │
                    │          (all pages are client components)   │
                    │                                              │
                    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
                    │  │  /login  │  │/customer/*│  │ /staff/* │  │
                    │  └──────────┘  └──────────┘  └──────────┘  │
                    │                                              │
                    │  ┌──────────────────────────────────────┐   │
                    │  │         Shared Layer                  │   │
                    │  │  AuthProvider · WebSocketProvider     │   │
                    │  │  api.ts · useRealtimeRefresh          │   │
                    │  └──────────────────────────────────────┘   │
                    └──────────────────┬──────────────────────────┘
                                       │
                          ┌────────────┴────────────┐
                          │  HTTP (REST)  │  WebSocket │
                          │  /api/*       │  /ws/*     │
                          └────────────┬────────────┘
                                       │
                              Django Backend (:8000)
```

The app is built as a fully static export (`output: "export"` in `next.config.ts`). There are no server components, no API routes, and no SSR. In production, it is served from a private S3 bucket via CloudFront with OAC.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | Next.js 16 (App Router, static export) |
| Language | TypeScript 5 (strict) |
| React | React 19 |
| Styling | Tailwind CSS v4 |
| Components | shadcn/ui v4 (base-nova style, Base UI primitives) |
| Icons | lucide-react |
| Auth | Django REST Framework Token auth |
| Real-time | Native WebSocket with auto-reconnect |
| Forms | Controlled components with `useState` |

## Project Structure

```
frontend/
├── app/                        # Next.js App Router pages
│   ├── layout.tsx              # Root layout (AuthProvider + WebSocketProvider)
│   ├── page.tsx                # Redirect hub (routes by role)
│   ├── login/                  # Login page
│   ├── customer/               # Customer-facing pages
│   │   ├── policies/           # Policy list + detail
│   │   ├── claims/             # Claims list + submission
│   │   ├── payment-success/    # Stripe checkout callback (success)
│   │   └── payment-cancel/     # Stripe checkout callback (cancel)
│   └── staff/                  # Staff/admin pages
│       ├── brokers/            # Broker management + KYB
│       ├── policies/           # Policy list + creation + detail
│       ├── claims/             # Claims list + detail (reserves, payouts)
│       ├── payments/           # Payment management per policy
│       ├── reconciliation/     # Reconciliation runs + break resolution
│       └── statements/         # Broker commission statements
├── components/
│   ├── Nav.tsx                 # Role-aware navigation bar
│   ├── status-badge.tsx        # Domain status badge (maps ~40 statuses to variants)
│   └── ui/                     # 14 shadcn/ui components
├── lib/
│   ├── api.ts                  # API client (~45 endpoints) + TypeScript interfaces
│   ├── auth.tsx                # AuthProvider context (token + user state)
│   ├── websocket.tsx           # WebSocketProvider (auto-reconnect, prefix subscriptions)
│   ├── useRealtimeRefresh.ts   # Debounced WebSocket refresh hook
│   ├── format.ts               # formatCents() utility
│   └── utils.ts                # cn() class merge utility
├── public/                     # Static assets
├── next.config.ts              # Static export config
├── tsconfig.json               # TypeScript config (strict, path aliases)
├── components.json             # shadcn/ui config (base-nova style)
└── postcss.config.mjs          # Tailwind v4 PostCSS plugin
```

## Pages and Routes

### Authentication

| Route | Description |
|-------|-------------|
| `/` | Redirect hub: unauthenticated -> `/login`, STAFF -> `/staff/brokers`, CUSTOMER -> `/customer/policies` |
| `/login` | Username/password login with demo credential hints |

### Customer Pages

| Route | Description |
|-------|-------------|
| `/customer/policies` | Policy list with status badges, Pay Now / Decline actions, expandable payment history |
| `/customer/policies/detail?id=N` | Single policy: endorsement history, refunds, pending approvals, PDF downloads, historical as-of view |
| `/customer/claims` | Claims list and new claim submission form |
| `/customer/payment-success` | Post-Stripe callback: polls checkout verification, WebSocket auto-update |
| `/customer/payment-cancel` | Static cancellation confirmation |

### Staff Pages

| Route | Description |
|-------|-------------|
| `/staff/brokers` | Broker table, create broker form, KYB initiation (Stripe Connect / Persona / simulated) |
| `/staff/policies` | All policies table, create policy form (broker, customer, territory from API, premium with charge breakdown) |
| `/staff/policies/detail?id=N` | Policy management: endorsements (create, apply, correct), cancellation with pro-rata refund, effective date editing, PDF documents |
| `/staff/claims` | Claims table with status and financials |
| `/staff/claims/detail?id=N` | Claim lifecycle: reserves (initial, adjustment, release), payments (create, approve, execute payout), payout destinations |
| `/staff/payments` | Per-policy payment cards with charge breakdown (premium, tax, fees) and Stripe references |
| `/staff/reconciliation` | Trigger reconciliation runs, view breaks (MISSING_IN_LEDGER, AMOUNT_MISMATCH, etc.), resolve with notes |
| `/staff/statements` | Generate broker commission statements by period, view premium/commission/clawback/net due breakdown |

## Architecture Details

### API Layer (`lib/api.ts`)

Single centralized module with a typed `request<T>()` wrapper around `fetch()`. All ~45 API methods are grouped by domain:

```
Auth        login, logout, me, listCustomers
Brokers     listBrokers, getBroker, createBroker, initiateKyb
Policies    listPolicies, getPolicy, createPolicy, cancelPolicy, declinePolicy,
            updatePolicyEffectiveDate, getPolicyAsOf, listJurisdictions
Payments    createCheckout, listPolicyPayments, verifyCheckoutSession,
            simulatePayment, listPolicyRefunds, simulateRefund
Endorsements listEndorsements, createEndorsement, approveEndorsement,
            applyEndorsement, correctEndorsement
Claims      listClaims, getClaim, submitClaim, getClaimFinancials,
            listReserveEvents, setReserve, listClaimPayments,
            createClaimPayment, approveClaimPayment, executeClaimPayout,
            simulatePayoutCallback, getPayoutDestination, setPayoutDestination,
            verifyPayoutDestination
Reconciliation  listReconciliationRuns, triggerReconciliation,
            getReconciliationRun, listReconciliationBreaks, resolveBreak
Statements  listBrokerStatements, generateBrokerStatement, getBrokerStatement
```

Base URL: `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`).

Authentication: `Authorization: Token <key>` header attached automatically.

Errors: Custom `ApiError` class with HTTP status and parsed JSON body.

### Authentication (`lib/auth.tsx`)

```
Login ──► POST /api/auth/login/ ──► { token, user }
                                          │
                            Store token in localStorage
                            Hold in module-level variable
                                          │
App Load ──► Read token from localStorage ──► GET /api/auth/me/ ──► validate
```

- Two roles: `STAFF` and `CUSTOMER`
- Client-side route protection via `useAuth()` checks in `useEffect`
- Token format: Django REST Framework Token auth

### Real-time Updates (`lib/websocket.tsx` + `lib/useRealtimeRefresh.ts`)

```
Browser ──► ws[s]://<API_BASE>/ws/events/?token=<auth_token> ──► Django Channels

           ┌───────────────────────────────────────────────┐
           │            WebSocketProvider                    │
           │                                                │
           │  Incoming message { event: "policy.updated" }  │
           │         │                                      │
           │         ▼                                      │
           │  Match against subscriber prefixes             │
           │    "policy." ──► refresh policy list            │
           │    "payment." ──► refresh payment data          │
           │                                                │
           │  Auto-reconnect on close (3s delay)            │
           └───────────────────────────────────────────────┘
```

Event prefixes used across the app:

| Prefix | Triggers refresh on |
|--------|-------------------|
| `policy.` | Policy list/detail pages |
| `payment.` | Payment pages, policy lists |
| `endorsement.` | Policy detail pages |
| `refund.` | Policy detail, payment pages |
| `claim.` | Claims list/detail pages |
| `broker.` | Broker management page |
| `reconciliation.` | Reconciliation and statements pages |

The `useRealtimeRefresh` hook debounces callbacks (500ms default) to prevent rapid re-fetching.

### State Management

No global state library. Two React Context providers wrap the entire app:

| Provider | Purpose |
|----------|---------|
| `AuthProvider` | User session (user object, loading state, login/logout) |
| `WebSocketProvider` | WebSocket connection lifecycle, subscription registry |

All page data is local `useState` fetched in `useEffect`. There is no shared cache between pages.

### Money Handling

All monetary values are stored and transmitted as **integer cents** (`_cents` suffix on all fields). The `formatCents()` utility converts to `$X.XX` for display. Charge breakdowns (premium, tax, fees, total) are shown on payment and policy creation flows.

### Domain Types

All TypeScript interfaces live in `lib/api.ts`:

| Interface | Domain |
|-----------|--------|
| `User` | Auth (id, username, role) |
| `Broker`, `KYBVerification` | Broker onboarding |
| `Policy`, `PolicyDetail`, `AsOfSnapshot` | Policy lifecycle + history |
| `PaymentRecord`, `CheckoutResult` | Payments + Stripe checkout |
| `EndorsementRecord` | Policy endorsements |
| `ClaimRecord`, `ClaimDetail` | Claims |
| `ReserveEventRecord`, `ClaimPaymentRecord` | Claim financials |
| `PayoutDestinationRecord` | Claim payouts |
| `RefundRecord`, `CancellationResult` | Refunds + cancellation |
| `ReconciliationRunRecord`, `ReconciliationBreakRecord` | Reconciliation |
| `BrokerStatementRecord` | Broker statements |

### shadcn/ui Components

14 components installed (base-nova style with `@base-ui/react` primitives):

Alert, Badge, Button, Card, Dialog, Input, Label, Select, Separator, Skeleton, Table, Tabs, Textarea, Tooltip

Custom components: `Nav` (role-aware navigation), `StatusBadge` (maps ~40 domain statuses to badge variants).

## Development

### Prerequisites

- Node.js 18+
- Backend running at `http://localhost:8000` (or set `NEXT_PUBLIC_API_URL`)

### Setup

```bash
cd frontend
npm install
npm run dev
```

### Available Scripts

| Script | Command | Purpose |
|--------|---------|---------|
| `dev` | `next dev` | Development server with hot reload |
| `build` | `next build` | Static export to `out/` directory |
| `start` | `next start` | Serve production build locally |
| `lint` | `eslint` | Run ESLint |
| `typecheck` | `tsc --noEmit` | TypeScript type checking |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API base URL |

### Demo Credentials

| Role | Username | Password |
|------|----------|----------|
| Staff | `staff1` | `staffpass1` |
| Customer | `customer1` | `custpass1` |

## Production Deployment

The app builds to a static `out/` directory and is deployed to S3 + CloudFront:

1. `npm run build` produces static HTML/JS/CSS in `out/`
2. Files are synced to a private S3 bucket
3. CloudFront serves the content with OAC (no public bucket access)
4. SPA routing: 404/403 errors return `/index.html` for client-side routing
5. CloudFront path-based routing sends `/api/*`, `/webhooks/*`, `/admin/*`, `/ws/*` to the ALB

CDK handles build and deployment automatically via `BucketDeployment` in `FrontendStack`.
