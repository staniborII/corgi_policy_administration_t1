"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useRealtimeRefresh } from "@/lib/useRealtimeRefresh";
import { api, type ClaimRecord } from "@/lib/api";
import Nav from "@/components/Nav";
import { formatCents } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
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

export default function StaffClaimsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [claims, setClaims] = useState<ClaimRecord[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "STAFF") {
      router.replace("/login");
    }
  }, [user, loading, router]);

  const refreshClaims = useCallback(() => {
    api.listClaims().then(setClaims).catch(() => {});
  }, []);

  useEffect(() => {
    if (loading || !user) return;
    let cancelled = false;
    setLoadingData(true);
    api.listClaims()
      .then((data) => { if (!cancelled) setClaims(data); })
      .catch(() => { if (!cancelled) setError("Failed to load claims."); })
      .finally(() => { if (!cancelled) setLoadingData(false); });
    return () => { cancelled = true; };
  }, [loading, user]);

  useRealtimeRefresh("claim.", refreshClaims);

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-5xl p-6">
        <h1 className="text-2xl font-bold">Claims Management</h1>

        {error && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {loadingData && (
          <div className="mt-4 space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        )}
        {!loadingData && claims.length === 0 && (
          <div className="py-8 text-center text-muted-foreground">
            <p>No claims found.</p>
            <p className="mt-1 text-sm">Claims will appear here once submitted.</p>
          </div>
        )}

        {claims.length > 0 && (
          <Table className="mt-4 text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>Claim #</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Date of Loss</TableHead>
                <TableHead>Estimated</TableHead>
                <TableHead>Reported</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {claims.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>{c.claim_number}</TableCell>
                  <TableCell><StatusBadge status={c.status} /></TableCell>
                  <TableCell>{c.date_of_loss}</TableCell>
                  <TableCell>
                    {c.estimated_amount_cents ? formatCents(c.estimated_amount_cents) : "—"}
                  </TableCell>
                  <TableCell>{new Date(c.reported_at).toLocaleDateString()}</TableCell>
                  <TableCell>
                    <a
                      href={`/staff/claims/detail?id=${c.id}`}
                      className="text-primary underline"
                    >
                      Manage
                    </a>
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
