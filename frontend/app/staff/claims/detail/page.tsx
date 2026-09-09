"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  api,
  ApiError,
  type ClaimDetail,
  type ClaimPaymentRecord,
  type PayoutDestinationRecord,
  type ReserveEventRecord,
} from "@/lib/api";
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

function ClaimDetailContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const claimId = Number(searchParams.get("id"));

  const [detail, setDetail] = useState<ClaimDetail | null>(null);
  const [reserves, setReserves] = useState<ReserveEventRecord[]>([]);
  const [payments, setPayments] = useState<ClaimPaymentRecord[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState("");

  // Reserve form
  const [reserveAmount, setReserveAmount] = useState("");
  const [reserveType, setReserveType] = useState("INITIAL");
  const [reserveMemo, setReserveMemo] = useState("");

  // Payment form
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentPayee, setPaymentPayee] = useState("");

  // Payout destination form
  const [destPayeeName, setDestPayeeName] = useState("");
  const [destLastFour, setDestLastFour] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "STAFF") router.replace("/login");
  }, [user, loading, router]);

  const reload = useCallback(async () => {
    if (!claimId) return;
    try {
      const [d, r, p] = await Promise.all([
        api.getClaim(claimId),
        api.listReserveEvents(claimId),
        api.listClaimPayments(claimId),
      ]);
      setDetail(d);
      setReserves(r);
      setPayments(p);
    } catch {
      setError("Failed to load claim data.");
    } finally {
      setLoadingData(false);
    }
  }, [claimId]);

  useEffect(() => {
    if (loading || !user || !claimId) return;
    reload();
  }, [loading, user, claimId, reload]);

  function getErrorMessage(err: unknown): string {
    if (err instanceof ApiError) {
      const body = err.body as Record<string, unknown>;
      return (body.detail as string) || `API error ${err.status}`;
    }
    return err instanceof Error ? err.message : "An error occurred";
  }

  async function handleSetReserve(e: React.FormEvent) {
    e.preventDefault();
    setActionLoading("reserve");
    setError("");
    try {
      await api.setReserve(claimId, {
        amount_cents: Math.round(parseFloat(reserveAmount) * 100),
        reserve_type: reserveType,
        memo: reserveMemo,
      });
      setReserveAmount("");
      setReserveMemo("");
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleCreatePayment(e: React.FormEvent) {
    e.preventDefault();
    setActionLoading("payment");
    setError("");
    try {
      await api.createClaimPayment(claimId, {
        amount_cents: Math.round(parseFloat(paymentAmount) * 100),
        payee: paymentPayee,
      });
      setPaymentAmount("");
      setPaymentPayee("");
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleApprovePayment(paymentId: number) {
    setActionLoading(`approve-${paymentId}`);
    setError("");
    try {
      await api.approveClaimPayment(paymentId);
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleExecutePayout(paymentId: number) {
    setActionLoading(`execute-${paymentId}`);
    setError("");
    try {
      await api.executeClaimPayout(paymentId);
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleSimulateSettled(paymentId: number, ref: string, amount: number) {
    setActionLoading(`settle-${paymentId}`);
    setError("");
    try {
      await api.simulatePayoutCallback({ payout_reference: ref, event_type: "SETTLED", amount_cents: amount });
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleSimulateReturned(paymentId: number, ref: string) {
    setActionLoading(`return-${paymentId}`);
    setError("");
    try {
      await api.simulatePayoutCallback({ payout_reference: ref, event_type: "RETURNED", reason: "Simulated return" });
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleSetDestination(e: React.FormEvent) {
    e.preventDefault();
    setActionLoading("dest");
    setError("");
    try {
      await api.setPayoutDestination(claimId, {
        payee_name: destPayeeName,
        account_last_four: destLastFour,
      });
      setDestPayeeName("");
      setDestLastFour("");
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  async function handleVerifyDestination(outcome: string) {
    setActionLoading(`verify-${outcome}`);
    setError("");
    try {
      await api.verifyPayoutDestination(claimId, outcome);
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActionLoading("");
    }
  }

  if (loading || !user) return null;
  if (loadingData) return <><Nav /><main className="mx-auto max-w-5xl p-6"><p className="text-sm text-muted-foreground">Loading...</p></main></>;
  if (!detail) return <><Nav /><main className="mx-auto max-w-5xl p-6"><p className="text-sm text-muted-foreground">Claim not found.</p></main></>;

  const { claim, financials, payout_destination: dest } = detail;

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-5xl p-6">
        <a href="/staff/claims" className="text-sm text-primary underline">
          &larr; Back to Claims
        </a>

        <div className="mt-2 flex items-center justify-between">
          <h1 className="text-2xl font-bold">Claim {claim.claim_number}</h1>
          <StatusBadge status={claim.status} />
        </div>

        {error && (
          <Alert variant="destructive" className="mt-2">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Info grid */}
        <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
          <div>Date of Loss: {claim.date_of_loss}</div>
          <div>Reported: {new Date(claim.reported_at).toLocaleDateString()}</div>
          <div>Estimated: {claim.estimated_amount_cents ? formatCents(claim.estimated_amount_cents) : "—"}</div>
          <div>Description: {claim.description}</div>
        </div>

        {/* Financials */}
        <Card className="mt-6">
          <CardContent className="grid grid-cols-3 gap-4 pt-6">
            <div>
              <div className="text-xs font-bold text-muted-foreground">Reserve</div>
              <div className="text-xl">{formatCents(financials.reserve_cents)}</div>
            </div>
            <div>
              <div className="text-xs font-bold text-muted-foreground">Paid</div>
              <div className="text-xl">{formatCents(financials.paid_cents)}</div>
            </div>
            <div>
              <div className="text-xs font-bold text-muted-foreground">Incurred</div>
              <div className="text-xl">{formatCents(financials.incurred_cents)}</div>
            </div>
          </CardContent>
        </Card>

        {/* Payout Destination */}
        <h2 className="mt-6 text-lg font-semibold">Payout Destination</h2>
        {dest ? (
          <Card className="mt-2">
            <CardContent className="pt-6 text-sm">
              <div className="flex items-center justify-between">
                <div>
                  <strong>{dest.payee_name}</strong> — ****{dest.account_last_four}
                  <span className="ml-2 text-xs text-amber-500">
                    [{dest.provider}]
                  </span>
                </div>
                <StatusBadge status={dest.verification_status} />
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                Ref: {dest.provider_reference}
              </div>
              {dest.verification_status === "PENDING" && (
                <div className="mt-2 flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => handleVerifyDestination("VERIFIED")}
                    disabled={actionLoading.startsWith("verify")}
                  >
                    Simulate Verify
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => handleVerifyDestination("FAILED")}
                    disabled={actionLoading.startsWith("verify")}
                  >
                    Simulate Fail
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        ) : (
          <Card className="mt-2">
            <CardContent className="pt-6">
              <form onSubmit={handleSetDestination} className="space-y-3">
                <div>
                  <Label>Payee Name</Label>
                  <Input
                    value={destPayeeName}
                    onChange={(e) => setDestPayeeName(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label>Last 4 Digits</Label>
                  <Input
                    value={destLastFour}
                    onChange={(e) => setDestLastFour(e.target.value)}
                    required
                    maxLength={4}
                    minLength={4}
                    className="mt-1"
                  />
                </div>
                <Button type="submit" disabled={actionLoading === "dest"}>
                  {actionLoading === "dest" ? "Setting..." : "Set Destination"}
                </Button>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Reserves */}
        <h2 className="mt-6 text-lg font-semibold">Reserve Events</h2>
        <Card className="mt-2">
          <CardContent className="pt-6">
            <form onSubmit={handleSetReserve} className="space-y-3">
              <div className="grid grid-cols-[1fr_1fr_2fr] gap-3">
                <div>
                  <Label>Amount ($)</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={reserveAmount}
                    onChange={(e) => setReserveAmount(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label>Type</Label>
                  <select
                    value={reserveType}
                    onChange={(e) => setReserveType(e.target.value)}
                    className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    <option value="INITIAL">Initial</option>
                    <option value="ADJUSTMENT">Adjustment</option>
                    <option value="RELEASE">Release</option>
                  </select>
                </div>
                <div>
                  <Label>Memo</Label>
                  <Input
                    value={reserveMemo}
                    onChange={(e) => setReserveMemo(e.target.value)}
                    className="mt-1"
                  />
                </div>
              </div>
              <Button type="submit" disabled={actionLoading === "reserve"}>
                {actionLoading === "reserve" ? "Setting..." : "Add Reserve Event"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {reserves.length > 0 && (
          <Table className="mt-4 text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Memo</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reserves.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.reserve_type}</TableCell>
                  <TableCell>{formatCents(r.amount_cents)}</TableCell>
                  <TableCell>{r.memo || "—"}</TableCell>
                  <TableCell>{new Date(r.recorded_at).toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {/* Payments */}
        <h2 className="mt-6 text-lg font-semibold">Payments</h2>
        <Card className="mt-2">
          <CardContent className="pt-6">
            <form onSubmit={handleCreatePayment} className="space-y-3">
              <div className="grid grid-cols-[1fr_2fr] gap-3">
                <div>
                  <Label>Amount ($)</Label>
                  <Input
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={paymentAmount}
                    onChange={(e) => setPaymentAmount(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label>Payee</Label>
                  <Input
                    value={paymentPayee}
                    onChange={(e) => setPaymentPayee(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>
              </div>
              <Button type="submit" disabled={actionLoading === "payment"}>
                {actionLoading === "payment" ? "Creating..." : "Create Payment"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {payments.length > 0 && (
          <Table className="mt-4 text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Payee</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Payout Ref</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {payments.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{p.id}</TableCell>
                  <TableCell>{formatCents(p.amount_cents)}</TableCell>
                  <TableCell>{p.payee}</TableCell>
                  <TableCell><StatusBadge status={p.status} /></TableCell>
                  <TableCell className="text-xs">{p.payout_reference || "—"}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {p.status === "PENDING_APPROVAL" && (
                        <Button
                          size="sm"
                          onClick={() => handleApprovePayment(p.id)}
                          disabled={actionLoading === `approve-${p.id}`}
                        >
                          Approve
                        </Button>
                      )}
                      {p.status === "APPROVED" && (
                        <Button
                          size="sm"
                          onClick={() => handleExecutePayout(p.id)}
                          disabled={actionLoading === `execute-${p.id}`}
                        >
                          Execute Payout
                        </Button>
                      )}
                      {p.status === "PENDING" && p.payout_reference && (
                        <>
                          <Button
                            size="sm"
                            onClick={() => handleSimulateSettled(p.id, p.payout_reference, p.amount_cents)}
                            disabled={actionLoading === `settle-${p.id}`}
                          >
                            Sim Settle
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => handleSimulateReturned(p.id, p.payout_reference)}
                            disabled={actionLoading === `return-${p.id}`}
                          >
                            Sim Return
                          </Button>
                        </>
                      )}
                    </div>
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

export default function StaffClaimDetailPage() {
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <ClaimDetailContent />
    </Suspense>
  );
}
