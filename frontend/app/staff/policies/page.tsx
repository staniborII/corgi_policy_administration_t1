"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type Policy, type Broker, ApiError } from "@/lib/api";
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

export default function StaffPoliciesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const [jurisdictions, setJurisdictions] = useState<string[]>([]);
  const [form, setForm] = useState({
    customer_id: "",
    broker_id: "",
    effective_date: "",
    premium_amount_cents: "",
    coverage_territory: "",
  });
  const [createError, setCreateError] = useState("");
  const [creating, setCreating] = useState(false);
  const [lastCharges, setLastCharges] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "STAFF") {
      router.replace("/login");
      return;
    }
    loadData();
  }, [user, loading, router]);

  async function loadData() {
    setLoadingData(true);
    try {
      const [p, b, j] = await Promise.all([api.listPolicies(), api.listBrokers(), api.listJurisdictions()]);
      setPolicies(p);
      setBrokers(b);
      setJurisdictions(j);
    } catch {
      setError("Failed to load data.");
    } finally {
      setLoadingData(false);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreateError("");
    setCreating(true);
    setLastCharges(null);
    try {
      const result = await api.createPolicy({
        customer_id: parseInt(form.customer_id, 10),
        broker_id: parseInt(form.broker_id, 10),
        effective_date: form.effective_date,
        premium_amount_cents: parseInt(form.premium_amount_cents, 10),
        coverage_territory: form.coverage_territory,
      });
      setLastCharges(result.charges);
      setShowCreate(false);
      await loadData();
    } catch (err) {
      setCreateError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to create policy.");
    } finally {
      setCreating(false);
    }
  }

  if (loading || !user) return null;

  const approvedBrokers = brokers.filter((b) => b.status === "APPROVED");

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 900, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h1>Policies</h1>
          <button onClick={() => setShowCreate(!showCreate)} style={{ padding: "0.5rem 1rem" }}>
            {showCreate ? "Cancel" : "Create Policy"}
          </button>
        </div>

        {showCreate && (
          <form onSubmit={handleCreate} style={{ border: "1px solid #ddd", padding: "1rem", marginBottom: "1.5rem", borderRadius: 4 }}>
            <h3>New Policy</h3>
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ display: "block", marginBottom: 2, fontSize: "0.85rem" }}>Customer ID</label>
              <input
                type="number"
                value={form.customer_id}
                onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
                required
                style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }}
              />
            </div>
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ display: "block", marginBottom: 2, fontSize: "0.85rem" }}>Broker</label>
              <select
                value={form.broker_id}
                onChange={(e) => setForm({ ...form, broker_id: e.target.value })}
                required
                style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }}
              >
                <option value="">Select broker...</option>
                {approvedBrokers.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.company_name} ({(b.commission_rate_bps / 100).toFixed(2)}%)
                  </option>
                ))}
              </select>
              {approvedBrokers.length === 0 && (
                <p style={{ color: "#f0ad4e", fontSize: "0.85rem" }}>No approved brokers available.</p>
              )}
            </div>
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ display: "block", marginBottom: 2, fontSize: "0.85rem" }}>Effective Date</label>
              <input
                type="date"
                value={form.effective_date}
                onChange={(e) => setForm({ ...form, effective_date: e.target.value })}
                required
                style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }}
              />
            </div>
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ display: "block", marginBottom: 2, fontSize: "0.85rem" }}>Premium (cents)</label>
              <input
                type="number"
                value={form.premium_amount_cents}
                onChange={(e) => setForm({ ...form, premium_amount_cents: e.target.value })}
                required
                min="1"
                style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }}
              />
            </div>
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ display: "block", marginBottom: 2, fontSize: "0.85rem" }}>Coverage Territory</label>
              <select
                value={form.coverage_territory}
                onChange={(e) => setForm({ ...form, coverage_territory: e.target.value })}
                required
                style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }}
              >
                <option value="">Select jurisdiction...</option>
                {jurisdictions.map((j) => (
                  <option key={j} value={j}>{j}</option>
                ))}
              </select>
              {jurisdictions.length === 0 && !loadingData && (
                <p style={{ color: "#f0ad4e", fontSize: "0.85rem" }}>No jurisdictions configured. Add tax/fee rules in the admin panel.</p>
              )}
            </div>
            {createError && <p style={{ color: "red", fontSize: "0.85rem" }}>{createError}</p>}
            <button type="submit" disabled={creating} style={{ padding: "0.5rem 1rem" }}>
              {creating ? "Creating..." : "Create"}
            </button>
          </form>
        )}

        {lastCharges && (
          <div style={{ border: "1px solid #5cb85c", padding: "1rem", marginBottom: "1.5rem", borderRadius: 4, backgroundColor: "#f0fff0" }}>
            <h3>Policy Created — Charge Breakdown</h3>
            <p>Premium: {formatCents(lastCharges.premium_cents as number)}</p>
            <p>Total Tax: {formatCents(lastCharges.total_tax_cents as number)}</p>
            <p>Total Fees: {formatCents(lastCharges.total_fees_cents as number)}</p>
            <p><strong>Total: {formatCents(lastCharges.total_cents as number)}</strong></p>
            <button onClick={() => setLastCharges(null)}>Dismiss</button>
          </div>
        )}

        {error && <p style={{ color: "red" }}>{error}</p>}
        {loadingData && <p>Loading...</p>}
        {!loadingData && policies.length === 0 && <p>No policies found.</p>}

        {policies.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                <th style={{ padding: "0.5rem" }}>Policy #</th>
                <th style={{ padding: "0.5rem" }}>Status</th>
                <th style={{ padding: "0.5rem" }}>Effective</th>
                <th style={{ padding: "0.5rem" }}>Expiration</th>
                <th style={{ padding: "0.5rem" }}>Premium</th>
                <th style={{ padding: "0.5rem" }}>Territory</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "0.5rem" }}>{p.policy_number}</td>
                  <td style={{ padding: "0.5rem" }}>{statusBadge(p.status)}</td>
                  <td style={{ padding: "0.5rem" }}>{p.effective_date}</td>
                  <td style={{ padding: "0.5rem" }}>{p.expiration_date}</td>
                  <td style={{ padding: "0.5rem" }}>{formatCents(p.premium_amount_cents)}</td>
                  <td style={{ padding: "0.5rem" }}>{p.coverage_territory}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </>
  );
}
