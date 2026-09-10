"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import { useRealtimeRefresh } from "@/lib/useRealtimeRefresh";
import { api, type PaymentRecord } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type VerifyState = "verifying" | "success" | "pending" | "error";

export default function PaymentSuccessPage() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session_id");
  const [state, setState] = useState<VerifyState>("verifying");
  const [payment, setPayment] = useState<PaymentRecord | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const verifyStarted = useRef(false);

  useEffect(() => {
    if (!sessionId) {
      setState("error");
      setErrorMsg("No session ID found in URL.");
      return;
    }

    if (verifyStarted.current) return;
    verifyStarted.current = true;

    let cancelled = false;
    let attempts = 0;
    const maxAttempts = 5;

    async function verify() {
      try {
        const result = await api.verifyCheckoutSession(sessionId!);
        if (cancelled) return;

        setPayment(result);
        if (result.status === "SUCCEEDED") {
          setState("success");
        } else if (result.status === "PENDING" && attempts < maxAttempts) {
          attempts++;
          setTimeout(verify, 2000);
        } else {
          setState("pending");
        }
      } catch {
        if (cancelled) return;
        setState("error");
        setErrorMsg("Could not verify payment status. Please check your policies page.");
      }
    }

    verify();
    return () => { cancelled = true; };
  }, [sessionId]);

  const handlePaymentEvent = useCallback(() => {
    if (!sessionId || state === "success") return;
    api.verifyCheckoutSession(sessionId).then((result) => {
      setPayment(result);
      if (result.status === "SUCCEEDED") setState("success");
    }).catch(() => {});
  }, [sessionId, state]);

  useRealtimeRefresh("payment.", handlePaymentEvent);

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-4xl p-6">
        {state === "verifying" && (
          <Card className="border-blue-200 bg-blue-50 text-center">
            <CardContent className="pt-6 space-y-3">
              <h1 className="text-2xl font-bold text-blue-800">Verifying Payment...</h1>
              <p className="text-blue-700">
                Confirming your payment with Stripe. This should only take a moment.
              </p>
              <Skeleton className="mx-auto h-4 w-48" />
            </CardContent>
          </Card>
        )}

        {state === "success" && (
          <Card className="border-green-200 bg-green-50 text-center">
            <CardContent className="pt-6">
              <h1 className="text-2xl font-bold text-green-800">Payment Successful</h1>
              <p className="mt-2 text-green-800">
                Your premium payment has been received and your policy is now active.
              </p>
            </CardContent>
          </Card>
        )}

        {state === "pending" && (
          <Card className="border-amber-200 bg-amber-50 text-center">
            <CardContent className="pt-6">
              <h1 className="text-2xl font-bold text-amber-800">Payment Processing</h1>
              <p className="mt-2 text-amber-700">
                Your payment is still being processed. It may take a moment to complete.
              </p>
              <Button
                className="mt-4"
                onClick={() => {
                  setState("verifying");
                  api.verifyCheckoutSession(sessionId!).then((result) => {
                    setPayment(result);
                    setState(result.status === "SUCCEEDED" ? "success" : "pending");
                  }).catch(() => {
                    setState("error");
                    setErrorMsg("Could not verify payment status.");
                  });
                }}
              >
                Check Again
              </Button>
            </CardContent>
          </Card>
        )}

        {state === "error" && (
          <Card className="border-red-200 bg-red-50 text-center">
            <CardContent className="pt-6">
              <h1 className="text-2xl font-bold text-red-800">Verification Issue</h1>
              <p className="mt-2 text-red-700">{errorMsg}</p>
            </CardContent>
          </Card>
        )}

        <div className="mt-6 text-center">
          <Link href="/customer/policies" className="text-primary hover:underline">
            Back to My Policies
          </Link>
        </div>
      </main>
    </>
  );
}
