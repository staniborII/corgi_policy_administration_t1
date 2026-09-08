"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type Broker, ApiError } from "@/lib/api";
import Nav from "@/components/Nav";

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    PENDING_KYB: "#f0ad4e",
    APPROVED: "#5cb85c",
    REJECTED: "#d9534f",
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

export default function BrokersPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [selectedBroker, setSelectedBroker] = useState<Broker | null>(null);

  const [form, setForm] = useState({
    company_name: "",
    commission_rate_bps: "1500",
    contact_email: "",
    contact_first_name: "",
    contact_last_name: "",
  });
  const [createError, setCreateError] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "STAFF") {
      router.replace("/login");
      return;
    }
    loadBrokers();
  }, [user, loading, router]);

  async function loadBrokers() {
    setLoadingData(true);
    try {
      setBrokers(await api.listBrokers());
    } catch {
      setError("Failed to load brokers.");
    } finally {
      setLoadingData(false);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreateError("");
    setCreating(true);
    try {
      await api.createBroker({
        ...form,
        commission_rate_bps: parseInt(form.commission_rate_bps, 10),
      });
      setShowCreate(false);
      setForm({ company_name: "", commission_rate_bps: "1500", contact_email: "", contact_first_name: "", contact_last_name: "" });
      await loadBrokers();
    } catch (err) {
      setCreateError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to create broker.");
    } finally {
      setCreating(false);
    }
  }

  async function handleInitiateKyb(brokerId: number) {
    try {
      const result = await api.initiateKyb(brokerId);
      alert(`KYB initiated. Inquiry ID: ${result.inquiry_id}`);
      await loadBrokers();
      if (selectedBroker?.id === brokerId) {
        setSelectedBroker(await api.getBroker(brokerId));
      }
    } catch (err) {
      alert(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to initiate KYB.");
    }
  }

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main style={{ padding: "1.5rem", fontFamily: "system-ui, sans-serif", maxWidth: 900, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h1>Brokers</h1>
          <button onClick={() => setShowCreate(!showCreate)} style={{ padding: "0.5rem 1rem" }}>
            {showCreate ? "Cancel" : "Create Broker"}
          </button>
        </div>

        {showCreate && (
          <form onSubmit={handleCreate} style={{ border: "1px solid #ddd", padding: "1rem", marginBottom: "1.5rem", borderRadius: 4 }}>
            <h3>New Broker</h3>
            {[
              { label: "Company Name", key: "company_name" },
              { label: "Commission Rate (bps)", key: "commission_rate_bps" },
              { label: "Contact Email", key: "contact_email" },
              { label: "Contact First Name", key: "contact_first_name" },
              { label: "Contact Last Name", key: "contact_last_name" },
            ].map(({ label, key }) => (
              <div key={key} style={{ marginBottom: "0.75rem" }}>
                <label style={{ display: "block", marginBottom: 2, fontSize: "0.85rem" }}>{label}</label>
                <input
                  value={form[key as keyof typeof form]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  required
                  style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }}
                />
              </div>
            ))}
            {createError && <p style={{ color: "red", fontSize: "0.85rem" }}>{createError}</p>}
            <button type="submit" disabled={creating} style={{ padding: "0.5rem 1rem" }}>
              {creating ? "Creating..." : "Create"}
            </button>
          </form>
        )}

        {error && <p style={{ color: "red" }}>{error}</p>}
        {loadingData && <p>Loading...</p>}

        {!loadingData && brokers.length === 0 && <p>No brokers found.</p>}

        {brokers.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                <th style={{ padding: "0.5rem" }}>Company</th>
                <th style={{ padding: "0.5rem" }}>Commission</th>
                <th style={{ padding: "0.5rem" }}>KYB Status</th>
                <th style={{ padding: "0.5rem" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {brokers.map((b) => (
                <tr key={b.id} style={{ borderBottom: "1px solid #eee", cursor: "pointer" }}>
                  <td style={{ padding: "0.5rem" }} onClick={() => setSelectedBroker(b)}>{b.company_name}</td>
                  <td style={{ padding: "0.5rem" }}>{(b.commission_rate_bps / 100).toFixed(2)}%</td>
                  <td style={{ padding: "0.5rem" }}>{statusBadge(b.status)}</td>
                  <td style={{ padding: "0.5rem" }}>
                    {b.status === "PENDING_KYB" && (
                      <button onClick={() => handleInitiateKyb(b.id)} style={{ fontSize: "0.85rem" }}>
                        Initiate KYB
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {selectedBroker && (
          <div style={{ marginTop: "2rem", border: "1px solid #ddd", padding: "1rem", borderRadius: 4 }}>
            <h2>{selectedBroker.company_name}</h2>
            <p>Status: {statusBadge(selectedBroker.status)}</p>
            <p>Commission: {(selectedBroker.commission_rate_bps / 100).toFixed(2)}%</p>
            {selectedBroker.latest_kyb && (
              <div style={{ marginTop: "0.5rem" }}>
                <h3>Latest KYB Verification</h3>
                <p>Inquiry ID: {selectedBroker.latest_kyb.persona_inquiry_id}</p>
                <p>Status: {selectedBroker.latest_kyb.status}</p>
                {selectedBroker.latest_kyb.persona_inquiry_id.startsWith("SIMULATED") && (
                  <p style={{ color: "#f0ad4e", fontWeight: "bold" }}>SIMULATED — No real Persona credentials configured</p>
                )}
              </div>
            )}
            <button onClick={() => setSelectedBroker(null)} style={{ marginTop: "0.5rem" }}>Close</button>
          </div>
        )}
      </main>
    </>
  );
}
