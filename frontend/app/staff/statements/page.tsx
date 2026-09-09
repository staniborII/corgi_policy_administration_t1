"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type BrokerStatementRecord, type Broker, ApiError } from "@/lib/api";
import Nav from "@/components/Nav";

function formatCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

export default function BrokerStatementsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [statements, setStatements] = useState<BrokerStatementRecord[]>([]);
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");

  const [selectedBrokerId, setSelectedBrokerId] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [generating, setGenerating] = useState(false);

  const [detail, setDetail] = useState<BrokerStatementRecord | null>(null);

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
      const [s, b] = await Promise.all([
        api.listBrokerStatements(),
        api.listBrokers(),
      ]);
      setStatements(s);
      setBrokers(b);
    } catch {
      setError("Failed to load statements.");
    } finally {
      setLoadingData(false);
    }
  }

  async function handleGenerate() {
    if (!selectedBrokerId || !periodStart || !periodEnd) {
      setError("Select a broker and period dates.");
      return;
    }
    setGenerating(true);
    setError("");
    try {
      await api.generateBrokerStatement({
        broker_id: parseInt(selectedBrokerId, 10),
        period_start: periodStart,
        period_end: periodEnd,
      });
      await loadData();
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to generate statement.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleViewDetail(id: number) {
    try {
      const s = await api.getBrokerStatement(id);
      setDetail(s);
    } catch {
      setError("Failed to load statement detail.");
    }
  }

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 1000, margin: "0 auto" }}>
        <h1>Broker Statements</h1>

        {error && <p style={{ color: "red" }}>{error}</p>}

        {/* Generate Form */}
        <div style={{ padding: "1rem", border: "1px solid #ddd", borderRadius: 4, marginBottom: "1.5rem" }}>
          <h3 style={{ marginTop: 0 }}>Generate Statement</h3>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <select
              value={selectedBrokerId}
              onChange={(e) => setSelectedBrokerId(e.target.value)}
              style={{ padding: "0.4rem" }}
            >
              <option value="">Select Broker</option>
              {brokers.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.company_name}
                </option>
              ))}
            </select>
            <label style={{ fontSize: "0.85rem" }}>From:</label>
            <input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} style={{ padding: "0.4rem" }} />
            <label style={{ fontSize: "0.85rem" }}>To:</label>
            <input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} style={{ padding: "0.4rem" }} />
            <button
              onClick={handleGenerate}
              disabled={generating}
              style={{ padding: "0.5rem 1rem", backgroundColor: "#0275d8", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
            >
              {generating ? "Generating..." : "Generate"}
            </button>
          </div>
        </div>

        {/* Statements List */}
        {loadingData ? (
          <p>Loading...</p>
        ) : statements.length === 0 ? (
          <p style={{ color: "#666" }}>No statements generated yet.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                <th style={{ padding: "0.5rem" }}>ID</th>
                <th style={{ padding: "0.5rem" }}>Broker</th>
                <th style={{ padding: "0.5rem" }}>Period</th>
                <th style={{ padding: "0.5rem" }}>Premium</th>
                <th style={{ padding: "0.5rem" }}>Commission</th>
                <th style={{ padding: "0.5rem" }}>Clawback</th>
                <th style={{ padding: "0.5rem" }}>Net Due</th>
                <th style={{ padding: "0.5rem" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {statements.map((s) => (
                <tr key={s.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{s.id}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{s.broker_name}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{s.period_start} &ndash; {s.period_end}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{formatCents(s.total_premium_cents)}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{formatCents(s.total_commission_cents)}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{formatCents(s.total_clawback_cents)}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem", fontWeight: "bold" }}>{formatCents(s.net_due_cents)}</td>
                  <td style={{ padding: "0.5rem" }}>
                    <button
                      onClick={() => handleViewDetail(s.id)}
                      style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem", cursor: "pointer" }}
                    >
                      Detail
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Detail Modal */}
        {detail && (
          <div style={{ marginTop: "1.5rem", padding: "1rem", border: "1px solid #0275d8", borderRadius: 4, backgroundColor: "#f0f7ff" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ marginTop: 0 }}>Statement #{detail.id} — {detail.broker_name}</h3>
              <button onClick={() => setDetail(null)} style={{ cursor: "pointer" }}>Close</button>
            </div>
            <p>Period: {detail.period_start} &ndash; {detail.period_end}</p>
            <p>Premium: {formatCents(detail.total_premium_cents)} | Commission: {formatCents(detail.total_commission_cents)} | Clawback: {formatCents(detail.total_clawback_cents)} | <strong>Net Due: {formatCents(detail.net_due_cents)}</strong></p>

            {Array.isArray(detail.statement_data.payments) && detail.statement_data.payments.length > 0 && (
              <>
                <h4>Payments</h4>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>
                      <th style={{ padding: "0.25rem" }}>Policy</th>
                      <th style={{ padding: "0.25rem" }}>Premium</th>
                      <th style={{ padding: "0.25rem" }}>Total</th>
                      <th style={{ padding: "0.25rem" }}>Commission</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(detail.statement_data.payments as Array<Record<string, unknown>>).map((p, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                        <td style={{ padding: "0.25rem" }}>{p.policy_number as string}</td>
                        <td style={{ padding: "0.25rem" }}>{formatCents(p.premium_cents as number)}</td>
                        <td style={{ padding: "0.25rem" }}>{formatCents(p.total_cents as number)}</td>
                        <td style={{ padding: "0.25rem" }}>{formatCents(p.commission_cents as number)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}

            {Array.isArray(detail.statement_data.refunds) && detail.statement_data.refunds.length > 0 && (
              <>
                <h4>Refunds</h4>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>
                      <th style={{ padding: "0.25rem" }}>Policy</th>
                      <th style={{ padding: "0.25rem" }}>Refund</th>
                      <th style={{ padding: "0.25rem" }}>Clawback</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(detail.statement_data.refunds as Array<Record<string, unknown>>).map((r, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                        <td style={{ padding: "0.25rem" }}>{r.policy_number as string}</td>
                        <td style={{ padding: "0.25rem" }}>{formatCents(r.refund_cents as number)}</td>
                        <td style={{ padding: "0.25rem" }}>{formatCents(r.clawback_cents as number)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}
      </main>
    </>
  );
}
