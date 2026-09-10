"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useRealtimeRefresh } from "@/lib/useRealtimeRefresh";
import { api, ApiError, type Policy, type PaymentRecord } from "@/lib/api";
import Nav from "@/components/Nav";
import { formatCents } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";

export default function CustomerPoliciesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [paymentLoading, setPaymentLoading] = useState<number | null>(null);
  const [decliningId, setDecliningId] = useState<number | null>(null);
  const [payments, setPayments] = useState<Record<number, PaymentRecord[]>>({});

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "CUSTOMER") {
      router.replace("/login");
    }
  }, [user, loading, router]);

  const refreshPolicies = useCallback(() => {
    api.listPolicies().then(setPolicies).catch(() => {});
  }, []);

  useEffect(() => {
    if (loading || !user) return;
    let cancelled = false;
    setLoadingData(true);
    api.listPolicies()
      .then((data) => { if (!cancelled) setPolicies(data); })
      .catch(() => { if (!cancelled) setError("Failed to load policies."); })
      .finally(() => { if (!cancelled) setLoadingData(false); });
    return () => { cancelled = true; };
  }, [loading, user]);

  useRealtimeRefresh(["policy.", "payment."], refreshPolicies);

  async function handlePay(policyId: number) {
    setPaymentLoading(policyId);
    setError("");
    try {
      const result = await api.createCheckout(policyId);
      if (result.checkout_url) {
        const url = result.checkout_url;
        requestAnimationFrame(() => { window.location.assign(url); });
      } else if (result.simulated) {
        await api.simulatePayment(result.payment_id);
        const data = await api.listPolicies();
        setPolicies(data);
      }
    } catch (err) {
      const message = err instanceof ApiError && err.body?.detail
        ? String(err.body.detail)
        : "Failed to initiate payment.";
      setError(message);
    } finally {
      setPaymentLoading(null);
    }
  }

  async function handleDecline(policyId: number) {
    if (!confirm("Are you sure you want to decline this policy? This cannot be undone.")) return;
    setDecliningId(policyId);
    setError("");
    try {
      await api.declinePolicy(policyId);
      const data = await api.listPolicies();
      setPolicies(data);
    } catch (err) {
      const message = err instanceof ApiError && err.body?.detail
        ? String(err.body.detail)
        : "Failed to decline policy.";
      setError(message);
    } finally {
      setDecliningId(null);
    }
  }

  async function loadPayments(policyId: number) {
    try {
      const data = await api.listPolicyPayments(policyId);
      setPayments((prev) => ({ ...prev, [policyId]: data }));
    } catch {
      /* ignore */
    }
  }

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-4xl p-6">
        <h1 className="text-2xl font-bold">My Policies</h1>

        {error && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription className="flex items-center justify-between">
              {error}
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setLoadingData(true);
                  setError("");
                  api.listPolicies()
                    .then(setPolicies)
                    .catch(() => setError("Failed to load policies."))
                    .finally(() => setLoadingData(false));
                }}
              >
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}
        {loadingData && (
          <div className="mt-4 space-y-4">
            {[1, 2].map((i) => (
              <Card key={i}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <Skeleton className="h-6 w-40" />
                    <Skeleton className="h-6 w-20" />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-2">
                    <Skeleton className="h-5 w-36" />
                    <Skeleton className="h-5 w-36" />
                    <Skeleton className="h-5 w-32" />
                    <Skeleton className="h-5 w-32" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
        {!loadingData && policies.length === 0 && (
          <div className="py-8 text-center text-muted-foreground">
            <p>No policies found.</p>
            <p>Your policies will appear here once created by Staff.</p>
          </div>
        )}

        {policies.length > 0 && (
          <div className="mt-4 space-y-4">
            {policies.map((p) => (
              <Card key={p.id}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold">
                      <a
                        href={`/customer/policies/detail?id=${p.id}`}
                        className="text-primary underline"
                      >
                        {p.policy_number}
                      </a>
                    </h3>
                    <StatusBadge status={p.status} />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>Effective: {p.effective_date}</div>
                    <div>Expires: {p.expiration_date}</div>
                    <div>Premium: {formatCents(p.premium_amount_cents)}</div>
                    <div>Territory: {p.coverage_territory}</div>
                  </div>

                  {(p.status === "DRAFT" || p.status === "PENDING_PAYMENT") && (() => {
                    const effectivePassed = new Date(p.effective_date + "T00:00:00") < new Date(new Date().toDateString());
                    return effectivePassed ? (
                      <Card className="mt-3 border-red-200 bg-red-50">
                        <CardContent className="pt-4">
                          <p className="mb-2 text-sm text-red-800">
                            This policy&apos;s effective date ({p.effective_date}) has passed. Payment is no longer accepted. Please contact staff to re-issue with a new effective date.
                          </p>
                          <Button
                            variant="destructive"
                            onClick={() => handleDecline(p.id)}
                            disabled={decliningId === p.id}
                          >
                            {decliningId === p.id ? "Declining..." : "Decline Policy"}
                          </Button>
                        </CardContent>
                      </Card>
                    ) : (
                      <Card className="mt-3 border-amber-200 bg-amber-50">
                        <CardContent className="pt-4">
                          <p className="mb-2 text-sm">
                            Payment required to activate this policy.
                          </p>
                          <div className="flex gap-2">
                            <Button
                              onClick={() => handlePay(p.id)}
                              disabled={paymentLoading === p.id || decliningId === p.id}
                              className="bg-green-600 hover:bg-green-700"
                            >
                              {paymentLoading === p.id ? "Processing..." : "Pay Now"}
                            </Button>
                            <Button
                              variant="destructive"
                              onClick={() => handleDecline(p.id)}
                              disabled={paymentLoading === p.id || decliningId === p.id}
                            >
                              {decliningId === p.id ? "Declining..." : "Decline"}
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })()}

                  {p.status === "ACTIVE" && (
                    <Card className="mt-3 border-green-200 bg-green-50">
                      <CardContent className="pt-4">
                        <p className="text-sm text-green-800">
                          Policy is active. Coverage is in effect.
                        </p>
                      </CardContent>
                    </Card>
                  )}

                  <div className="mt-3">
                    <Button
                      variant="link"
                      size="sm"
                      onClick={() => loadPayments(p.id)}
                      className="px-0"
                    >
                      View Payments
                    </Button>
                    {payments[p.id] && (
                      <div className="mt-2 space-y-1 text-sm">
                        {payments[p.id].length === 0 ? (
                          <p className="text-muted-foreground">No payments yet.</p>
                        ) : (
                          payments[p.id].map((pay) => (
                            <div
                              key={pay.id}
                              className="flex items-center gap-2 rounded-md border p-2"
                            >
                              <span>{formatCents(pay.amount_cents)}</span>
                              <StatusBadge status={pay.status} />
                              <span className="text-muted-foreground">
                                {new Date(pay.created_at).toLocaleDateString()}
                              </span>
                              {pay.stripe_payment_intent_id.startsWith("SIMULATED") && (
                                <Badge variant="outline">SIMULATED</Badge>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
