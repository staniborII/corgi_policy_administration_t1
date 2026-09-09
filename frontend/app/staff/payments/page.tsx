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
    PENDING: "#f0ad4e",
    PROCESSING: "#0275d8",
    SUCCEEDED: "#5cb85c",
    FAILED: "#d9534f",
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

export default function StaffPaymentsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [payments, setPayments] = useState<Record<number, PaymentRecord[]>>({});
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [expandedPolicy, setExpandedPolicy] = useState<number | null>(null);
  const fetched = useRef(false);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "STAFF") {
      router.replace("/login");
      return;
    }
    if (fetched.current) return;
    fetched.current = true;
    let cancelled = false;
    setLoadingData(true);
    api.listPolicies()
      .then((data) => { if (!cancelled) setPolicies(data); })
      .catch(() => { if (!cancelled) setError("Failed to load policies."); })
      .finally(() => { if (!cancelled) setLoadingData(false); });
    return () => { cancelled = true; };
  }, [user, loading, router]);

  async function togglePayments(policyId: number) {
    if (expandedPolicy === policyId) {
      setExpandedPolicy(null);
      return;
    }
    setExpandedPolicy(policyId);
    if (!payments[policyId]) {
      try {
        const data = await api.listPolicyPayments(policyId);
        setPayments((prev) => ({ ...prev, [policyId]: data }));
      } catch {
        /* ignore */
      }
    }
  }

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 1000, margin: "0 auto" }}>
        <h1>Payment Management</h1>

        {error && <p style={{ color: "red" }}>{error}</p>}
        {loadingData && <p>Loading...</p>}
        {!loadingData && policies.length === 0 && <p>No policies found.</p>}

        {policies.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                <th style={{ padding: "0.5rem" }}>Policy #</th>
                <th style={{ padding: "0.5rem" }}>Status</th>
                <th style={{ padding: "0.5rem" }}>Premium</th>
                <th style={{ padding: "0.5rem" }}>Territory</th>
                <th style={{ padding: "0.5rem" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <>
                  <tr key={p.id} style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: "0.5rem" }}>{p.policy_number}</td>
                    <td style={{ padding: "0.5rem" }}>{statusBadge(p.status)}</td>
                    <td style={{ padding: "0.5rem" }}>{formatCents(p.premium_amount_cents)}</td>
                    <td style={{ padding: "0.5rem" }}>{p.coverage_territory}</td>
                    <td style={{ padding: "0.5rem" }}>
                      <button
                        onClick={() => togglePayments(p.id)}
                        style={{ fontSize: "0.85rem", cursor: "pointer", padding: "0.25rem 0.5rem" }}
                      >
                        {expandedPolicy === p.id ? "Hide Payments" : "View Payments"}
                      </button>
                    </td>
                  </tr>
                  {expandedPolicy === p.id && payments[p.id] && (
                    <tr key={`${p.id}-payments`}>
                      <td colSpan={5} style={{ padding: "0.5rem 1rem", backgroundColor: "#f9f9f9" }}>
                        {payments[p.id].length === 0 ? (
                          <p style={{ color: "#666", margin: "0.5rem 0" }}>No payments recorded.</p>
                        ) : (
                          payments[p.id].map((pay) => (
                            <div key={pay.id} style={{
                              padding: "0.75rem", border: "1px solid #eee",
                              borderRadius: 4, marginBottom: "0.5rem", backgroundColor: "#fff",
                            }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span>
                                  <strong>Payment #{pay.id}</strong> — {formatCents(pay.amount_cents)}
                                </span>
                                {statusBadge(pay.status)}
                              </div>
                              {pay.charges_snapshot && (
                                <div style={{ marginTop: "0.5rem", fontSize: "0.85rem", color: "#555" }}>
                                  <span>Premium: {formatCents(pay.charges_snapshot.premium_cents as number)}</span>
                                  {" | "}
                                  <span>Tax: {formatCents(pay.charges_snapshot.total_tax_cents as number)}</span>
                                  {" | "}
                                  <span>Fees: {formatCents(pay.charges_snapshot.total_fees_cents as number)}</span>
                                  {" | "}
                                  <strong>Total: {formatCents(pay.charges_snapshot.total_cents as number)}</strong>
                                </div>
                              )}
                              <div style={{ marginTop: "0.25rem", fontSize: "0.8rem", color: "#888" }}>
                                {pay.stripe_payment_intent_id && (
                                  <span>PI: {pay.stripe_payment_intent_id}</span>
                                )}
                                {pay.stripe_payment_intent_id && pay.stripe_payment_intent_id.startsWith("SIMULATED") && (
                                  <span style={{ marginLeft: "0.5rem", color: "#f0ad4e", fontWeight: "bold" }}>SIMULATED</span>
                                )}
                              </div>
                            </div>
                          ))
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </>
  );
}
