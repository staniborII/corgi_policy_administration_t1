"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useRealtimeRefresh } from "@/lib/useRealtimeRefresh";
import { api, type Policy, type Broker, type User, ApiError } from "@/lib/api";
import Nav from "@/components/Nav";
import { formatCents } from "@/lib/format";
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

export default function StaffPoliciesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [customers, setCustomers] = useState<User[]>([]);
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

  useRealtimeRefresh(["policy.", "payment."], loadData);

  async function loadData() {
    setLoadingData(true);
    try {
      const [p, b, j, c] = await Promise.all([api.listPolicies(), api.listBrokers(), api.listJurisdictions(), api.listCustomers()]);
      setPolicies(p);
      setBrokers(b);
      setJurisdictions(j);
      setCustomers(c);
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
        premium_amount_cents: Math.round(parseFloat(form.premium_amount_cents) * 100),
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

  const selectedBrokerId = form.broker_id ? parseInt(form.broker_id, 10) : null;
  const customerIdsWithBroker = selectedBrokerId
    ? new Set(
        policies
          .filter((p) => p.broker === selectedBrokerId && !["CANCELLED", "EXPIRED"].includes(p.status))
          .map((p) => p.customer)
      )
    : new Set<number>();
  const availableCustomers = customers.filter((c) => !customerIdsWithBroker.has(c.id));

  const selectClassName =
    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-5xl p-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Policies</h1>
          <Button
            variant={showCreate ? "outline" : "default"}
            onClick={() => setShowCreate(!showCreate)}
          >
            {showCreate ? "Cancel" : "Create Policy"}
          </Button>
        </div>

        {showCreate && (
          <Card className="mt-4 mb-6">
            <CardHeader>
              <CardTitle>New Policy</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreate} className="space-y-4">
                <div className="space-y-1">
                  <Label htmlFor="broker_id">Broker</Label>
                  <select
                    id="broker_id"
                    value={form.broker_id}
                    onChange={(e) => setForm({ ...form, broker_id: e.target.value, customer_id: "" })}
                    required
                    className={selectClassName}
                  >
                    <option value="">Select broker...</option>
                    {approvedBrokers.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.company_name} ({(b.commission_rate_bps / 100).toFixed(2)}%)
                      </option>
                    ))}
                  </select>
                  {approvedBrokers.length === 0 && (
                    <p className="text-sm text-amber-500">No approved brokers available.</p>
                  )}
                </div>

                <div className="space-y-1">
                  <Label htmlFor="customer_id">Customer</Label>
                  <select
                    id="customer_id"
                    value={form.customer_id}
                    onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
                    required
                    disabled={!selectedBrokerId}
                    className={selectClassName}
                  >
                    <option value="">{selectedBrokerId ? "Select customer..." : "Select a broker first"}</option>
                    {availableCustomers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.first_name} {c.last_name} ({c.username})
                      </option>
                    ))}
                  </select>
                  {selectedBrokerId && availableCustomers.length === 0 && (
                    <p className="text-sm text-amber-500">All customers already have an active policy with this broker.</p>
                  )}
                </div>

                <div className="space-y-1">
                  <Label htmlFor="effective_date">Effective Date</Label>
                  <Input
                    id="effective_date"
                    type="date"
                    value={form.effective_date}
                    onChange={(e) => setForm({ ...form, effective_date: e.target.value })}
                    required
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="premium_amount_cents">Annual Premium ($)</Label>
                  <Input
                    id="premium_amount_cents"
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder="e.g. 120000.00"
                    value={form.premium_amount_cents}
                    onChange={(e) => setForm({ ...form, premium_amount_cents: e.target.value })}
                    required
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="coverage_territory">Coverage Territory</Label>
                  <select
                    id="coverage_territory"
                    value={form.coverage_territory}
                    onChange={(e) => setForm({ ...form, coverage_territory: e.target.value })}
                    required
                    className={selectClassName}
                  >
                    <option value="">Select jurisdiction...</option>
                    {jurisdictions.map((j) => (
                      <option key={j} value={j}>{j}</option>
                    ))}
                  </select>
                  {jurisdictions.length === 0 && !loadingData && (
                    <p className="text-sm text-amber-500">
                      No jurisdictions configured. Add tax/fee rules in the admin panel.
                    </p>
                  )}
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

        {lastCharges && (
          <Card className="mt-4 mb-6 border-green-500 bg-green-50 dark:bg-green-950/20">
            <CardHeader>
              <CardTitle>Policy Created — Charge Breakdown</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              <p>Premium: {formatCents(lastCharges.premium_cents as number)}</p>
              <p>Total Tax: {formatCents(lastCharges.total_tax_cents as number)}</p>
              <p>Total Fees: {formatCents(lastCharges.total_fees_cents as number)}</p>
              <p className="font-bold">Total: {formatCents(lastCharges.total_cents as number)}</p>
              <Button variant="outline" className="mt-2" onClick={() => setLastCharges(null)}>
                Dismiss
              </Button>
            </CardContent>
          </Card>
        )}

        {error && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {loadingData && <p className="mt-4 text-muted-foreground">Loading...</p>}
        {!loadingData && policies.length === 0 && (
          <p className="mt-4 text-muted-foreground">No policies found.</p>
        )}

        {policies.length > 0 && (
          <Table className="mt-4">
            <TableHeader>
              <TableRow>
                <TableHead>Policy #</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Effective</TableHead>
                <TableHead>Expiration</TableHead>
                <TableHead>Premium</TableHead>
                <TableHead>Territory</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {policies.map((p) => (
                <TableRow
                  key={p.id}
                  className="cursor-pointer"
                  onClick={() => router.push(`/staff/policies/detail?id=${p.id}`)}
                >
                  <TableCell className="font-medium text-primary underline">
                    {p.policy_number}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={p.status} />
                  </TableCell>
                  <TableCell>
                    {p.effective_date}
                    {(p.status === "DRAFT" || p.status === "PENDING_PAYMENT") &&
                      new Date(p.effective_date + "T00:00:00") < new Date(new Date().toDateString()) && (
                      <span className="ml-1 text-xs font-medium text-red-600">EXPIRED</span>
                    )}
                  </TableCell>
                  <TableCell>{p.expiration_date}</TableCell>
                  <TableCell>{formatCents(p.premium_amount_cents)}</TableCell>
                  <TableCell>{p.coverage_territory}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </main>
    </>
  );
}
