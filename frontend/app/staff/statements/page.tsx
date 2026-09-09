"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type BrokerStatementRecord, type Broker, ApiError } from "@/lib/api";
import Nav from "@/components/Nav";
import { formatCents } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardHeader,
  CardContent,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";

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
      <main className="mx-auto max-w-5xl p-6">
        <h1 className="text-2xl font-bold mb-4">Broker Statements</h1>

        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Generate Form */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Generate Statement</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1">
                <Label htmlFor="broker-select">Broker</Label>
                <select
                  id="broker-select"
                  value={selectedBrokerId}
                  onChange={(e) => setSelectedBrokerId(e.target.value)}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="">Select Broker</option>
                  {brokers.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.company_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="period-start">From</Label>
                <Input
                  id="period-start"
                  type="date"
                  value={periodStart}
                  onChange={(e) => setPeriodStart(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="period-end">To</Label>
                <Input
                  id="period-end"
                  type="date"
                  value={periodEnd}
                  onChange={(e) => setPeriodEnd(e.target.value)}
                />
              </div>
              <Button onClick={handleGenerate} disabled={generating}>
                {generating ? "Generating..." : "Generate"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Statements List */}
        {loadingData ? (
          <p className="text-muted-foreground">Loading...</p>
        ) : statements.length === 0 ? (
          <p className="text-muted-foreground">No statements generated yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Broker</TableHead>
                <TableHead>Period</TableHead>
                <TableHead>Premium</TableHead>
                <TableHead>Commission</TableHead>
                <TableHead>Clawback</TableHead>
                <TableHead>Net Due</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {statements.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="text-sm">{s.id}</TableCell>
                  <TableCell className="text-sm">{s.broker_name}</TableCell>
                  <TableCell className="text-sm">{s.period_start} &ndash; {s.period_end}</TableCell>
                  <TableCell className="text-sm">{formatCents(s.total_premium_cents)}</TableCell>
                  <TableCell className="text-sm">{formatCents(s.total_commission_cents)}</TableCell>
                  <TableCell className="text-sm">{formatCents(s.total_clawback_cents)}</TableCell>
                  <TableCell className="text-sm font-bold">{formatCents(s.net_due_cents)}</TableCell>
                  <TableCell>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleViewDetail(s.id)}
                    >
                      Detail
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {/* Detail Panel */}
        {detail && (
          <Card className="mt-6 border-primary bg-primary/5">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Statement #{detail.id} &mdash; {detail.broker_name}</CardTitle>
                <Button variant="ghost" size="sm" onClick={() => setDetail(null)}>
                  Close
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm mb-1">Period: {detail.period_start} &ndash; {detail.period_end}</p>
              <p className="text-sm mb-4">
                Premium: {formatCents(detail.total_premium_cents)} | Commission: {formatCents(detail.total_commission_cents)} | Clawback: {formatCents(detail.total_clawback_cents)} | <strong>Net Due: {formatCents(detail.net_due_cents)}</strong>
              </p>

              {Array.isArray(detail.statement_data.payments) && detail.statement_data.payments.length > 0 && (
                <>
                  <Separator className="my-4" />
                  <h4 className="text-sm font-semibold mb-2">Payments</h4>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Policy</TableHead>
                        <TableHead>Premium</TableHead>
                        <TableHead>Total</TableHead>
                        <TableHead>Commission</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(detail.statement_data.payments as Array<Record<string, unknown>>).map((p, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-sm">{p.policy_number as string}</TableCell>
                          <TableCell className="text-sm">{formatCents(p.premium_cents as number)}</TableCell>
                          <TableCell className="text-sm">{formatCents(p.total_cents as number)}</TableCell>
                          <TableCell className="text-sm">{formatCents(p.commission_cents as number)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </>
              )}

              {Array.isArray(detail.statement_data.refunds) && detail.statement_data.refunds.length > 0 && (
                <>
                  <Separator className="my-4" />
                  <h4 className="text-sm font-semibold mb-2">Refunds</h4>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Policy</TableHead>
                        <TableHead>Refund</TableHead>
                        <TableHead>Clawback</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(detail.statement_data.refunds as Array<Record<string, unknown>>).map((r, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-sm">{r.policy_number as string}</TableCell>
                          <TableCell className="text-sm">{formatCents(r.refund_cents as number)}</TableCell>
                          <TableCell className="text-sm">{formatCents(r.clawback_cents as number)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </>
              )}
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}
