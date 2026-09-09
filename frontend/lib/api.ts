const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let token: string | null = null;

const isBrowser = typeof window !== "undefined";

export function setToken(t: string | null) {
  token = t;
  if (!isBrowser) return;
  if (t) {
    localStorage.setItem("auth_token", t);
  } else {
    localStorage.removeItem("auth_token");
  }
}

export function getToken(): string | null {
  if (!token && isBrowser) {
    token = localStorage.getItem("auth_token");
  }
  return token;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  const t = getToken();
  if (t) {
    headers["Authorization"] = `Token ${t}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: Record<string, unknown>,
  ) {
    super(`API error ${status}`);
  }
}

export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: "STAFF" | "CUSTOMER";
}

export interface Broker {
  id: number;
  company_name: string;
  commission_rate_bps: number;
  status: string;
  latest_kyb: { id: number; persona_inquiry_id: string; status: string } | null;
  created_at: string;
}

export interface Policy {
  id: number;
  policy_number: string;
  status: string;
  effective_date: string;
  expiration_date: string;
  premium_amount_cents: number;
  coverage_territory: string;
  customer: number;
  broker: number;
  created_at: string;
}

export interface PolicyDetail extends Policy {
  events: Array<{
    id: number;
    event_type: string;
    effective_at: string;
    data: Record<string, unknown>;
  }>;
}

export interface PaymentRecord {
  id: number;
  policy: number;
  amount_cents: number;
  status: string;
  stripe_payment_intent_id: string;
  stripe_checkout_session_id: string;
  charges_snapshot: Record<string, unknown> | null;
  effective_at: string;
  recorded_at: string;
  created_at: string;
}

export interface CheckoutResult {
  payment_id: number;
  checkout_url: string | null;
  session_id: string;
  simulated: boolean;
  charges: Record<string, unknown>;
}

export interface EndorsementRecord {
  id: number;
  policy: number;
  endorsement_number: string;
  endorsement_type: string;
  status: string;
  description: string;
  effective_date: string;
  annual_premium_delta_cents: number;
  premium_change_cents: number;
  charges_snapshot: Record<string, unknown> | null;
  correction_of: number | null;
  created_at: string;
  recorded_at: string;
}

export interface AsOfSnapshot {
  policy_number: string;
  status: string;
  effective_date: string;
  expiration_date: string;
  coverage_territory: string;
  base_premium_cents: number;
  effective_premium_cents: number;
  endorsements: Array<{
    id: number;
    endorsement_number: string;
    type: string;
    effective_date: string;
    annual_premium_delta_cents: number;
    premium_change_cents: number;
    description: string;
  }>;
  as_of: string;
  customer: string;
  broker: string;
}

export interface ClaimRecord {
  id: number;
  policy: number;
  claim_number: string;
  status: string;
  date_of_loss: string;
  description: string;
  estimated_amount_cents: number | null;
  reported_at: string;
  created_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface ClaimDetail {
  claim: ClaimRecord;
  financials: {
    reserve_cents: number;
    paid_cents: number;
    incurred_cents: number;
  };
  payout_destination: PayoutDestinationRecord | null;
}

export interface ReserveEventRecord {
  id: number;
  claim: number;
  amount_cents: number;
  reserve_type: string;
  effective_at: string;
  recorded_at: string;
  created_by: number | null;
  memo: string;
}

export interface ClaimPaymentRecord {
  id: number;
  claim: number;
  amount_cents: number;
  status: string;
  payee: string;
  effective_at: string;
  recorded_at: string;
  created_by: number | null;
  approved_by: number | null;
  payout_reference: string;
  created_at: string;
  updated_at: string;
}

export interface PayoutDestinationRecord {
  id: number;
  claim: number;
  payee_name: string;
  account_last_four: string;
  verification_status: string;
  provider: string;
  provider_reference: string;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RefundRecord {
  id: number;
  payment: number;
  amount_cents: number;
  status: string;
  stripe_refund_id: string;
  reason: string;
  charges_snapshot: Record<string, unknown> | null;
  effective_at: string;
  recorded_at: string;
  created_at: string;
}

export interface CancellationResult {
  policy: Policy;
  unearned_premium_cents: number;
  total_refundable_tax_cents: number;
  total_refundable_fees_cents: number;
  total_refund_cents: number;
  commission_clawback_cents: number;
  refund?: RefundRecord;
}

export interface BrokerStatementRecord {
  id: number;
  broker: number;
  broker_name: string;
  period_start: string;
  period_end: string;
  total_premium_cents: number;
  total_commission_cents: number;
  total_clawback_cents: number;
  net_due_cents: number;
  statement_data: Record<string, unknown>;
  is_closed: boolean;
  generated_at: string;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; user: User }>("/api/auth/login/", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  logout: () =>
    request<void>("/api/auth/logout/", { method: "POST" }),

  me: () =>
    request<User>("/api/auth/me/"),

  listBrokers: () =>
    request<Broker[]>("/api/brokers/"),

  getBroker: (id: number) =>
    request<Broker>(`/api/brokers/${id}/`),

  createBroker: (data: {
    company_name: string;
    commission_rate_bps: number;
    contact_email: string;
    contact_first_name: string;
    contact_last_name: string;
  }) =>
    request<Broker>("/api/brokers/", { method: "POST", body: JSON.stringify(data) }),

  initiateKyb: (brokerId: number) =>
    request<{ inquiry_id: string }>(`/api/brokers/${brokerId}/kyb/`, { method: "POST" }),

  listJurisdictions: () =>
    request<string[]>("/api/policies/jurisdictions/"),

  listPolicies: () =>
    request<Policy[]>("/api/policies/"),

  getPolicy: (id: number) =>
    request<PolicyDetail>(`/api/policies/${id}/`),

  createPolicy: (data: {
    customer_id: number;
    broker_id: number;
    effective_date: string;
    premium_amount_cents: number;
    coverage_territory: string;
  }) =>
    request<{ policy: Policy; charges: Record<string, unknown> }>("/api/policies/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  createCheckout: (policyId: number) =>
    request<CheckoutResult>("/api/payments/checkout/", {
      method: "POST",
      body: JSON.stringify({ policy_id: policyId }),
    }),

  listPolicyPayments: (policyId: number) =>
    request<PaymentRecord[]>(`/api/payments/policy/${policyId}/`),

  simulatePayment: (paymentId: number) =>
    request<PaymentRecord>(`/api/payments/${paymentId}/simulate/`, {
      method: "POST",
    }),

  listEndorsements: (policyId: number) =>
    request<EndorsementRecord[]>(`/api/endorsements/?policy_id=${policyId}`),

  createEndorsement: (data: {
    policy_id: number;
    endorsement_type: string;
    effective_date: string;
    annual_premium_delta_cents: number;
    description: string;
  }) =>
    request<{ endorsement: EndorsementRecord; charges: Record<string, unknown> }>("/api/endorsements/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  approveEndorsement: (endorsementId: number) =>
    request<EndorsementRecord>(`/api/endorsements/${endorsementId}/approve/`, {
      method: "POST",
    }),

  applyEndorsement: (endorsementId: number) =>
    request<EndorsementRecord>(`/api/endorsements/${endorsementId}/apply/`, {
      method: "POST",
    }),

  correctEndorsement: (endorsementId: number, correctedEffectiveDate: string) =>
    request<EndorsementRecord>(`/api/endorsements/${endorsementId}/correct/`, {
      method: "POST",
      body: JSON.stringify({ corrected_effective_date: correctedEffectiveDate }),
    }),

  getPolicyAsOf: (policyId: number, asOf?: string) =>
    request<AsOfSnapshot>(`/api/policies/${policyId}/as-of/${asOf ? `?as_of=${encodeURIComponent(asOf)}` : ""}`),

  // Claims
  listClaims: (policyId?: number) =>
    request<ClaimRecord[]>(`/api/claims/${policyId ? `?policy_id=${policyId}` : ""}`),

  getClaim: (id: number) =>
    request<ClaimDetail>(`/api/claims/${id}/`),

  submitClaim: (data: {
    policy_id: number;
    date_of_loss: string;
    description: string;
    estimated_amount_cents?: number;
  }) =>
    request<ClaimRecord>("/api/claims/", { method: "POST", body: JSON.stringify(data) }),

  getClaimFinancials: (claimId: number) =>
    request<{ reserve_cents: number; paid_cents: number; incurred_cents: number }>(
      `/api/claims/${claimId}/financials/`
    ),

  listReserveEvents: (claimId: number) =>
    request<ReserveEventRecord[]>(`/api/claims/${claimId}/reserves/`),

  setReserve: (claimId: number, data: { amount_cents: number; reserve_type: string; memo?: string }) =>
    request<ReserveEventRecord>(`/api/claims/${claimId}/reserves/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listClaimPayments: (claimId: number) =>
    request<ClaimPaymentRecord[]>(`/api/claims/${claimId}/payments/`),

  createClaimPayment: (claimId: number, data: { amount_cents: number; payee: string }) =>
    request<ClaimPaymentRecord>(`/api/claims/${claimId}/payments/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  approveClaimPayment: (paymentId: number) =>
    request<ClaimPaymentRecord>(`/api/claims/payments/${paymentId}/approve/`, { method: "POST" }),

  executeClaimPayout: (paymentId: number) =>
    request<ClaimPaymentRecord>(`/api/claims/payments/${paymentId}/execute/`, { method: "POST" }),

  simulatePayoutCallback: (data: { payout_reference: string; event_type: string; amount_cents?: number; reason?: string }) =>
    request<ClaimPaymentRecord>("/api/claims/payout-callback/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getPayoutDestination: (claimId: number) =>
    request<PayoutDestinationRecord>(`/api/claims/${claimId}/payout-destination/`),

  setPayoutDestination: (claimId: number, data: { payee_name: string; account_last_four: string }) =>
    request<PayoutDestinationRecord>(`/api/claims/${claimId}/payout-destination/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  verifyPayoutDestination: (claimId: number, outcome: string) =>
    request<PayoutDestinationRecord>(`/api/claims/${claimId}/payout-destination/verify/`, {
      method: "POST",
      body: JSON.stringify({ outcome }),
    }),

  // Cancellation & Refunds
  cancelPolicy: (policyId: number, cancellationDate?: string) =>
    request<CancellationResult>(`/api/policies/${policyId}/cancel/`, {
      method: "POST",
      body: JSON.stringify(cancellationDate ? { cancellation_date: cancellationDate } : {}),
    }),

  listPolicyRefunds: (policyId: number) =>
    request<RefundRecord[]>(`/api/payments/policy/${policyId}/refunds/`),

  simulateRefund: (refundId: number) =>
    request<RefundRecord>(`/api/payments/refunds/${refundId}/simulate/`, { method: "POST" }),

  // Broker Statements
  listBrokerStatements: (brokerId?: number) =>
    request<BrokerStatementRecord[]>(`/api/reconciliation/broker-statements/${brokerId ? `?broker_id=${brokerId}` : ""}`),

  generateBrokerStatement: (data: { broker_id: number; period_start: string; period_end: string }) =>
    request<BrokerStatementRecord>("/api/reconciliation/broker-statements/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getBrokerStatement: (id: number) =>
    request<BrokerStatementRecord>(`/api/reconciliation/broker-statements/${id}/`),
};
