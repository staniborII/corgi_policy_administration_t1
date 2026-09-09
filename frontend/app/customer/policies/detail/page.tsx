"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  api,
  type Policy,
  type EndorsementRecord,
  type AsOfSnapshot,
  type RefundRecord,
  ApiError,
} from "@/lib/api";
import Nav from "@/components/Nav";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    DRAFT: "#0275d8",
    PENDING_PAYMENT: "#f0ad4e",
    PENDING_CUSTOMER_APPROVAL: "#e67e22",
    ACTIVE: "#5cb85c",
    APPLIED: "#5cb85c",
    APPROVED: "#28a745",
    REVERSED: "#d9534f",
    CANCELLED: "#d9534f",
    EXPIRED: "#999",
  };
  return (
    <span
      style={{
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: "0.8rem",
        backgroundColor: colors[status] || "#999",
        color: "#fff",
      }}
    >
      {status}
    </span>
  );
}

export default function CustomerPolicyDetailPage() {
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <CustomerPolicyDetailContent />
    </Suspense>
  );
}

function CustomerPolicyDetailContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const policyId = searchParams.get("id");

  const [policy, setPolicy] = useState<Policy | null>(null);
  const [endorsements, setEndorsements] = useState<EndorsementRecord[]>([]);
  const [refunds, setRefunds] = useState<RefundRecord[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const [asOfDate, setAsOfDate] = useState("");
  const [asOfSnapshot, setAsOfSnapshot] = useState<AsOfSnapshot | null>(null);
  const [loadingAsOf, setLoadingAsOf] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "CUSTOMER") {
      router.replace("/login");
      return;
    }
    if (!policyId) {
      router.replace("/customer/policies");
      return;
    }
    loadData();
  }, [user, loading, router, policyId]);

  async function loadData() {
    if (!policyId) return;
    setLoadingData(true);
    try {
      const [p, e, r] = await Promise.all([
        api.getPolicy(parseInt(policyId, 10)),
        api.listEndorsements(parseInt(policyId, 10)),
        api.listPolicyRefunds(parseInt(policyId, 10)),
      ]);
      setPolicy(p);
      setEndorsements(e);
      setRefunds(r);
    } catch {
      setError("Failed to load policy data.");
    } finally {
      setLoadingData(false);
    }
  }

  async function handleApprove(endorsementId: number) {
    setActionLoading(endorsementId);
    setError("");
    try {
      await api.approveEndorsement(endorsementId);
      await loadData();
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to approve endorsement.");
    } finally {
      setActionLoading(null);
    }
  }

  async function handlePayEndorsement(policyIdNum: number) {
    setError("");
    try {
      const result = await api.createCheckout(policyIdNum);
      if (result.checkout_url) {
        window.location.assign(result.checkout_url);
      } else if (result.simulated) {
        await api.simulatePayment(result.payment_id);
        await loadData();
      }
    } catch {
      setError("Failed to initiate payment.");
    }
  }

  async function handleAsOf() {
    if (!policyId) return;
    setLoadingAsOf(true);
    try {
      const snapshot = await api.getPolicyAsOf(
        parseInt(policyId, 10),
        asOfDate ? new Date(asOfDate).toISOString() : undefined,
      );
      setAsOfSnapshot(snapshot);
    } catch {
      setError("Failed to load historical view.");
    } finally {
      setLoadingAsOf(false);
    }
  }

  function pdfUrl(type: "declarations" | "endorsement-schedule", asOf?: string) {
    const base = `${API_BASE}/api/documents/policy/${policyId}/${type}/`;
    return asOf ? `${base}?as_of=${encodeURIComponent(new Date(asOf).toISOString())}` : base;
  }

  if (loading || !user) return null;
  if (loadingData) {
    return (
      <>
        <Nav />
        <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 900, margin: "0 auto" }}>
          <p>Loading...</p>
        </main>
      </>
    );
  }

  if (!policy) {
    return (
      <>
        <Nav />
        <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 900, margin: "0 auto" }}>
          <p style={{ color: "red" }}>{error || "Policy not found."}</p>
          <button onClick={() => router.push("/customer/policies")} style={{ padding: "0.5rem 1rem" }}>
            Back to My Policies
          </button>
        </main>
      </>
    );
  }

  const pendingApproval = endorsements.filter((e) => e.status === "PENDING_CUSTOMER_APPROVAL");
  const hasPendingPayment = endorsements.some((e) => e.status === "PENDING_PAYMENT");

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 900, margin: "0 auto" }}>
        <button onClick={() => router.push("/customer/policies")} style={{ marginBottom: "1rem", cursor: "pointer", background: "none", border: "none", color: "#0275d8", fontSize: "0.9rem" }}>
          &larr; Back to My Policies
        </button>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h1 style={{ margin: 0 }}>{policy.policy_number}</h1>
          {statusBadge(policy.status)}
        </div>

        <div style={{ marginTop: "1rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", fontSize: "0.9rem" }}>
          <div>Effective: {policy.effective_date}</div>
          <div>Expires: {policy.expiration_date}</div>
          <div>Premium: {formatCents(policy.premium_amount_cents)}</div>
          <div>Territory: {policy.coverage_territory}</div>
        </div>

        {error && <p style={{ color: "red", marginTop: "0.5rem" }}>{error}</p>}

        {/* Pending Approvals */}
        {pendingApproval.length > 0 && (
          <div style={{ marginTop: "1.5rem", padding: "1rem", border: "2px solid #e67e22", borderRadius: 4, backgroundColor: "#fff8f0" }}>
            <h3 style={{ marginTop: 0, color: "#e67e22" }}>Endorsements Requiring Your Approval</h3>
            {pendingApproval.map((e) => (
              <div key={e.id} style={{ padding: "0.75rem", border: "1px solid #eee", borderRadius: 4, marginBottom: "0.5rem", backgroundColor: "#fff" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong>{e.endorsement_number}</strong>
                  {statusBadge(e.status)}
                </div>
                <p style={{ fontSize: "0.85rem", margin: "0.5rem 0" }}>{e.description}</p>
                <div style={{ fontSize: "0.85rem", color: "#666" }}>
                  <span>Type: {e.endorsement_type}</span>
                  {" | "}
                  <span>Effective: {e.effective_date}</span>
                  {" | "}
                  <span>Premium Change: {formatCents(e.premium_change_cents)}</span>
                </div>
                {e.charges_snapshot && (
                  <div style={{ fontSize: "0.85rem", marginTop: "0.25rem" }}>
                    Total Due: <strong>{formatCents(e.charges_snapshot.total_cents as number)}</strong>
                  </div>
                )}
                <button
                  onClick={() => handleApprove(e.id)}
                  disabled={actionLoading === e.id}
                  style={{ marginTop: "0.5rem", padding: "0.4rem 1rem", backgroundColor: "#28a745", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
                >
                  {actionLoading === e.id ? "Approving..." : "Approve Endorsement"}
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Pending Payment Notice */}
        {hasPendingPayment && (
          <div style={{ marginTop: "1rem", padding: "0.75rem", backgroundColor: "#fff3cd", borderRadius: 4 }}>
            <p style={{ margin: "0 0 0.5rem 0", fontSize: "0.85rem" }}>
              Additional payment required for endorsed changes.
            </p>
            <button
              onClick={() => handlePayEndorsement(policy.id)}
              style={{ padding: "0.5rem 1rem", backgroundColor: "#5cb85c", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
            >
              Pay Additional Premium
            </button>
          </div>
        )}

        {/* Documents */}
        <div style={{ marginTop: "1.5rem", padding: "1rem", border: "1px solid #ddd", borderRadius: 4 }}>
          <h3 style={{ marginTop: 0 }}>Documents</h3>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <a href={pdfUrl("declarations")} style={{ padding: "0.5rem 1rem", backgroundColor: "#0275d8", color: "#fff", borderRadius: 4, textDecoration: "none", fontSize: "0.85rem" }}>
              Download Declarations
            </a>
            <a href={pdfUrl("endorsement-schedule")} style={{ padding: "0.5rem 1rem", backgroundColor: "#0275d8", color: "#fff", borderRadius: 4, textDecoration: "none", fontSize: "0.85rem" }}>
              Download Endorsement Schedule
            </a>
          </div>
        </div>

        {/* Historical View */}
        <div style={{ marginTop: "1.5rem", padding: "1rem", border: "1px solid #ddd", borderRadius: 4 }}>
          <h3 style={{ marginTop: 0 }}>Historical View (As-Of)</h3>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <input
              type="datetime-local"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
              style={{ padding: "0.4rem" }}
            />
            <button onClick={handleAsOf} disabled={loadingAsOf} style={{ padding: "0.4rem 1rem" }}>
              {loadingAsOf ? "Loading..." : "View"}
            </button>
          </div>

          {asOfSnapshot && (
            <div style={{ marginTop: "0.75rem", padding: "0.75rem", backgroundColor: "#f0f7ff", borderRadius: 4 }}>
              <p><strong>As of:</strong> {new Date(asOfSnapshot.as_of).toLocaleString()}</p>
              <p>Effective Premium: {formatCents(asOfSnapshot.effective_premium_cents)}</p>
              {asOfSnapshot.endorsements.length > 0 ? (
                <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "0.5rem", fontSize: "0.85rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>
                      <th style={{ padding: "0.25rem" }}>Number</th>
                      <th style={{ padding: "0.25rem" }}>Effective</th>
                      <th style={{ padding: "0.25rem" }}>Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {asOfSnapshot.endorsements.map((e) => (
                      <tr key={e.id} style={{ borderBottom: "1px solid #eee" }}>
                        <td style={{ padding: "0.25rem" }}>{e.endorsement_number}</td>
                        <td style={{ padding: "0.25rem" }}>{e.effective_date}</td>
                        <td style={{ padding: "0.25rem" }}>{formatCents(e.premium_change_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p style={{ fontSize: "0.85rem", color: "#666" }}>No endorsements at that time.</p>
              )}
            </div>
          )}
        </div>

        {/* All Endorsements */}
        <div style={{ marginTop: "1.5rem" }}>
          <h2>Endorsement History</h2>
          {endorsements.length === 0 && <p style={{ color: "#666" }}>No endorsements on this policy.</p>}
          {endorsements.length > 0 && (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                  <th style={{ padding: "0.5rem" }}>Number</th>
                  <th style={{ padding: "0.5rem" }}>Status</th>
                  <th style={{ padding: "0.5rem" }}>Effective</th>
                  <th style={{ padding: "0.5rem" }}>Premium Change</th>
                  <th style={{ padding: "0.5rem" }}>Description</th>
                </tr>
              </thead>
              <tbody>
                {endorsements.map((e) => (
                  <tr key={e.id} style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{e.endorsement_number}</td>
                    <td style={{ padding: "0.5rem" }}>{statusBadge(e.status)}</td>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{e.effective_date}</td>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{formatCents(e.premium_change_cents)}</td>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{e.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Refunds */}
        {refunds.length > 0 && (
          <div style={{ marginTop: "1.5rem" }}>
            <h2>Refunds</h2>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                  <th style={{ padding: "0.5rem" }}>Amount</th>
                  <th style={{ padding: "0.5rem" }}>Status</th>
                  <th style={{ padding: "0.5rem" }}>Reason</th>
                  <th style={{ padding: "0.5rem" }}>Date</th>
                </tr>
              </thead>
              <tbody>
                {refunds.map((r) => (
                  <tr key={r.id} style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{formatCents(r.amount_cents)}</td>
                    <td style={{ padding: "0.5rem" }}>{statusBadge(r.status)}</td>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{r.reason}</td>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{new Date(r.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </>
  );
}
