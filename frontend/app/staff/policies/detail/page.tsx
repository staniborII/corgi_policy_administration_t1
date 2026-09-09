"use client";

import { Suspense, useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  api,
  type Policy,
  type EndorsementRecord,
  type AsOfSnapshot,
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

export default function StaffPolicyDetailPage() {
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <StaffPolicyDetailContent />
    </Suspense>
  );
}

function StaffPolicyDetailContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const policyId = searchParams.get("id");

  const [policy, setPolicy] = useState<Policy | null>(null);
  const [endorsements, setEndorsements] = useState<EndorsementRecord[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [endForm, setEndForm] = useState({
    endorsement_type: "COVERAGE_LIMIT_CHANGE",
    effective_date: "",
    annual_premium_delta_cents: "",
    description: "",
  });
  const [createError, setCreateError] = useState("");
  const [creating, setCreating] = useState(false);
  const [lastCharges, setLastCharges] = useState<Record<string, unknown> | null>(null);

  const [showCorrect, setShowCorrect] = useState<number | null>(null);
  const [correctDate, setCorrectDate] = useState("");
  const [correctError, setCorrectError] = useState("");

  const [asOfDate, setAsOfDate] = useState("");
  const [asOfSnapshot, setAsOfSnapshot] = useState<AsOfSnapshot | null>(null);
  const [loadingAsOf, setLoadingAsOf] = useState(false);

  const [actionLoading, setActionLoading] = useState<number | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "STAFF") {
      router.replace("/login");
      return;
    }
    if (!policyId) {
      router.replace("/staff/policies");
      return;
    }
    loadData();
  }, [user, loading, router, policyId]);

  async function loadData() {
    if (!policyId) return;
    setLoadingData(true);
    try {
      const [p, e] = await Promise.all([
        api.getPolicy(parseInt(policyId, 10)),
        api.listEndorsements(parseInt(policyId, 10)),
      ]);
      setPolicy(p);
      setEndorsements(e);
    } catch {
      setError("Failed to load policy data.");
    } finally {
      setLoadingData(false);
    }
  }

  async function handleCreateEndorsement(e: FormEvent) {
    e.preventDefault();
    if (!policyId) return;
    setCreateError("");
    setCreating(true);
    setLastCharges(null);
    try {
      const result = await api.createEndorsement({
        policy_id: parseInt(policyId, 10),
        endorsement_type: endForm.endorsement_type,
        effective_date: endForm.effective_date,
        annual_premium_delta_cents: parseInt(endForm.annual_premium_delta_cents, 10),
        description: endForm.description,
      });
      setLastCharges(result.charges);
      setShowCreate(false);
      setEndForm({
        endorsement_type: "COVERAGE_LIMIT_CHANGE",
        effective_date: "",
        annual_premium_delta_cents: "",
        description: "",
      });
      await loadData();
    } catch (err) {
      setCreateError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to create endorsement.");
    } finally {
      setCreating(false);
    }
  }

  async function handleApply(endorsementId: number) {
    setActionLoading(endorsementId);
    try {
      await api.applyEndorsement(endorsementId);
      await loadData();
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to apply endorsement.");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleCorrect(endorsementId: number) {
    if (!correctDate) return;
    setCorrectError("");
    setActionLoading(endorsementId);
    try {
      await api.correctEndorsement(endorsementId, correctDate);
      setShowCorrect(null);
      setCorrectDate("");
      await loadData();
    } catch (err) {
      setCorrectError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to correct endorsement.");
    } finally {
      setActionLoading(null);
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
      setError("Failed to load as-of snapshot.");
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
          <button onClick={() => router.push("/staff/policies")} style={{ padding: "0.5rem 1rem" }}>
            Back to Policies
          </button>
        </main>
      </>
    );
  }

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 900, margin: "0 auto" }}>
        <button onClick={() => router.push("/staff/policies")} style={{ marginBottom: "1rem", cursor: "pointer", background: "none", border: "none", color: "#0275d8", fontSize: "0.9rem" }}>
          &larr; Back to Policies
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

        {/* PDF Downloads */}
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

        {/* As-Of View */}
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
              {loadingAsOf ? "Loading..." : "View As-Of"}
            </button>
            {asOfDate && (
              <>
                <a href={pdfUrl("declarations", asOfDate)} style={{ fontSize: "0.85rem", color: "#0275d8" }}>
                  Declarations PDF (as-of)
                </a>
                <a href={pdfUrl("endorsement-schedule", asOfDate)} style={{ fontSize: "0.85rem", color: "#0275d8" }}>
                  Schedule PDF (as-of)
                </a>
              </>
            )}
          </div>

          {asOfSnapshot && (
            <div style={{ marginTop: "0.75rem", padding: "0.75rem", backgroundColor: "#f0f7ff", borderRadius: 4 }}>
              <p><strong>Policy state as of:</strong> {new Date(asOfSnapshot.as_of).toLocaleString()}</p>
              <p>Effective Premium: {formatCents(asOfSnapshot.effective_premium_cents)}</p>
              <p>Base Premium: {formatCents(asOfSnapshot.base_premium_cents)}</p>
              {asOfSnapshot.endorsements.length > 0 && (
                <div style={{ marginTop: "0.5rem" }}>
                  <strong>Endorsements at that time:</strong>
                  <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "0.25rem", fontSize: "0.85rem" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>
                        <th style={{ padding: "0.25rem" }}>#</th>
                        <th style={{ padding: "0.25rem" }}>Type</th>
                        <th style={{ padding: "0.25rem" }}>Effective</th>
                        <th style={{ padding: "0.25rem" }}>Premium Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {asOfSnapshot.endorsements.map((e) => (
                        <tr key={e.id} style={{ borderBottom: "1px solid #eee" }}>
                          <td style={{ padding: "0.25rem" }}>{e.endorsement_number}</td>
                          <td style={{ padding: "0.25rem" }}>{e.type}</td>
                          <td style={{ padding: "0.25rem" }}>{e.effective_date}</td>
                          <td style={{ padding: "0.25rem" }}>{formatCents(e.premium_change_cents)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {asOfSnapshot.endorsements.length === 0 && (
                <p style={{ fontSize: "0.85rem", color: "#666" }}>No endorsements at that point in time.</p>
              )}
            </div>
          )}
        </div>

        {/* Endorsements Section */}
        <div style={{ marginTop: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2>Endorsements</h2>
            {policy.status === "ACTIVE" && (
              <button onClick={() => setShowCreate(!showCreate)} style={{ padding: "0.5rem 1rem" }}>
                {showCreate ? "Cancel" : "Create Endorsement"}
              </button>
            )}
          </div>

          {showCreate && (
            <form onSubmit={handleCreateEndorsement} style={{ border: "1px solid #ddd", padding: "1rem", marginBottom: "1rem", borderRadius: 4 }}>
              <h3 style={{ marginTop: 0 }}>New Endorsement</h3>
              <div style={{ marginBottom: "0.75rem" }}>
                <label style={{ display: "block", marginBottom: 2, fontSize: "0.85rem" }}>Type</label>
                <select
                  value={endForm.endorsement_type}
                  onChange={(e) => setEndForm({ ...endForm, endorsement_type: e.target.value })}
                  style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }}
                >
                  <option value="COVERAGE_LIMIT_CHANGE">Coverage Limit Change</option>
                  <option value="ADDRESS_CORRECTION">Address Correction</option>
                </select>
              </div>
              <div style={{ marginBottom: "0.75rem" }}>
                <label style={{ display: "block", marginBottom: 2, fontSize: "0.85rem" }}>Effective Date</label>
                <input
                  type="date"
                  value={endForm.effective_date}
                  onChange={(e) => setEndForm({ ...endForm, effective_date: e.target.value })}
                  required
                  style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }}
                />
              </div>
              <div style={{ marginBottom: "0.75rem" }}>
                <label style={{ display: "block", marginBottom: 2, fontSize: "0.85rem" }}>Annual Premium Delta (cents)</label>
                <input
                  type="number"
                  value={endForm.annual_premium_delta_cents}
                  onChange={(e) => setEndForm({ ...endForm, annual_premium_delta_cents: e.target.value })}
                  required
                  style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }}
                />
                <p style={{ fontSize: "0.75rem", color: "#666", margin: "2px 0 0 0" }}>
                  Positive = increase, negative = decrease. For address corrections, this is ignored.
                </p>
              </div>
              <div style={{ marginBottom: "0.75rem" }}>
                <label style={{ display: "block", marginBottom: 2, fontSize: "0.85rem" }}>Description</label>
                <input
                  type="text"
                  value={endForm.description}
                  onChange={(e) => setEndForm({ ...endForm, description: e.target.value })}
                  required
                  style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }}
                />
              </div>
              {createError && <p style={{ color: "red", fontSize: "0.85rem" }}>{createError}</p>}
              <button type="submit" disabled={creating} style={{ padding: "0.5rem 1rem" }}>
                {creating ? "Creating..." : "Create Endorsement"}
              </button>
            </form>
          )}

          {lastCharges && (
            <div style={{ border: "1px solid #5cb85c", padding: "1rem", marginBottom: "1rem", borderRadius: 4, backgroundColor: "#f0fff0" }}>
              <h4 style={{ marginTop: 0 }}>Endorsement Created — Charge Breakdown</h4>
              <p>Pro-Rated Premium: {formatCents(lastCharges.premium_change_cents as number)}</p>
              <p>Tax: {formatCents(lastCharges.total_tax_cents as number)}</p>
              <p>Fees: {formatCents(lastCharges.total_fees_cents as number)}</p>
              <p><strong>Total: {formatCents(lastCharges.total_cents as number)}</strong></p>
              <button onClick={() => setLastCharges(null)} style={{ fontSize: "0.8rem" }}>Dismiss</button>
            </div>
          )}

          {endorsements.length === 0 && <p style={{ color: "#666" }}>No endorsements yet.</p>}
          {endorsements.length > 0 && (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                  <th style={{ padding: "0.5rem" }}>Number</th>
                  <th style={{ padding: "0.5rem" }}>Type</th>
                  <th style={{ padding: "0.5rem" }}>Status</th>
                  <th style={{ padding: "0.5rem" }}>Effective</th>
                  <th style={{ padding: "0.5rem" }}>Premium Change</th>
                  <th style={{ padding: "0.5rem" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {endorsements.map((e) => (
                  <tr key={e.id} style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>
                      {e.endorsement_number}
                      {e.correction_of && (
                        <span style={{ fontSize: "0.7rem", color: "#666", display: "block" }}>
                          (correction)
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{e.endorsement_type}</td>
                    <td style={{ padding: "0.5rem" }}>{statusBadge(e.status)}</td>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{e.effective_date}</td>
                    <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{formatCents(e.premium_change_cents)}</td>
                    <td style={{ padding: "0.5rem" }}>
                      <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                        {(e.status === "APPROVED" || e.status === "PENDING_PAYMENT") && (
                          <button
                            onClick={() => handleApply(e.id)}
                            disabled={actionLoading === e.id}
                            style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem", backgroundColor: "#5cb85c", color: "#fff", border: "none", borderRadius: 3, cursor: "pointer" }}
                          >
                            {actionLoading === e.id ? "..." : "Apply"}
                          </button>
                        )}
                        {e.status === "APPLIED" && (
                          <button
                            onClick={() => { setShowCorrect(e.id); setCorrectDate(""); setCorrectError(""); }}
                            style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem", backgroundColor: "#f0ad4e", color: "#fff", border: "none", borderRadius: 3, cursor: "pointer" }}
                          >
                            Correct
                          </button>
                        )}
                      </div>

                      {showCorrect === e.id && (
                        <div style={{ marginTop: "0.5rem", padding: "0.5rem", border: "1px solid #f0ad4e", borderRadius: 4, fontSize: "0.85rem" }}>
                          <label style={{ display: "block", marginBottom: 2 }}>Corrected Effective Date:</label>
                          <input
                            type="date"
                            value={correctDate}
                            onChange={(ev) => setCorrectDate(ev.target.value)}
                            style={{ padding: "0.3rem", marginRight: "0.5rem" }}
                          />
                          <button
                            onClick={() => handleCorrect(e.id)}
                            disabled={actionLoading === e.id || !correctDate}
                            style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem" }}
                          >
                            {actionLoading === e.id ? "..." : "Submit Correction"}
                          </button>
                          <button
                            onClick={() => setShowCorrect(null)}
                            style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem", marginLeft: "0.25rem" }}
                          >
                            Cancel
                          </button>
                          {correctError && <p style={{ color: "red", margin: "0.25rem 0 0 0" }}>{correctError}</p>}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>
    </>
  );
}
