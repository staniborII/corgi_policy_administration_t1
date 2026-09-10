"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useRealtimeRefresh } from "@/lib/useRealtimeRefresh";
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
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function CustomerPolicyDetailPage() {
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <CustomerPolicyDetailContent />
    </Suspense>
  );
}

function CustomerPolicyDetailContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const policyId = searchParams.get("id");

  const [policy, setPolicy] = useState<Policy | null>(null);
  const [endorsements, setEndorsements] = useState<EndorsementRecord[]>([]);
  const [refunds, setRefunds] = useState<RefundRecord[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const [asOfDate, setAsOfDate] = useState("");
  const [asOfSnapshot, setAsOfSnapshot] = useState<AsOfSnapshot | null>(null);
  const [loadingAsOf, setLoadingAsOf] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "CUSTOMER") {
      router.replace("/login");
      return;
    }
    if (!policyId) {
      router.replace("/customer/policies");
      return;
    }
    loadData();
  }, [user, loading, router, policyId]);

  useRealtimeRefresh(["policy.", "endorsement.", "payment."], loadData);

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

  async function handleApprove(endorsementId: number) {
    setActionLoading(endorsementId);
    setError("");
    try {
      await api.approveEndorsement(endorsementId);
      await loadData();
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.body) : "Failed to approve endorsement.");
    } finally {
      setActionLoading(null);
    }
  }

  async function handlePayEndorsement(policyIdNum: number) {
    setError("");
    try {
      const result = await api.createCheckout(policyIdNum);
      if (result.checkout_url) {
        window.location.assign(result.checkout_url);
      } else if (result.simulated) {
        await api.simulatePayment(result.payment_id);
        await loadData();
      }
    } catch {
      setError("Failed to initiate payment.");
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
      setError("Failed to load historical view.");
    } finally {
      setLoadingAsOf(false);
    }
  }

  function pdfPath(type: "declarations" | "endorsement-schedule", asOf?: string) {
    const base = `/api/documents/policy/${policyId}/${type}/`;
    return asOf ? `${base}?as_of=${encodeURIComponent(new Date(asOf).toISOString())}` : base;
  }

  async function downloadPdf(type: "declarations" | "endorsement-schedule", asOf?: string) {
    try {
      const { getToken } = await import("@/lib/api");
      const t = getToken();
      const headers: Record<string, string> = {};
      if (t) headers["Authorization"] = `Token ${t}`;
      const res = await fetch(`${API_BASE}${pdfPath(type, asOf)}`, { headers });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail || "Failed to download document.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = res.headers.get("Content-Disposition")?.split("filename=")[1]?.replace(/"/g, "") || `${type}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError("Failed to download document.");
    }
  }

  if (loading || !user) return null;
  if (loadingData) {
    return (
      <>
        <Nav />
        <main className="mx-auto max-w-4xl p-6">
          <Skeleton className="mb-4 h-8 w-32" />
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
          <Skeleton className="mt-6 h-32 w-full" />
          <Skeleton className="mt-6 h-48 w-full" />
        </main>
      </>
    );
  }

  if (!policy) {
    return (
      <>
        <Nav />
        <main className="mx-auto max-w-4xl p-6">
          <Alert variant="destructive">
            <AlertDescription>{error || "Policy not found."}</AlertDescription>
          </Alert>
          <div className="mt-4 flex gap-2">
            <Button variant="outline" onClick={() => router.push("/customer/policies")}>
              Back to My Policies
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

  const pendingApproval = endorsements.filter((e) => e.status === "PENDING_CUSTOMER_APPROVAL");
  const hasPendingPayment = endorsements.some((e) => e.status === "PENDING_PAYMENT");

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-4xl p-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/customer/policies")}
          className="mb-4"
        >
          &larr; Back to My Policies
        </Button>

        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">{policy.policy_number}</h1>
          <StatusBadge status={policy.status} />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
          <div>Effective: {policy.effective_date}</div>
          <div>Expires: {policy.expiration_date}</div>
          <div>Premium: {formatCents(policy.premium_amount_cents)}</div>
          <div>Territory: {policy.coverage_territory}</div>
        </div>

        {error && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription className="flex items-center justify-between">
              {error}
              <Button variant="outline" size="sm" onClick={loadData}>
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {/* Pending Approvals */}
        {pendingApproval.length > 0 && (
          <Card className="mt-6 border-2 border-orange-400 bg-orange-50">
            <CardHeader>
              <CardTitle className="text-orange-600">
                Endorsements Requiring Your Approval
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {pendingApproval.map((e) => (
                <Card key={e.id}>
                  <CardContent className="pt-4">
                    <div className="flex items-center justify-between">
                      <strong>{e.endorsement_number}</strong>
                      <StatusBadge status={e.status} />
                    </div>
                    <p className="mt-2 text-sm">{e.description}</p>
                    <div className="mt-1 text-sm text-muted-foreground">
                      <span>Type: {e.endorsement_type}</span>
                      {" | "}
                      <span>Effective: {e.effective_date}</span>
                      {" | "}
                      <span>Premium Change: {formatCents(e.premium_change_cents)}</span>
                    </div>
                    {e.charges_snapshot && (
                      <div className="mt-1 text-sm">
                        Total Due: <strong>{formatCents(e.charges_snapshot.total_cents as number)}</strong>
                      </div>
                    )}
                    <Button
                      onClick={() => handleApprove(e.id)}
                      disabled={actionLoading === e.id}
                      className="mt-3 bg-green-600 hover:bg-green-700"
                    >
                      {actionLoading === e.id ? "Approving..." : "Approve Endorsement"}
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Pending Payment Notice */}
        {hasPendingPayment && (
          <Card className="mt-4 border-amber-200 bg-amber-50">
            <CardContent className="pt-4">
              <p className="mb-2 text-sm">
                Additional payment required for endorsed changes.
              </p>
              <Button
                onClick={() => handlePayEndorsement(policy.id)}
                className="bg-green-600 hover:bg-green-700"
              >
                Pay Additional Premium
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Documents */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Documents</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => downloadPdf("declarations")}>
                Download Declarations
              </Button>
              <Button size="sm" onClick={() => downloadPdf("endorsement-schedule")}>
                Download Endorsement Schedule
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Historical View */}
        <Card className="mt-6">
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
              <Button
                variant="outline"
                onClick={handleAsOf}
                disabled={loadingAsOf}
              >
                {loadingAsOf ? "Loading..." : "View"}
              </Button>
            </div>

            {asOfSnapshot && (
              <div className="mt-3 rounded-md bg-blue-50 p-3">
                <p>
                  <strong>As of:</strong> {new Date(asOfSnapshot.as_of).toLocaleString()}
                </p>
                <p>Effective Premium: {formatCents(asOfSnapshot.effective_premium_cents)}</p>
                {asOfSnapshot.endorsements.length > 0 ? (
                  <Table className="mt-2">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Number</TableHead>
                        <TableHead>Effective</TableHead>
                        <TableHead>Change</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {asOfSnapshot.endorsements.map((e) => (
                        <TableRow key={e.id}>
                          <TableCell>{e.endorsement_number}</TableCell>
                          <TableCell>{e.effective_date}</TableCell>
                          <TableCell>{formatCents(e.premium_change_cents)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="mt-2 text-sm text-muted-foreground">
                    No endorsements at that time.
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* All Endorsements */}
        <div className="mt-6">
          <h2 className="text-xl font-semibold">Endorsement History</h2>
          {endorsements.length === 0 && (
            <p className="mt-2 text-muted-foreground">No endorsements on this policy.</p>
          )}
          {endorsements.length > 0 && (
            <Table className="mt-2">
              <TableHeader>
                <TableRow>
                  <TableHead>Number</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Effective</TableHead>
                  <TableHead>Premium Change</TableHead>
                  <TableHead>Description</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {endorsements.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell>{e.endorsement_number}</TableCell>
                    <TableCell><StatusBadge status={e.status} /></TableCell>
                    <TableCell>{e.effective_date}</TableCell>
                    <TableCell>{formatCents(e.premium_change_cents)}</TableCell>
                    <TableCell>{e.description}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {/* Refunds */}
        {refunds.length > 0 && (
          <div className="mt-6">
            <h2 className="text-xl font-semibold">Refunds</h2>
            <Table className="mt-2">
              <TableHeader>
                <TableRow>
                  <TableHead>Amount</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {refunds.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{formatCents(r.amount_cents)}</TableCell>
                    <TableCell><StatusBadge status={r.status} /></TableCell>
                    <TableCell>{r.reason}</TableCell>
                    <TableCell>{new Date(r.created_at).toLocaleDateString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </main>
    </>
  );
}
