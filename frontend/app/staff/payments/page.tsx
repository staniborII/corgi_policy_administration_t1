"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type Policy, type PaymentRecord } from "@/lib/api";
import Nav from "@/components/Nav";
import { formatCents } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function StaffPaymentsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [payments, setPayments] = useState<Record<number, PaymentRecord[]>>({});
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [expandedPolicy, setExpandedPolicy] = useState<number | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "STAFF") {
      router.replace("/login");
    }
  }, [user, loading, router]);

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

  async function togglePayments(policyId: number) {
    if (expandedPolicy === policyId) {
      setExpandedPolicy(null);
      return;
    }
    setExpandedPolicy(policyId);
    if (!payments[policyId]) {
      try {
        const data = await api.listPolicyPayments(policyId);
        setPayments((prev) => ({ ...prev, [policyId]: data }));
      } catch {
        /* ignore */
      }
    }
  }

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-5xl p-6">
        <h1 className="text-2xl font-bold mb-4">Payment Management</h1>

        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {loadingData && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        )}
        {!loadingData && policies.length === 0 && (
          <div className="py-8 text-center text-muted-foreground">
            <p>No policies found.</p>
            <p className="mt-1 text-sm">Policies and their payments will appear here once created.</p>
          </div>
        )}

        {policies.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Policy #</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Premium</TableHead>
                <TableHead>Territory</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {policies.map((p) => (
                <>
                  <TableRow key={p.id}>
                    <TableCell>{p.policy_number}</TableCell>
                    <TableCell><StatusBadge status={p.status} /></TableCell>
                    <TableCell>{formatCents(p.premium_amount_cents)}</TableCell>
                    <TableCell>{p.coverage_territory}</TableCell>
                    <TableCell>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => togglePayments(p.id)}
                      >
                        {expandedPolicy === p.id ? "Hide Payments" : "View Payments"}
                      </Button>
                    </TableCell>
                  </TableRow>
                  {expandedPolicy === p.id && payments[p.id] && (
                    <TableRow key={`${p.id}-payments`}>
                      <TableCell colSpan={5} className="bg-muted/50 p-4">
                        {payments[p.id].length === 0 ? (
                          <p className="text-muted-foreground text-sm my-1">No payments recorded.</p>
                        ) : (
                          <div className="space-y-2">
                            {payments[p.id].map((pay) => (
                              <Card key={pay.id}>
                                <CardContent className="p-3">
                                  <div className="flex items-center justify-between">
                                    <span>
                                      <strong>Payment #{pay.id}</strong> &mdash; {formatCents(pay.amount_cents)}
                                    </span>
                                    <StatusBadge status={pay.status} />
                                  </div>
                                  {pay.charges_snapshot && (
                                    <div className="mt-2 text-sm text-muted-foreground">
                                      <span>Premium: {formatCents(pay.charges_snapshot.premium_cents as number)}</span>
                                      {" | "}
                                      <span>Tax: {formatCents(pay.charges_snapshot.total_tax_cents as number)}</span>
                                      {" | "}
                                      <span>Fees: {formatCents(pay.charges_snapshot.total_fees_cents as number)}</span>
                                      {" | "}
                                      <strong>Total: {formatCents(pay.charges_snapshot.total_cents as number)}</strong>
                                    </div>
                                  )}
                                  <div className="mt-1 text-xs text-muted-foreground">
                                    {pay.stripe_payment_intent_id && (
                                      <span>PI: {pay.stripe_payment_intent_id}</span>
                                    )}
                                    {pay.stripe_payment_intent_id && pay.stripe_payment_intent_id.startsWith("SIMULATED") && (
                                      <span className="ml-2 font-bold text-yellow-600">SIMULATED</span>
                                    )}
                                  </div>
                                </CardContent>
                              </Card>
                            ))}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  )}
                </>
              ))}
            </TableBody>
          </Table>
        )}
      </main>
    </>
  );
}
