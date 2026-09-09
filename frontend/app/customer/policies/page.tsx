"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type Policy, type PaymentRecord } from "@/lib/api";
import Nav from "@/components/Nav";

function formatCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    DRAFT: "#0275d8",
    PENDING_PAYMENT: "#f0ad4e",
    ACTIVE: "#5cb85c",
    CANCELLED: "#d9534f",
    EXPIRED: "#999",
  };
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 4, fontSize: "0.8rem",
      backgroundColor: colors[status] || "#999", color: "#fff",
    }}>
      {status}
    </span>
  );
}

function paymentStatusBadge(status: string) {
  const colors: Record<string, string> = {
    PENDING: "#f0ad4e",
    PROCESSING: "#0275d8",
    SUCCEEDED: "#5cb85c",
    FAILED: "#d9534f",
  };
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 4, fontSize: "0.75rem",
      backgroundColor: colors[status] || "#999", color: "#fff",
    }}>
      {status}
    </span>
  );
}

export default function CustomerPoliciesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [paymentLoading, setPaymentLoading] = useState<number | null>(null);
  const [payments, setPayments] = useState<Record<number, PaymentRecord[]>>({});
  const fetched = useRef(false);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "CUSTOMER") {
      router.replace("/login");
    }
  }, [user, loading, router]);

  useEffect(() => {
    if (loading || !user || fetched.current) return;
    fetched.current = true;
    let cancelled = false;
    api.listPolicies()
      .then((data) => { if (!cancelled) setPolicies(data); })
      .catch(() => { if (!cancelled) setError("Failed to load policies."); })
      .finally(() => { if (!cancelled) setLoadingData(false); });
    return () => { cancelled = true; };
  }, [loading, user]);

  async function handlePay(policyId: number) {
    setPaymentLoading(policyId);
    setError("");
    try {
      const result = await api.createCheckout(policyId);
      if (result.checkout_url) {
        const url = result.checkout_url;
        requestAnimationFrame(() => { window.location.assign(url); });
      } else if (result.simulated) {
        await api.simulatePayment(result.payment_id);
        const data = await api.listPolicies();
        setPolicies(data);
      }
    } catch {
      setError("Failed to initiate payment.");
    } finally {
      setPaymentLoading(null);
    }
  }

  async function loadPayments(policyId: number) {
    try {
      const data = await api.listPolicyPayments(policyId);
      setPayments((prev) => ({ ...prev, [policyId]: data }));
    } catch {
      /* ignore */
    }
  }

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 900, margin: "0 auto" }}>
        <h1>My Policies</h1>

        {error && <p style={{ color: "red" }}>{error}</p>}
        {loadingData && <p>Loading...</p>}
        {!loadingData && policies.length === 0 && (
          <div style={{ padding: "2rem", textAlign: "center", color: "#666" }}>
            <p>No policies found.</p>
            <p>Your policies will appear here once created by Staff.</p>
          </div>
        )}

        {policies.length > 0 && (
          <div>
            {policies.map((p) => (
              <div key={p.id} style={{
                border: "1px solid #ddd", borderRadius: 4, padding: "1rem",
                marginBottom: "1rem",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h3 style={{ margin: 0 }}>
                    <a href={`/customer/policies/detail?id=${p.id}`} style={{ color: "#0275d8", textDecoration: "underline" }}>
                      {p.policy_number}
                    </a>
                  </h3>
                  {statusBadge(p.status)}
                </div>
                <div style={{ marginTop: "0.75rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", fontSize: "0.9rem" }}>
                  <div>Effective: {p.effective_date}</div>
                  <div>Expires: {p.expiration_date}</div>
                  <div>Premium: {formatCents(p.premium_amount_cents)}</div>
                  <div>Territory: {p.coverage_territory}</div>
                </div>

                {(p.status === "DRAFT" || p.status === "PENDING_PAYMENT") && (
                  <div style={{
                    marginTop: "0.75rem", padding: "0.75rem",
                    backgroundColor: "#fff3cd", borderRadius: 4,
                  }}>
                    <p style={{ margin: "0 0 0.5rem 0", fontSize: "0.85rem" }}>
                      Payment required to activate this policy.
                    </p>
                    <button
                      onClick={() => handlePay(p.id)}
                      disabled={paymentLoading === p.id}
                      style={{
                        padding: "0.5rem 1rem", backgroundColor: "#5cb85c",
                        color: "#fff", border: "none", borderRadius: 4, cursor: "pointer",
                      }}
                    >
                      {paymentLoading === p.id ? "Processing..." : "Pay Now"}
                    </button>
                  </div>
                )}

                {p.status === "ACTIVE" && (
                  <p style={{
                    marginTop: "0.75rem", padding: "0.5rem",
                    backgroundColor: "#d4edda", borderRadius: 4, fontSize: "0.85rem",
                  }}>
                    Policy is active. Coverage is in effect.
                  </p>
                )}

                <div style={{ marginTop: "0.5rem" }}>
                  <button
                    onClick={() => loadPayments(p.id)}
                    style={{ fontSize: "0.8rem", cursor: "pointer", background: "none", border: "none", color: "#0275d8", textDecoration: "underline" }}
                  >
                    View Payments
                  </button>
                  {payments[p.id] && (
                    <div style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                      {payments[p.id].length === 0 ? (
                        <p style={{ color: "#666" }}>No payments yet.</p>
                      ) : (
                        payments[p.id].map((pay) => (
                          <div key={pay.id} style={{
                            padding: "0.5rem", border: "1px solid #eee",
                            borderRadius: 4, marginBottom: "0.25rem",
                          }}>
                            <span>{formatCents(pay.amount_cents)}</span>
                            {" "}
                            {paymentStatusBadge(pay.status)}
                            {" "}
                            <span style={{ color: "#666" }}>{new Date(pay.created_at).toLocaleDateString()}</span>
                            {pay.stripe_payment_intent_id.startsWith("SIMULATED") && (
                              <span style={{ marginLeft: "0.5rem", fontSize: "0.75rem", color: "#f0ad4e" }}>SIMULATED</span>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
