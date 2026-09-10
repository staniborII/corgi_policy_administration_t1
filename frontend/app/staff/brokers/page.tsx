"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useRealtimeRefresh } from "@/lib/useRealtimeRefresh";
import { api, type Broker, ApiError } from "@/lib/api";
import Nav from "@/components/Nav";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardHeader, CardContent, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";

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
    commission_rate_percent: "15",
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

  useRealtimeRefresh("broker.", loadBrokers);

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
      const { commission_rate_percent, ...rest } = form;
      await api.createBroker({
        ...rest,
        commission_rate_bps: Math.round(parseFloat(commission_rate_percent) * 100),
      });
      setShowCreate(false);
      setForm({ company_name: "", commission_rate_percent: "15", contact_email: "", contact_first_name: "", contact_last_name: "" });
      await loadBrokers();
    } catch (err) {
      setCreateError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to create broker.");
    } finally {
      setCreating(false);
    }
  }

  async function handleInitiateKyb(brokerId: number) {
    // Open blank window synchronously so browsers don't block it as a popup
    const onboardingWindow = window.open("about:blank", "_blank");
    try {
      const kyb = await api.initiateKyb(brokerId);
      if (kyb.onboarding_url) {
        if (onboardingWindow) {
          onboardingWindow.location.href = kyb.onboarding_url;
        } else {
          window.location.href = kyb.onboarding_url;
        }
      } else {
        onboardingWindow?.close();
        alert(`KYB initiated (${kyb.provider}). Reference: ${kyb.provider_reference}`);
      }
      await loadBrokers();
      if (selectedBroker?.id === brokerId) {
        setSelectedBroker(await api.getBroker(brokerId));
      }
    } catch (err) {
      onboardingWindow?.close();
      const msg = err instanceof ApiError ? (err.body?.detail || JSON.stringify(err.body)) : "Failed to initiate KYB.";
      alert(msg);
    }
  }

  function getProviderLabel(provider: string) {
    switch (provider) {
      case "STRIPE_CONNECT": return "Stripe Connect";
      case "PERSONA": return "Persona";
      case "SIMULATED": return "Simulated";
      default: return provider;
    }
  }

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-5xl p-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Brokers</h1>
          <Button
            variant={showCreate ? "outline" : "default"}
            onClick={() => setShowCreate(!showCreate)}
          >
            {showCreate ? "Cancel" : "Create Broker"}
          </Button>
        </div>

        {showCreate && (
          <Card className="mt-4 mb-6">
            <CardHeader>
              <CardTitle>New Broker</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreate} className="space-y-4">
                {[
                  { label: "Company Name", key: "company_name" },
                  { label: "Contact Email", key: "contact_email" },
                  { label: "Contact First Name", key: "contact_first_name" },
                  { label: "Contact Last Name", key: "contact_last_name" },
                ].map(({ label, key }) => (
                  <div key={key} className="space-y-1">
                    <Label htmlFor={key}>{label}</Label>
                    <Input
                      id={key}
                      value={form[key as keyof typeof form]}
                      onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                      required
                    />
                  </div>
                ))}
                <div className="space-y-1">
                  <Label htmlFor="commission_rate_percent">Commission Rate (%)</Label>
                  <div className="relative">
                    <Input
                      id="commission_rate_percent"
                      type="number"
                      step="0.01"
                      min="0"
                      max="100"
                      value={form.commission_rate_percent}
                      onChange={(e) => setForm({ ...form, commission_rate_percent: e.target.value })}
                      required
                      className="pr-8"
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">%</span>
                  </div>
                  <p className="text-xs text-muted-foreground">e.g. 15 = 15% commission on premium</p>
                </div>
                {createError && (
                  <Alert variant="destructive">
                    <AlertDescription>{createError}</AlertDescription>
                  </Alert>
                )}
                <Button type="submit" disabled={creating}>
                  {creating ? "Creating..." : "Create"}
                </Button>
              </form>
            </CardContent>
          </Card>
        )}

        {error && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {loadingData && <p className="mt-4 text-muted-foreground">Loading...</p>}

        {!loadingData && brokers.length === 0 && (
          <p className="mt-4 text-muted-foreground">No brokers found.</p>
        )}

        {brokers.length > 0 && (
          <Table className="mt-4">
            <TableHeader>
              <TableRow>
                <TableHead>Company</TableHead>
                <TableHead>Commission</TableHead>
                <TableHead>KYB Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {brokers.map((b) => (
                <TableRow key={b.id} className="cursor-pointer">
                  <TableCell onClick={() => setSelectedBroker(b)} className="font-medium">
                    {b.company_name}
                  </TableCell>
                  <TableCell>{(b.commission_rate_bps / 100).toFixed(2)}%</TableCell>
                  <TableCell>
                    <StatusBadge status={b.status} />
                  </TableCell>
                  <TableCell>
                    {b.status === "PENDING_KYB" && (
                      <Button variant="outline" size="sm" onClick={() => handleInitiateKyb(b.id)}>
                        Initiate KYB
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {selectedBroker && (
          <Card className="mt-8">
            <CardHeader>
              <CardTitle>{selectedBroker.company_name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="flex items-center gap-2">
                Status: <StatusBadge status={selectedBroker.status} />
              </p>
              <p>Commission: {(selectedBroker.commission_rate_bps / 100).toFixed(2)}%</p>
              {selectedBroker.stripe_connect_account_id && (
                <p className="text-sm text-muted-foreground">
                  Stripe Connect: {selectedBroker.stripe_connect_account_id}
                </p>
              )}
              {selectedBroker.latest_kyb && (
                <div className="mt-2 space-y-1">
                  <h3 className="text-lg font-semibold">Latest KYB Verification</h3>
                  <div className="flex items-center gap-2">
                    <span>Provider:</span>
                    <Badge variant="outline">{getProviderLabel(selectedBroker.latest_kyb.provider)}</Badge>
                  </div>
                  <p>Reference: {selectedBroker.latest_kyb.provider_reference}</p>
                  <p>Status: {selectedBroker.latest_kyb.status}</p>
                  {selectedBroker.latest_kyb.provider === "SIMULATED" && (
                    <p className="font-bold text-amber-500">
                      SIMULATED — No real provider configured
                    </p>
                  )}
                  {selectedBroker.latest_kyb.provider_reference.startsWith("SIMULATED") && (
                    <p className="font-bold text-amber-500">
                      SIMULATED — Provider credentials not configured
                    </p>
                  )}
                  {selectedBroker.latest_kyb.onboarding_url && selectedBroker.latest_kyb.status === "PENDING" && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-2"
                      onClick={() => window.open(selectedBroker.latest_kyb!.onboarding_url, "_blank", "noopener")}
                    >
                      Open Onboarding Link
                    </Button>
                  )}
                </div>
              )}
              <Button variant="outline" className="mt-2" onClick={() => setSelectedBroker(null)}>
                Close
              </Button>
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}
