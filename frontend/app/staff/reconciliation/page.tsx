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
import { formatCents } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
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
import { Skeleton } from "@/components/ui/skeleton";

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
      <main className="mx-auto max-w-5xl p-6">
        <h1 className="text-2xl font-bold mb-4">Reconciliation</h1>

        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription className="flex items-center justify-between">
              {error}
              <Button variant="outline" size="sm" onClick={loadData}>
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {/* Trigger */}
        <div className="mb-6">
          <Button onClick={handleTrigger} disabled={triggering}>
            {triggering ? "Running..." : "Run Reconciliation"}
          </Button>
        </div>

        {/* Recent Runs */}
        <h2 className="text-xl font-semibold mb-3">Recent Runs</h2>
        {loadingData ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : runs.length === 0 ? (
          <p className="text-muted-foreground">No reconciliation runs yet.</p>
        ) : (
          <div className="mb-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Breaks</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="text-sm">{r.id}</TableCell>
                    <TableCell className="text-sm">{r.run_date}</TableCell>
                    <TableCell><StatusBadge status={r.status} /></TableCell>
                    <TableCell className="text-sm">{r.breaks_count}</TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" onClick={() => handleViewRun(r.id)}>
                        Detail
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Selected Run Detail */}
        {selectedRun && (
          <Card className="mb-6 border-primary bg-primary/5">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Run #{selectedRun.id} &mdash; {selectedRun.run_date}</CardTitle>
                <Button variant="ghost" size="sm" onClick={() => setSelectedRun(null)}>
                  Close
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm mb-3">
                <StatusBadge status={selectedRun.status} />
                <span className="ml-2">Breaks: {selectedRun.breaks.length}</span>
              </p>
              {selectedRun.breaks.length > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead>Expected</TableHead>
                      <TableHead>Actual</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedRun.breaks.map((b) => (
                      <TableRow key={b.id}>
                        <TableCell><StatusBadge status={b.break_type} /></TableCell>
                        <TableCell className="text-sm">{b.description}</TableCell>
                        <TableCell className="text-sm">{b.expected_amount_cents !== null ? formatCents(b.expected_amount_cents) : "—"}</TableCell>
                        <TableCell className="text-sm">{b.actual_amount_cents !== null ? formatCents(b.actual_amount_cents) : "—"}</TableCell>
                        <TableCell><StatusBadge status={b.status} /></TableCell>
                        <TableCell>
                          {b.status !== "RESOLVED" && (
                            <Button variant="outline" size="sm" onClick={() => handleResolve(b.id)}>
                              Resolve
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        )}

        {/* All Breaks */}
        <h2 className="text-xl font-semibold mb-3">Breaks</h2>
        <div className="mb-3 flex gap-2">
          {["OPEN", "ACKNOWLEDGED", "RESOLVED", ""].map((f) => (
            <Button
              key={f}
              variant={breakFilter === f ? "default" : "secondary"}
              size="sm"
              onClick={() => handleFilterChange(f)}
            >
              {f || "ALL"}
            </Button>
          ))}
        </div>
        {breaks.length === 0 ? (
          <p className="text-muted-foreground">No breaks found.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Expected</TableHead>
                <TableHead>Actual</TableHead>
                <TableHead>Age</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {breaks.map((b) => (
                <TableRow key={b.id}>
                  <TableCell><StatusBadge status={b.break_type} /></TableCell>
                  <TableCell className="text-sm">{b.description}</TableCell>
                  <TableCell className="text-sm">{b.expected_amount_cents !== null ? formatCents(b.expected_amount_cents) : "—"}</TableCell>
                  <TableCell className="text-sm">{b.actual_amount_cents !== null ? formatCents(b.actual_amount_cents) : "—"}</TableCell>
                  <TableCell className="text-sm">{formatAge(b.age_seconds)}</TableCell>
                  <TableCell><StatusBadge status={b.status} /></TableCell>
                  <TableCell>
                    {b.status !== "RESOLVED" && (
                      <Button variant="outline" size="sm" onClick={() => handleResolve(b.id)}>
                        Resolve
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </main>
    </>
  );
}
