"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  api,
  ApiError,
  type ClaimDetail,
  type ClaimPaymentRecord,
  type PayoutDestinationRecord,
  type ReserveEventRecord,
} from "@/lib/api";
import Nav from "@/components/Nav";

function formatCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function badge(s: string, colors: Record<string, string>) {
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 4, fontSize: "0.8rem",
      backgroundColor: colors[s] || "#999", color: "#fff",
    }}>
      {s.replace(/_/g, " ")}
    </span>
  );
}

const claimColors: Record<string, string> = {
  OPEN: "#0275d8", UNDER_REVIEW: "#f0ad4e", RESERVED: "#5bc0de",
  PAYMENT_PENDING: "#f0ad4e", PARTIALLY_PAID: "#0275d8", PAID: "#5cb85c", CLOSED: "#999",
};

const paymentColors: Record<string, string> = {
  DRAFT: "#999", PENDING_APPROVAL: "#f0ad4e", APPROVED: "#5cb85c",
  PENDING: "#0275d8", SETTLED: "#5cb85c", RETURNED: "#d9534f", FAILED: "#d9534f",
};

const verifyColors: Record<string, string> = {
  PENDING: "#f0ad4e", VERIFIED: "#5cb85c", FAILED: "#d9534f",
};

function ClaimDetailContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const claimId = Number(searchParams.get("id"));

  const [detail, setDetail] = useState<ClaimDetail | null>(null);
  const [reserves, setReserves] = useState<ReserveEventRecord[]>([]);
  const [payments, setPayments] = useState<ClaimPaymentRecord[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState("");
  const fetched = useRef(false);

  // Reserve form
  const [reserveAmount, setReserveAmount] = useState("");
  const [reserveType, setReserveType] = useState("INITIAL");
  const [reserveMemo, setReserveMemo] = useState("");

  // Payment form
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentPayee, setPaymentPayee] = useState("");

  // Payout destination form
  const [destPayeeName, setDestPayeeName] = useState("");
  const [destLastFour, setDestLastFour] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "STAFF") router.replace("/login");
  }, [user, loading, router]);

  const reload = useCallback(async () => {
    if (!claimId) return;
    try {
      const [d, r, p] = await Promise.all([
        api.getClaim(claimId),
        api.listReserveEvents(claimId),
        api.listClaimPayments(claimId),
      ]);
      setDetail(d);
      setReserves(r);
      setPayments(p);
    } catch {
      setError("Failed to load claim data.");
    } finally {
      setLoadingData(false);
    }
  }, [claimId]);

  useEffect(() => {
    if (loading || !user || fetched.current || !claimId) return;
    fetched.current = true;
    reload();
  }, [loading, user, claimId, reload]);

  function getErrorMessage(err: unknown): string {
    if (err instanceof ApiError) {
      const body = err.body as Record<string, unknown>;
      return (body.detail as string) || `API error ${err.status}`;
    }
    return err instanceof Error ? err.message : "An error occurred";
  }

  async function handleSetReserve(e: React.FormEvent) {
    e.preventDefault();
    setActionLoading("reserve");
    setError("");
    try {
      await api.setReserve(claimId, {
        amount_cents: Math.round(parseFloat(reserveAmount) * 100),
        reserve_type: reserveType,
        memo: reserveMemo,
      });
      setReserveAmount("");
      setReserveMemo("");
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleCreatePayment(e: React.FormEvent) {
    e.preventDefault();
    setActionLoading("payment");
    setError("");
    try {
      await api.createClaimPayment(claimId, {
        amount_cents: Math.round(parseFloat(paymentAmount) * 100),
        payee: paymentPayee,
      });
      setPaymentAmount("");
      setPaymentPayee("");
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleApprovePayment(paymentId: number) {
    setActionLoading(`approve-${paymentId}`);
    setError("");
    try {
      await api.approveClaimPayment(paymentId);
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleExecutePayout(paymentId: number) {
    setActionLoading(`execute-${paymentId}`);
    setError("");
    try {
      await api.executeClaimPayout(paymentId);
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleSimulateSettled(paymentId: number, ref: string, amount: number) {
    setActionLoading(`settle-${paymentId}`);
    setError("");
    try {
      await api.simulatePayoutCallback({ payout_reference: ref, event_type: "SETTLED", amount_cents: amount });
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleSimulateReturned(paymentId: number, ref: string) {
    setActionLoading(`return-${paymentId}`);
    setError("");
    try {
      await api.simulatePayoutCallback({ payout_reference: ref, event_type: "RETURNED", reason: "Simulated return" });
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleSetDestination(e: React.FormEvent) {
    e.preventDefault();
    setActionLoading("dest");
    setError("");
    try {
      await api.setPayoutDestination(claimId, {
        payee_name: destPayeeName,
        account_last_four: destLastFour,
      });
      setDestPayeeName("");
      setDestLastFour("");
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleVerifyDestination(outcome: string) {
    setActionLoading(`verify-${outcome}`);
    setError("");
    try {
      await api.verifyPayoutDestination(claimId, outcome);
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  if (loading || !user) return null;
  if (loadingData) return <><Nav /><main style={{ padding: "1.5rem" }}><p>Loading...</p></main></>;
  if (!detail) return <><Nav /><main style={{ padding: "1.5rem" }}><p>Claim not found.</p></main></>;

  const { claim, financials, payout_destination: dest } = detail;

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 1000, margin: "0 auto" }}>
        <a href="/staff/claims" style={{ color: "#0275d8", textDecoration: "underline" }}>&larr; Back to Claims</a>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.5rem" }}>
          <h1 style={{ margin: 0 }}>Claim {claim.claim_number}</h1>
          {badge(claim.status, claimColors)}
        </div>

        {error && <p style={{ color: "red", marginTop: "0.5rem" }}>{error}</p>}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "1rem", fontSize: "0.9rem" }}>
          <div>Date of Loss: {claim.date_of_loss}</div>
          <div>Reported: {new Date(claim.reported_at).toLocaleDateString()}</div>
          <div>Estimated: {claim.estimated_amount_cents ? formatCents(claim.estimated_amount_cents) : "—"}</div>
          <div>Description: {claim.description}</div>
        </div>

        {/* Financials */}
        <div style={{
          marginTop: "1.5rem", padding: "1rem", backgroundColor: "#f8f9fa",
          borderRadius: 4, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem",
        }}>
          <div>
            <div style={{ fontWeight: "bold", fontSize: "0.85rem", color: "#666" }}>Reserve</div>
            <div style={{ fontSize: "1.25rem" }}>{formatCents(financials.reserve_cents)}</div>
          </div>
          <div>
            <div style={{ fontWeight: "bold", fontSize: "0.85rem", color: "#666" }}>Paid</div>
            <div style={{ fontSize: "1.25rem" }}>{formatCents(financials.paid_cents)}</div>
          </div>
          <div>
            <div style={{ fontWeight: "bold", fontSize: "0.85rem", color: "#666" }}>Incurred</div>
            <div style={{ fontSize: "1.25rem" }}>{formatCents(financials.incurred_cents)}</div>
          </div>
        </div>

        {/* Payout Destination */}
        <h2 style={{ marginTop: "1.5rem" }}>Payout Destination</h2>
        {dest ? (
          <div style={{ border: "1px solid #ddd", borderRadius: 4, padding: "1rem", fontSize: "0.9rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <strong>{dest.payee_name}</strong> — ****{dest.account_last_four}
                <span style={{ marginLeft: "0.5rem", fontSize: "0.75rem", color: "#f0ad4e" }}>
                  [{dest.provider}]
                </span>
              </div>
              {badge(dest.verification_status, verifyColors)}
            </div>
            <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "#888" }}>
              Ref: {dest.provider_reference}
            </div>
            {dest.verification_status === "PENDING" && (
              <div style={{ marginTop: "0.5rem" }}>
                <button
                  onClick={() => handleVerifyDestination("VERIFIED")}
                  disabled={actionLoading.startsWith("verify")}
                  style={{ marginRight: "0.5rem", padding: "0.3rem 0.75rem", backgroundColor: "#5cb85c", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
                >
                  Simulate Verify
                </button>
                <button
                  onClick={() => handleVerifyDestination("FAILED")}
                  disabled={actionLoading.startsWith("verify")}
                  style={{ padding: "0.3rem 0.75rem", backgroundColor: "#d9534f", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
                >
                  Simulate Fail
                </button>
              </div>
            )}
          </div>
        ) : (
          <form onSubmit={handleSetDestination} style={{ border: "1px solid #ddd", borderRadius: 4, padding: "1rem" }}>
            <div style={{ marginBottom: "0.5rem" }}>
              <label style={{ display: "block", fontWeight: "bold", fontSize: "0.85rem" }}>Payee Name</label>
              <input value={destPayeeName} onChange={(e) => setDestPayeeName(e.target.value)} required style={{ width: "100%", padding: "0.4rem" }} />
            </div>
            <div style={{ marginBottom: "0.5rem" }}>
              <label style={{ display: "block", fontWeight: "bold", fontSize: "0.85rem" }}>Last 4 Digits</label>
              <input value={destLastFour} onChange={(e) => setDestLastFour(e.target.value)} required maxLength={4} minLength={4} style={{ width: "100%", padding: "0.4rem" }} />
            </div>
            <button type="submit" disabled={actionLoading === "dest"} style={{ padding: "0.3rem 0.75rem", backgroundColor: "#0275d8", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
              {actionLoading === "dest" ? "Setting..." : "Set Destination"}
            </button>
          </form>
        )}

        {/* Reserves */}
        <h2 style={{ marginTop: "1.5rem" }}>Reserve Events</h2>
        <form onSubmit={handleSetReserve} style={{ border: "1px solid #ddd", borderRadius: 4, padding: "1rem", marginBottom: "1rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 2fr", gap: "0.5rem" }}>
            <div>
              <label style={{ display: "block", fontWeight: "bold", fontSize: "0.85rem" }}>Amount ($)</label>
              <input type="number" step="0.01" value={reserveAmount} onChange={(e) => setReserveAmount(e.target.value)} required style={{ width: "100%", padding: "0.4rem" }} />
            </div>
            <div>
              <label style={{ display: "block", fontWeight: "bold", fontSize: "0.85rem" }}>Type</label>
              <select value={reserveType} onChange={(e) => setReserveType(e.target.value)} style={{ width: "100%", padding: "0.4rem" }}>
                <option value="INITIAL">Initial</option>
                <option value="ADJUSTMENT">Adjustment</option>
                <option value="RELEASE">Release</option>
              </select>
            </div>
            <div>
              <label style={{ display: "block", fontWeight: "bold", fontSize: "0.85rem" }}>Memo</label>
              <input value={reserveMemo} onChange={(e) => setReserveMemo(e.target.value)} style={{ width: "100%", padding: "0.4rem" }} />
            </div>
          </div>
          <button type="submit" disabled={actionLoading === "reserve"} style={{ marginTop: "0.5rem", padding: "0.3rem 0.75rem", backgroundColor: "#0275d8", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
            {actionLoading === "reserve" ? "Setting..." : "Add Reserve Event"}
          </button>
        </form>

        {reserves.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                <th style={{ padding: "0.4rem" }}>Type</th>
                <th style={{ padding: "0.4rem" }}>Amount</th>
                <th style={{ padding: "0.4rem" }}>Memo</th>
                <th style={{ padding: "0.4rem" }}>Date</th>
              </tr>
            </thead>
            <tbody>
              {reserves.map((r) => (
                <tr key={r.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "0.4rem" }}>{r.reserve_type}</td>
                  <td style={{ padding: "0.4rem" }}>{formatCents(r.amount_cents)}</td>
                  <td style={{ padding: "0.4rem" }}>{r.memo || "—"}</td>
                  <td style={{ padding: "0.4rem" }}>{new Date(r.recorded_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Payments */}
        <h2 style={{ marginTop: "1.5rem" }}>Payments</h2>
        <form onSubmit={handleCreatePayment} style={{ border: "1px solid #ddd", borderRadius: 4, padding: "1rem", marginBottom: "1rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "0.5rem" }}>
            <div>
              <label style={{ display: "block", fontWeight: "bold", fontSize: "0.85rem" }}>Amount ($)</label>
              <input type="number" step="0.01" min="0.01" value={paymentAmount} onChange={(e) => setPaymentAmount(e.target.value)} required style={{ width: "100%", padding: "0.4rem" }} />
            </div>
            <div>
              <label style={{ display: "block", fontWeight: "bold", fontSize: "0.85rem" }}>Payee</label>
              <input value={paymentPayee} onChange={(e) => setPaymentPayee(e.target.value)} required style={{ width: "100%", padding: "0.4rem" }} />
            </div>
          </div>
          <button type="submit" disabled={actionLoading === "payment"} style={{ marginTop: "0.5rem", padding: "0.3rem 0.75rem", backgroundColor: "#0275d8", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
            {actionLoading === "payment" ? "Creating..." : "Create Payment"}
          </button>
        </form>

        {payments.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                <th style={{ padding: "0.4rem" }}>ID</th>
                <th style={{ padding: "0.4rem" }}>Amount</th>
                <th style={{ padding: "0.4rem" }}>Payee</th>
                <th style={{ padding: "0.4rem" }}>Status</th>
                <th style={{ padding: "0.4rem" }}>Payout Ref</th>
                <th style={{ padding: "0.4rem" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "0.4rem" }}>{p.id}</td>
                  <td style={{ padding: "0.4rem" }}>{formatCents(p.amount_cents)}</td>
                  <td style={{ padding: "0.4rem" }}>{p.payee}</td>
                  <td style={{ padding: "0.4rem" }}>{badge(p.status, paymentColors)}</td>
                  <td style={{ padding: "0.4rem", fontSize: "0.75rem" }}>{p.payout_reference || "—"}</td>
                  <td style={{ padding: "0.4rem" }}>
                    {p.status === "PENDING_APPROVAL" && (
                      <button
                        onClick={() => handleApprovePayment(p.id)}
                        disabled={actionLoading === `approve-${p.id}`}
                        style={{ padding: "0.2rem 0.5rem", backgroundColor: "#5cb85c", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: "0.8rem", marginRight: "0.25rem" }}
                      >
                        Approve
                      </button>
                    )}
                    {p.status === "APPROVED" && (
                      <button
                        onClick={() => handleExecutePayout(p.id)}
                        disabled={actionLoading === `execute-${p.id}`}
                        style={{ padding: "0.2rem 0.5rem", backgroundColor: "#0275d8", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: "0.8rem", marginRight: "0.25rem" }}
                      >
                        Execute Payout
                      </button>
                    )}
                    {p.status === "PENDING" && p.payout_reference && (
                      <>
                        <button
                          onClick={() => handleSimulateSettled(p.id, p.payout_reference, p.amount_cents)}
                          disabled={actionLoading === `settle-${p.id}`}
                          style={{ padding: "0.2rem 0.5rem", backgroundColor: "#5cb85c", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: "0.8rem", marginRight: "0.25rem" }}
                        >
                          Sim Settle
                        </button>
                        <button
                          onClick={() => handleSimulateReturned(p.id, p.payout_reference)}
                          disabled={actionLoading === `return-${p.id}`}
                          style={{ padding: "0.2rem 0.5rem", backgroundColor: "#d9534f", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: "0.8rem" }}
                        >
                          Sim Return
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </>
  );
}

export default function StaffClaimDetailPage() {
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <ClaimDetailContent />
    </Suspense>
  );
}
