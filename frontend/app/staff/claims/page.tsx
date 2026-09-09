"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type ClaimRecord } from "@/lib/api";
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

export default function StaffClaimsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [claims, setClaims] = useState<ClaimRecord[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const fetched = useRef(false);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "STAFF") {
      router.replace("/login");
    }
  }, [user, loading, router]);

  useEffect(() => {
    if (loading || !user || fetched.current) return;
    fetched.current = true;
    let cancelled = false;
    api.listClaims()
      .then((data) => { if (!cancelled) setClaims(data); })
      .catch(() => { if (!cancelled) setError("Failed to load claims."); })
      .finally(() => { if (!cancelled) setLoadingData(false); });
    return () => { cancelled = true; };
  }, [loading, user]);

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 1000, margin: "0 auto" }}>
        <h1>Claims Management</h1>

        {error && <p style={{ color: "red" }}>{error}</p>}
        {loadingData && <p>Loading...</p>}
        {!loadingData && claims.length === 0 && (
          <p style={{ color: "#666", textAlign: "center", padding: "2rem" }}>No claims found.</p>
        )}

        {claims.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                <th style={{ padding: "0.5rem" }}>Claim #</th>
                <th style={{ padding: "0.5rem" }}>Status</th>
                <th style={{ padding: "0.5rem" }}>Date of Loss</th>
                <th style={{ padding: "0.5rem" }}>Estimated</th>
                <th style={{ padding: "0.5rem" }}>Reported</th>
                <th style={{ padding: "0.5rem" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {claims.map((c) => (
                <tr key={c.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "0.5rem" }}>{c.claim_number}</td>
                  <td style={{ padding: "0.5rem" }}>{statusBadge(c.status)}</td>
                  <td style={{ padding: "0.5rem" }}>{c.date_of_loss}</td>
                  <td style={{ padding: "0.5rem" }}>
                    {c.estimated_amount_cents ? formatCents(c.estimated_amount_cents) : "—"}
                  </td>
                  <td style={{ padding: "0.5rem" }}>{new Date(c.reported_at).toLocaleDateString()}</td>
                  <td style={{ padding: "0.5rem" }}>
                    <a
                      href={`/staff/claims/detail?id=${c.id}`}
                      style={{ color: "#0275d8", textDecoration: "underline", cursor: "pointer" }}
                    >
                      Manage
                    </a>
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
