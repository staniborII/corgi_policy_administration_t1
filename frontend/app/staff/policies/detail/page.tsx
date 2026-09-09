"use client";

import { Suspense, useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  api,
  type Policy,
  type EndorsementRecord,
  type AsOfSnapshot,
  type RefundRecord,
  ApiError,
} from "@/lib/api";
import Nav from "@/components/Nav";
import { formatCents } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function StaffPolicyDetailPage() {
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <StaffPolicyDetailContent />
    </Suspense>
  );
}

function StaffPolicyDetailContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const policyId = searchParams.get("id");

  const [policy, setPolicy] = useState<Policy | null>(null);
  const [endorsements, setEndorsements] = useState<EndorsementRecord[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [endForm, setEndForm] = useState({
    endorsement_type: "COVERAGE_LIMIT_CHANGE",
    effective_date: "",
    annual_premium_delta_cents: "",
    description: "",
  });
  const [createError, setCreateError] = useState("");
  const [creating, setCreating] = useState(false);
  const [lastCharges, setLastCharges] = useState<Record<string, unknown> | null>(null);

  const [showCorrect, setShowCorrect] = useState<number | null>(null);
  const [correctDate, setCorrectDate] = useState("");
  const [correctError, setCorrectError] = useState("");

  const [asOfDate, setAsOfDate] = useState("");
  const [asOfSnapshot, setAsOfSnapshot] = useState<AsOfSnapshot | null>(null);
  const [loadingAsOf, setLoadingAsOf] = useState(false);

  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const [cancelling, setCancelling] = useState(false);
  const [cancelDate, setCancelDate] = useState("");
  const [cancelResult, setCancelResult] = useState<Record<string, unknown> | null>(null);
  const [refunds, setRefunds] = useState<RefundRecord[]>([]);
  const [simulatingRefund, setSimulatingRefund] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "STAFF") {
      router.replace("/login");
      return;
    }
    if (!policyId) {
      router.replace("/staff/policies");
      return;
    }
    loadData();
  }, [user, loading, router, policyId]);

  async function loadData() {
    if (!policyId) return;
    setLoadingData(true);
    try {
      const [p, e, r] = await Promise.all([
        api.getPolicy(parseInt(policyId, 10)),
        api.listEndorsements(parseInt(policyId, 10)),
        api.listPolicyRefunds(parseInt(policyId, 10)),
      ]);
      setPolicy(p);
      setEndorsements(e);
      setRefunds(r);
    } catch {
      setError("Failed to load policy data.");
    } finally {
      setLoadingData(false);
    }
  }

  async function handleCreateEndorsement(e: FormEvent) {
    e.preventDefault();
    if (!policyId) return;
    setCreateError("");
    setCreating(true);
    setLastCharges(null);
    try {
      const result = await api.createEndorsement({
        policy_id: parseInt(policyId, 10),
        endorsement_type: endForm.endorsement_type,
        effective_date: endForm.effective_date,
        annual_premium_delta_cents: parseInt(endForm.annual_premium_delta_cents, 10),
        description: endForm.description,
      });
      setLastCharges(result.charges);
      setShowCreate(false);
      setEndForm({
        endorsement_type: "COVERAGE_LIMIT_CHANGE",
        effective_date: "",
        annual_premium_delta_cents: "",
        description: "",
      });
      await loadData();
    } catch (err) {
      setCreateError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to create endorsement.");
    } finally {
      setCreating(false);
    }
  }

  async function handleApply(endorsementId: number) {
    setActionLoading(endorsementId);
    try {
      await api.applyEndorsement(endorsementId);
      await loadData();
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to apply endorsement.");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleCorrect(endorsementId: number) {
    if (!correctDate) return;
    setCorrectError("");
    setActionLoading(endorsementId);
    try {
      await api.correctEndorsement(endorsementId, correctDate);
      setShowCorrect(null);
      setCorrectDate("");
      await loadData();
    } catch (err) {
      setCorrectError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to correct endorsement.");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleAsOf() {
    if (!policyId) return;
    setLoadingAsOf(true);
    try {
      const snapshot = await api.getPolicyAsOf(
        parseInt(policyId, 10),
        asOfDate ? new Date(asOfDate).toISOString() : undefined,
      );
      setAsOfSnapshot(snapshot);
    } catch {
      setError("Failed to load as-of snapshot.");
    } finally {
      setLoadingAsOf(false);
    }
  }

  async function handleCancel() {
    if (!policyId) return;
    if (!confirm("Are you sure you want to cancel this policy? A pro-rata refund will be created.")) return;
    setCancelling(true);
    setError("");
    try {
      const result = await api.cancelPolicy(parseInt(policyId, 10), cancelDate || undefined);
      setCancelResult(result as unknown as Record<string, unknown>);
      await loadData();
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to cancel policy.");
    } finally {
      setCancelling(false);
    }
  }

  async function handleSimulateRefund(refundId: number) {
    setSimulatingRefund(true);
    setError("");
    try {
      await api.simulateRefund(refundId);
      await loadData();
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to simulate refund.");
    } finally {
      setSimulatingRefund(false);
    }
  }

  function pdfUrl(type: "declarations" | "endorsement-schedule", asOf?: string) {
    const base = `${API_BASE}/api/documents/policy/${policyId}/${type}/`;
    return asOf ? `${base}?as_of=${encodeURIComponent(new Date(asOf).toISOString())}` : base;
  }

  if (loading || !user) return null;
  if (loadingData) {
    return (
      <>
        <Nav />
        <main className="mx-auto max-w-5xl p-6">
          <Skeleton className="mb-4 h-5 w-32" />
          <div className="flex items-center justify-between">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-6 w-20" />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-5 w-36" />
            <Skeleton className="h-5 w-36" />
          </div>
          <Skeleton className="mt-6 h-px w-full" />
          <Skeleton className="mt-6 h-32 w-full" />
          <Skeleton className="mt-6 h-px w-full" />
          <Skeleton className="mt-6 h-48 w-full" />
        </main>
      </>
    );
  }

  if (!policy) {
    return (
      <>
        <Nav />
        <main className="mx-auto max-w-5xl p-6">
          <Alert variant="destructive">
            <AlertDescription>{error || "Policy not found."}</AlertDescription>
          </Alert>
          <div className="mt-4 flex gap-2">
            <Button variant="outline" onClick={() => router.push("/staff/policies")}>
              Back to Policies
            </Button>
            {error && (
              <Button variant="secondary" onClick={loadData}>
                Retry
              </Button>
            )}
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-5xl p-6">
        {/* Back link */}
        <Button
          variant="link"
          className="mb-4 px-0 text-sm"
          onClick={() => router.push("/staff/policies")}
        >
          &larr; Back to Policies
        </Button>

        {/* Policy header */}
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">{policy.policy_number}</h1>
          <StatusBadge status={policy.status} />
        </div>

        {/* Policy info grid */}
        <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
          <div>Effective: {policy.effective_date}</div>
          <div>Expires: {policy.expiration_date}</div>
          <div>Premium: {formatCents(policy.premium_amount_cents)}</div>
          <div>Territory: {policy.coverage_territory}</div>
        </div>

        {/* Error display */}
        {error && (
          <Alert variant="destructive" className="mt-3">
            <AlertDescription className="flex items-center justify-between">
              {error}
              <Button variant="outline" size="sm" onClick={loadData}>
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}

        <Separator className="my-6" />

        {/* PDF Downloads */}
        <Card>
          <CardHeader>
            <CardTitle>Documents</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              <a href={pdfUrl("declarations")} className={buttonVariants()}>
                Download Declarations
              </a>
              <a href={pdfUrl("endorsement-schedule")} className={buttonVariants()}>
                Download Endorsement Schedule
              </a>
            </div>
          </CardContent>
        </Card>

        <Separator className="my-6" />

        {/* As-Of View */}
        <Card>
          <CardHeader>
            <CardTitle>Historical View (As-Of)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                type="datetime-local"
                value={asOfDate}
                onChange={(e) => setAsOfDate(e.target.value)}
                className="w-auto"
              />
              <Button onClick={handleAsOf} disabled={loadingAsOf}>
                {loadingAsOf ? "Loading..." : "View As-Of"}
              </Button>
              {asOfDate && (
                <>
                  <a href={pdfUrl("declarations", asOfDate)} className="text-sm text-primary underline-offset-4 hover:underline">
                    Declarations PDF (as-of)
                  </a>
                  <a href={pdfUrl("endorsement-schedule", asOfDate)} className="text-sm text-primary underline-offset-4 hover:underline">
                    Schedule PDF (as-of)
                  </a>
                </>
              )}
            </div>

            {asOfSnapshot && (
              <div className="mt-3 rounded-md bg-blue-50 p-3 dark:bg-blue-950">
                <p><strong>Policy state as of:</strong> {new Date(asOfSnapshot.as_of).toLocaleString()}</p>
                <p>Effective Premium: {formatCents(asOfSnapshot.effective_premium_cents)}</p>
                <p>Base Premium: {formatCents(asOfSnapshot.base_premium_cents)}</p>
                {asOfSnapshot.endorsements.length > 0 && (
                  <div className="mt-2">
                    <strong>Endorsements at that time:</strong>
                    <Table className="mt-1">
                      <TableHeader>
                        <TableRow>
                          <TableHead>#</TableHead>
                          <TableHead>Type</TableHead>
                          <TableHead>Effective</TableHead>
                          <TableHead>Premium Change</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {asOfSnapshot.endorsements.map((e) => (
                          <TableRow key={e.id}>
                            <TableCell>{e.endorsement_number}</TableCell>
                            <TableCell>{e.type}</TableCell>
                            <TableCell>{e.effective_date}</TableCell>
                            <TableCell>{formatCents(e.premium_change_cents)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
                {asOfSnapshot.endorsements.length === 0 && (
                  <p className="text-sm text-muted-foreground">No endorsements at that point in time.</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Separator className="my-6" />

        {/* Endorsements Section */}
        <div>
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Endorsements</h2>
            {policy.status === "ACTIVE" && (
              <Button
                variant={showCreate ? "outline" : "default"}
                onClick={() => setShowCreate(!showCreate)}
              >
                {showCreate ? "Cancel" : "Create Endorsement"}
              </Button>
            )}
          </div>

          {showCreate && (
            <Card className="mt-4 mb-4">
              <CardHeader>
                <CardTitle>New Endorsement</CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleCreateEndorsement} className="space-y-4">
                  <div className="space-y-1.5">
                    <Label>Type</Label>
                    <select
                      value={endForm.endorsement_type}
                      onChange={(e) => setEndForm({ ...endForm, endorsement_type: e.target.value })}
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    >
                      <option value="COVERAGE_LIMIT_CHANGE">Coverage Limit Change</option>
                      <option value="ADDRESS_CORRECTION">Address Correction</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Effective Date</Label>
                    <Input
                      type="date"
                      value={endForm.effective_date}
                      onChange={(e) => setEndForm({ ...endForm, effective_date: e.target.value })}
                      required
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Annual Premium Delta (cents)</Label>
                    <Input
                      type="number"
                      value={endForm.annual_premium_delta_cents}
                      onChange={(e) => setEndForm({ ...endForm, annual_premium_delta_cents: e.target.value })}
                      required
                    />
                    <p className="text-xs text-muted-foreground">
                      Positive = increase, negative = decrease. For address corrections, this is ignored.
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Description</Label>
                    <Input
                      type="text"
                      value={endForm.description}
                      onChange={(e) => setEndForm({ ...endForm, description: e.target.value })}
                      required
                    />
                  </div>
                  {createError && (
                    <Alert variant="destructive">
                      <AlertDescription>{createError}</AlertDescription>
                    </Alert>
                  )}
                  <Button type="submit" disabled={creating}>
                    {creating ? "Creating..." : "Create Endorsement"}
                  </Button>
                </form>
              </CardContent>
            </Card>
          )}

          {lastCharges && (
            <Card className="mb-4 border-green-500 bg-green-50 dark:bg-green-950">
              <CardHeader>
                <CardTitle>Endorsement Created — Charge Breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <p>Pro-Rated Premium: {formatCents(lastCharges.premium_change_cents as number)}</p>
                <p>Tax: {formatCents(lastCharges.total_tax_cents as number)}</p>
                <p>Fees: {formatCents(lastCharges.total_fees_cents as number)}</p>
                <p><strong>Total: {formatCents(lastCharges.total_cents as number)}</strong></p>
                <Button variant="ghost" size="sm" className="mt-2" onClick={() => setLastCharges(null)}>
                  Dismiss
                </Button>
              </CardContent>
            </Card>
          )}

          {endorsements.length === 0 && (
            <p className="mt-4 text-muted-foreground">No endorsements yet.</p>
          )}
          {endorsements.length > 0 && (
            <Table className="mt-4">
              <TableHeader>
                <TableRow>
                  <TableHead>Number</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Effective</TableHead>
                  <TableHead>Premium Change</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {endorsements.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="text-sm">
                      {e.endorsement_number}
                      {e.correction_of && (
                        <span className="block text-xs text-muted-foreground">
                          (correction)
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{e.endorsement_type}</TableCell>
                    <TableCell><StatusBadge status={e.status} /></TableCell>
                    <TableCell className="text-sm">{e.effective_date}</TableCell>
                    <TableCell className="text-sm">{formatCents(e.premium_change_cents)}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {(e.status === "APPROVED" || e.status === "PENDING_PAYMENT") && (
                          <Button
                            size="sm"
                            onClick={() => handleApply(e.id)}
                            disabled={actionLoading === e.id}
                          >
                            {actionLoading === e.id ? "..." : "Apply"}
                          </Button>
                        )}
                        {e.status === "APPLIED" && (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => { setShowCorrect(e.id); setCorrectDate(""); setCorrectError(""); }}
                          >
                            Correct
                          </Button>
                        )}
                      </div>

                      {showCorrect === e.id && (
                        <div className="mt-2 rounded-md border border-yellow-400 p-2 text-sm">
                          <Label className="mb-1 block">Corrected Effective Date:</Label>
                          <div className="flex flex-wrap items-center gap-2">
                            <Input
                              type="date"
                              value={correctDate}
                              onChange={(ev) => setCorrectDate(ev.target.value)}
                              className="w-auto"
                            />
                            <Button
                              size="sm"
                              onClick={() => handleCorrect(e.id)}
                              disabled={actionLoading === e.id || !correctDate}
                            >
                              {actionLoading === e.id ? "..." : "Submit Correction"}
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setShowCorrect(null)}
                            >
                              Cancel
                            </Button>
                          </div>
                          {correctError && (
                            <Alert variant="destructive" className="mt-2">
                              <AlertDescription>{correctError}</AlertDescription>
                            </Alert>
                          )}
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        <Separator className="my-6" />

        {/* Cancellation Section */}
        {policy.status === "ACTIVE" && (
          <Card className="border-destructive">
            <CardHeader>
              <CardTitle className="text-destructive">Cancel Policy</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-center gap-2">
                <Label className="text-sm">Cancellation Date (optional):</Label>
                <Input
                  type="date"
                  value={cancelDate}
                  onChange={(e) => setCancelDate(e.target.value)}
                  className="w-auto"
                />
                <Button
                  variant="destructive"
                  onClick={handleCancel}
                  disabled={cancelling}
                >
                  {cancelling ? "Cancelling..." : "Cancel Policy"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {cancelResult && (
          <Card className="mt-4 border-green-500 bg-green-50 dark:bg-green-950">
            <CardHeader>
              <CardTitle>Cancellation Complete</CardTitle>
            </CardHeader>
            <CardContent>
              <p>Unearned Premium: {formatCents(cancelResult.unearned_premium_cents as number)}</p>
              <p>Refundable Tax: {formatCents(cancelResult.total_refundable_tax_cents as number)}</p>
              <p>Refundable Fees: {formatCents(cancelResult.total_refundable_fees_cents as number)}</p>
              <p><strong>Total Refund: {formatCents(cancelResult.total_refund_cents as number)}</strong></p>
              <p>Commission Clawback: {formatCents(cancelResult.commission_clawback_cents as number)}</p>
              <Button variant="ghost" size="sm" className="mt-2" onClick={() => setCancelResult(null)}>
                Dismiss
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Refunds Section */}
        {refunds.length > 0 && (
          <>
            <Separator className="my-6" />
            <div>
              <h2 className="text-xl font-semibold">Refunds</h2>
              <Table className="mt-4">
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Amount</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Stripe Ref</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {refunds.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="text-sm">{r.id}</TableCell>
                      <TableCell className="text-sm">{formatCents(r.amount_cents)}</TableCell>
                      <TableCell><StatusBadge status={r.status} /></TableCell>
                      <TableCell className="font-mono text-xs">
                        {r.stripe_refund_id}
                        {r.stripe_refund_id.startsWith("SIMULATED") && (
                          <span className="ml-1 font-bold text-yellow-500">SIMULATED</span>
                        )}
                      </TableCell>
                      <TableCell className="text-sm">{r.reason}</TableCell>
                      <TableCell>
                        {r.status === "PENDING" && r.stripe_refund_id.startsWith("SIMULATED") && (
                          <Button
                            size="sm"
                            onClick={() => handleSimulateRefund(r.id)}
                            disabled={simulatingRefund}
                          >
                            {simulatingRefund ? "..." : "Simulate Success"}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </main>
    </>
  );
}
