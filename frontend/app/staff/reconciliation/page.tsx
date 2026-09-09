"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  api,
  type ReconciliationRunRecord,
  type ReconciliationBreakRecord,
  type ReconciliationRunDetail,
} from "@/lib/api";
import Nav from "@/components/Nav";

function formatCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function breakTypeBadge(breakType: string) {
  const colors: Record<string, string> = {
    MISSING_IN_LEDGER: "#d9534f",
    MISSING_IN_PROVIDER: "#f0ad4e",
    AMOUNT_MISMATCH: "#d9534f",
    STATUS_MISMATCH: "#e67e22",
    DUPLICATE_MATCH: "#5bc0de",
    STALE_UNRESOLVED: "#999",
  };
  return (
    <span
      style={{
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: "0.75rem",
        backgroundColor: colors[breakType] || "#999",
        color: "#fff",
      }}
    >
      {breakType.replace(/_/g, " ")}
    </span>
  );
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    OPEN: "#d9534f",
    ACKNOWLEDGED: "#f0ad4e",
    RESOLVED: "#5cb85c",
    RUNNING: "#0275d8",
    COMPLETED: "#5cb85c",
    FAILED: "#d9534f",
  };
  return (
    <span
      style={{
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: "0.75rem",
        backgroundColor: colors[status] || "#999",
        color: "#fff",
      }}
    >
      {status}
    </span>
  );
}

function formatAge(seconds: number | null) {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

export default function ReconciliationPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [runs, setRuns] = useState<ReconciliationRunRecord[]>([]);
  const [breaks, setBreaks] = useState<ReconciliationBreakRecord[]>([]);
  const [selectedRun, setSelectedRun] = useState<ReconciliationRunDetail | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState("");
  const [breakFilter, setBreakFilter] = useState("OPEN");

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
      const [r, b] = await Promise.all([
        api.listReconciliationRuns(),
        api.listReconciliationBreaks(breakFilter),
      ]);
      setRuns(r);
      setBreaks(b);
    } catch {
      setError("Failed to load reconciliation data.");
    } finally {
      setLoadingData(false);
    }
  }

  async function handleTrigger() {
    setTriggering(true);
    setError("");
    try {
      const run = await api.triggerReconciliation();
      const detail = await api.getReconciliationRun(run.id);
      setSelectedRun(detail);
      await loadData();
    } catch {
      setError("Reconciliation run failed.");
    } finally {
      setTriggering(false);
    }
  }

  async function handleViewRun(id: number) {
    try {
      const detail = await api.getReconciliationRun(id);
      setSelectedRun(detail);
    } catch {
      setError("Failed to load run detail.");
    }
  }

  async function handleResolve(breakId: number) {
    const notes = prompt("Resolution notes (optional):");
    if (notes === null) return;
    try {
      await api.resolveBreak(breakId, notes);
      await loadData();
      if (selectedRun) {
        const detail = await api.getReconciliationRun(selectedRun.id);
        setSelectedRun(detail);
      }
    } catch {
      setError("Failed to resolve break.");
    }
  }

  async function handleFilterChange(filter: string) {
    setBreakFilter(filter);
    try {
      const b = await api.listReconciliationBreaks(filter);
      setBreaks(b);
    } catch {
      setError("Failed to filter breaks.");
    }
  }

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 1100, margin: "0 auto" }}>
        <h1>Reconciliation</h1>

        {error && <p style={{ color: "red" }}>{error}</p>}

        {/* Trigger */}
        <div style={{ marginBottom: "1.5rem" }}>
          <button
            onClick={handleTrigger}
            disabled={triggering}
            style={{ padding: "0.5rem 1.5rem", backgroundColor: "#0275d8", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: "1rem" }}
          >
            {triggering ? "Running..." : "Run Reconciliation"}
          </button>
        </div>

        {/* Recent Runs */}
        <h2>Recent Runs</h2>
        {loadingData ? (
          <p>Loading...</p>
        ) : runs.length === 0 ? (
          <p style={{ color: "#666" }}>No reconciliation runs yet.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: "1.5rem" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                <th style={{ padding: "0.5rem" }}>ID</th>
                <th style={{ padding: "0.5rem" }}>Date</th>
                <th style={{ padding: "0.5rem" }}>Status</th>
                <th style={{ padding: "0.5rem" }}>Breaks</th>
                <th style={{ padding: "0.5rem" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{r.id}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{r.run_date}</td>
                  <td style={{ padding: "0.5rem" }}>{statusBadge(r.status)}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{r.breaks_count}</td>
                  <td style={{ padding: "0.5rem" }}>
                    <button onClick={() => handleViewRun(r.id)} style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem", cursor: "pointer" }}>
                      Detail
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Selected Run Detail */}
        {selectedRun && (
          <div style={{ padding: "1rem", border: "1px solid #0275d8", borderRadius: 4, backgroundColor: "#f0f7ff", marginBottom: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ marginTop: 0 }}>Run #{selectedRun.id} — {selectedRun.run_date}</h3>
              <button onClick={() => setSelectedRun(null)} style={{ cursor: "pointer" }}>Close</button>
            </div>
            <p>{statusBadge(selectedRun.status)} | Breaks: {selectedRun.breaks.length}</p>
            {selectedRun.breaks.length > 0 && (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>
                    <th style={{ padding: "0.25rem" }}>Type</th>
                    <th style={{ padding: "0.25rem" }}>Description</th>
                    <th style={{ padding: "0.25rem" }}>Expected</th>
                    <th style={{ padding: "0.25rem" }}>Actual</th>
                    <th style={{ padding: "0.25rem" }}>Status</th>
                    <th style={{ padding: "0.25rem" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedRun.breaks.map((b) => (
                    <tr key={b.id} style={{ borderBottom: "1px solid #eee" }}>
                      <td style={{ padding: "0.25rem" }}>{breakTypeBadge(b.break_type)}</td>
                      <td style={{ padding: "0.25rem" }}>{b.description}</td>
                      <td style={{ padding: "0.25rem" }}>{b.expected_amount_cents !== null ? formatCents(b.expected_amount_cents) : "—"}</td>
                      <td style={{ padding: "0.25rem" }}>{b.actual_amount_cents !== null ? formatCents(b.actual_amount_cents) : "—"}</td>
                      <td style={{ padding: "0.25rem" }}>{statusBadge(b.status)}</td>
                      <td style={{ padding: "0.25rem" }}>
                        {b.status !== "RESOLVED" && (
                          <button onClick={() => handleResolve(b.id)} style={{ padding: "0.15rem 0.4rem", fontSize: "0.75rem", cursor: "pointer" }}>
                            Resolve
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* All Breaks */}
        <h2>Breaks</h2>
        <div style={{ marginBottom: "0.5rem", display: "flex", gap: "0.5rem" }}>
          {["OPEN", "ACKNOWLEDGED", "RESOLVED", ""].map((f) => (
            <button
              key={f}
              onClick={() => handleFilterChange(f)}
              style={{
                padding: "0.3rem 0.8rem",
                fontSize: "0.8rem",
                backgroundColor: breakFilter === f ? "#0275d8" : "#eee",
                color: breakFilter === f ? "#fff" : "#333",
                border: "none",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              {f || "ALL"}
            </button>
          ))}
        </div>
        {breaks.length === 0 ? (
          <p style={{ color: "#666" }}>No breaks found.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                <th style={{ padding: "0.5rem" }}>Type</th>
                <th style={{ padding: "0.5rem" }}>Description</th>
                <th style={{ padding: "0.5rem" }}>Expected</th>
                <th style={{ padding: "0.5rem" }}>Actual</th>
                <th style={{ padding: "0.5rem" }}>Age</th>
                <th style={{ padding: "0.5rem" }}>Status</th>
                <th style={{ padding: "0.5rem" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {breaks.map((b) => (
                <tr key={b.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "0.5rem" }}>{breakTypeBadge(b.break_type)}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{b.description}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{b.expected_amount_cents !== null ? formatCents(b.expected_amount_cents) : "—"}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{b.actual_amount_cents !== null ? formatCents(b.actual_amount_cents) : "—"}</td>
                  <td style={{ padding: "0.5rem", fontSize: "0.85rem" }}>{formatAge(b.age_seconds)}</td>
                  <td style={{ padding: "0.5rem" }}>{statusBadge(b.status)}</td>
                  <td style={{ padding: "0.5rem" }}>
                    {b.status !== "RESOLVED" && (
                      <button onClick={() => handleResolve(b.id)} style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem", cursor: "pointer" }}>
                        Resolve
                      </button>
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
