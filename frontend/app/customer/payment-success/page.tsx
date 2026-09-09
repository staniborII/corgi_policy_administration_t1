"use client";

import Link from "next/link";
import Nav from "@/components/Nav";
import { Card, CardContent } from "@/components/ui/card";

export default function PaymentSuccessPage() {
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-4xl p-6">
        <Card className="border-green-200 bg-green-50 text-center">
          <CardContent className="pt-6">
            <h1 className="text-2xl font-bold text-green-800">Payment Successful</h1>
            <p className="mt-2 text-green-800">
              Your premium payment has been received. Your policy is now being activated.
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              It may take a moment for the webhook to process. Refresh the policies page to see the updated status.
            </p>
          </CardContent>
        </Card>
        <div className="mt-6 text-center">
          <Link href="/customer/policies" className="text-primary hover:underline">
            Back to My Policies
          </Link>
        </div>
      </main>
    </>
  );
}
