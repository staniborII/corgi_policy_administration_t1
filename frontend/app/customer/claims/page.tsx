"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type ClaimRecord, type Policy } from "@/lib/api";
import Nav from "@/components/Nav";

function formatCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function statusBadge(s: string) {
  const colors: Record<string, string> = {
    OPEN: "#0275d8",
    UNDER_REVIEW: "#f0ad4e",
    RESERVED: "#5bc0de",
    PAYMENT_PENDING: "#f0ad4e",
    PARTIALLY_PAID: "#0275d8",
    PAID: "#5cb85c",
    CLOSED: "#999",
  };
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 4, fontSize: "0.8rem",
      backgroundColor: colors[s] || "#999", color: "#fff",
    }}>
      {s.replace(/_/g, " ")}
    </span>
  );
}

function ClaimsContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const policyId = searchParams.get("policy_id");

  const [claims, setClaims] = useState<ClaimRecord[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const fetched = useRef(false);

  const [formPolicyId, setFormPolicyId] = useState(policyId || "");
  const [dateOfLoss, setDateOfLoss] = useState("");
  const [description, setDescription] = useState("");
  const [estimatedAmount, setEstimatedAmount] = useState("");

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

    Promise.all([
      api.listClaims(policyId ? Number(policyId) : undefined),
      api.listPolicies(),
    ])
      .then(([claimsData, policiesData]) => {
        if (!cancelled) {
          setClaims(claimsData);
          setPolicies(policiesData);
        }
      })
      .catch(() => { if (!cancelled) setError("Failed to load data."); })
      .finally(() => { if (!cancelled) setLoadingData(false); });

    return () => { cancelled = true; };
  }, [loading, user, policyId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const claim = await api.submitClaim({
        policy_id: Number(formPolicyId),
        date_of_loss: dateOfLoss,
        description,
        estimated_amount_cents: estimatedAmount ? Math.round(parseFloat(estimatedAmount) * 100) : undefined,
      });
      setClaims((prev) => [claim, ...prev]);
      setShowForm(false);
      setDateOfLoss("");
      setDescription("");
      setEstimatedAmount("");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to submit claim.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 900, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h1>My Claims</h1>
          <button
            onClick={() => setShowForm(!showForm)}
            style={{
              padding: "0.5rem 1rem", backgroundColor: "#0275d8",
              color: "#fff", border: "none", borderRadius: 4, cursor: "pointer",
            }}
          >
            {showForm ? "Cancel" : "Submit Claim"}
          </button>
        </div>

        {error && <p style={{ color: "red" }}>{error}</p>}

        {showForm && (
          <form onSubmit={handleSubmit} style={{
            border: "1px solid #ddd", borderRadius: 4, padding: "1rem", marginBottom: "1rem",
          }}>
            <h3>Submit a New Claim</h3>
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ display: "block", marginBottom: "0.25rem", fontWeight: "bold" }}>Policy</label>
              <select
                value={formPolicyId}
                onChange={(e) => setFormPolicyId(e.target.value)}
                required
                style={{ width: "100%", padding: "0.5rem" }}
              >
                <option value="">Select a policy...</option>
                {policies.filter((p) => ["ACTIVE", "CANCELLED", "EXPIRED"].includes(p.status)).map((p) => (
                  <option key={p.id} value={p.id}>{p.policy_number} ({p.status})</option>
                ))}
              </select>
            </div>
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ display: "block", marginBottom: "0.25rem", fontWeight: "bold" }}>Date of Loss</label>
              <input
                type="date"
                value={dateOfLoss}
                onChange={(e) => setDateOfLoss(e.target.value)}
                required
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ display: "block", marginBottom: "0.25rem", fontWeight: "bold" }}>Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
                rows={3}
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ display: "block", marginBottom: "0.25rem", fontWeight: "bold" }}>Estimated Amount ($)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={estimatedAmount}
                onChange={(e) => setEstimatedAmount(e.target.value)}
                placeholder="Optional"
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              style={{
                padding: "0.5rem 1rem", backgroundColor: "#5cb85c",
                color: "#fff", border: "none", borderRadius: 4, cursor: "pointer",
              }}
            >
              {submitting ? "Submitting..." : "Submit Claim"}
            </button>
          </form>
        )}

        {loadingData && <p>Loading...</p>}
        {!loadingData && claims.length === 0 && !showForm && (
          <p style={{ color: "#666", textAlign: "center", padding: "2rem" }}>No claims found.</p>
        )}

        {claims.map((c) => (
          <div key={c.id} style={{
            border: "1px solid #ddd", borderRadius: 4, padding: "1rem", marginBottom: "0.75rem",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0 }}>{c.claim_number}</h3>
              {statusBadge(c.status)}
            </div>
            <div style={{ marginTop: "0.5rem", fontSize: "0.9rem", color: "#555" }}>
              <div>Date of Loss: {c.date_of_loss}</div>
              <div>Description: {c.description}</div>
              {c.estimated_amount_cents && (
                <div>Estimated Amount: {formatCents(c.estimated_amount_cents)}</div>
              )}
              <div>Reported: {new Date(c.reported_at).toLocaleDateString()}</div>
            </div>
          </div>
        ))}
      </main>
    </>
  );
}

export default function CustomerClaimsPage() {
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <ClaimsContent />
    </Suspense>
  );
}
