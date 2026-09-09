"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type ClaimRecord, type Policy } from "@/lib/api";
import Nav from "@/components/Nav";
import { formatCents } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";

function ClaimsContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const policyId = searchParams.get("policy_id");

  const [claims, setClaims] = useState<ClaimRecord[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [formPolicyId, setFormPolicyId] = useState(policyId || "");
  const [dateOfLoss, setDateOfLoss] = useState("");
  const [description, setDescription] = useState("");
  const [estimatedAmount, setEstimatedAmount] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "CUSTOMER") {
      router.replace("/login");
    }
  }, [user, loading, router]);

  useEffect(() => {
    if (loading || !user) return;
    let cancelled = false;
    setLoadingData(true);

    Promise.all([
      api.listClaims(policyId ? Number(policyId) : undefined),
      api.listPolicies(),
    ])
      .then(([claimsData, policiesData]) => {
        if (!cancelled) {
          setClaims(claimsData);
          setPolicies(policiesData);
        }
      })
      .catch(() => { if (!cancelled) setError("Failed to load data."); })
      .finally(() => { if (!cancelled) setLoadingData(false); });

    return () => { cancelled = true; };
  }, [loading, user, policyId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const claim = await api.submitClaim({
        policy_id: Number(formPolicyId),
        date_of_loss: dateOfLoss,
        description,
        estimated_amount_cents: estimatedAmount ? Math.round(parseFloat(estimatedAmount) * 100) : undefined,
      });
      setClaims((prev) => [claim, ...prev]);
      setShowForm(false);
      setDateOfLoss("");
      setDescription("");
      setEstimatedAmount("");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to submit claim.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-4xl p-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">My Claims</h1>
          <Button
            onClick={() => setShowForm(!showForm)}
            variant={showForm ? "outline" : "default"}
          >
            {showForm ? "Cancel" : "Submit Claim"}
          </Button>
        </div>

        {error && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {showForm && (
          <Card className="mt-4 mb-4">
            <CardHeader>
              <CardTitle>Submit a New Claim</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="policy">Policy</Label>
                  <select
                    id="policy"
                    value={formPolicyId}
                    onChange={(e) => setFormPolicyId(e.target.value)}
                    required
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    <option value="">Select a policy...</option>
                    {policies.filter((p) => ["ACTIVE", "CANCELLED", "EXPIRED"].includes(p.status)).map((p) => (
                      <option key={p.id} value={p.id}>{p.policy_number} ({p.status})</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="dateOfLoss">Date of Loss</Label>
                  <Input
                    id="dateOfLoss"
                    type="date"
                    value={dateOfLoss}
                    onChange={(e) => setDateOfLoss(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    required
                    rows={3}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="estimatedAmount">Estimated Amount ($)</Label>
                  <Input
                    id="estimatedAmount"
                    type="number"
                    step="0.01"
                    min="0"
                    value={estimatedAmount}
                    onChange={(e) => setEstimatedAmount(e.target.value)}
                    placeholder="Optional"
                  />
                </div>
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Submitting..." : "Submit Claim"}
                </Button>
              </form>
            </CardContent>
          </Card>
        )}

        {loadingData && (
          <div className="mt-4 space-y-3">
            {[1, 2].map((i) => (
              <Card key={i}>
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <Skeleton className="h-6 w-32" />
                    <Skeleton className="h-6 w-20" />
                  </div>
                  <div className="mt-2 space-y-2">
                    <Skeleton className="h-4 w-48" />
                    <Skeleton className="h-4 w-64" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
        {!loadingData && claims.length === 0 && !showForm && (
          <div className="py-8 text-center text-muted-foreground">
            <p>No claims found.</p>
            <p className="mt-1 text-sm">Submit a claim using the button above.</p>
          </div>
        )}

        <div className="mt-4 space-y-3">
          {claims.map((c) => (
            <Card key={c.id}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold">{c.claim_number}</h3>
                  <StatusBadge status={c.status} />
                </div>
                <div className="mt-2 space-y-1 text-sm text-muted-foreground">
                  <div>Date of Loss: {c.date_of_loss}</div>
                  <div>Description: {c.description}</div>
                  {c.estimated_amount_cents && (
                    <div>Estimated Amount: {formatCents(c.estimated_amount_cents)}</div>
                  )}
                  <div>Reported: {new Date(c.reported_at).toLocaleDateString()}</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
    </>
  );
}

export default function CustomerClaimsPage() {
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <ClaimsContent />
    </Suspense>
  );
}
