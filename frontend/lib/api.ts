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
};
