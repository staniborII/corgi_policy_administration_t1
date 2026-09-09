"use client";

import Link from "next/link";
import Nav from "@/components/Nav";
import { Card, CardContent } from "@/components/ui/card";

export default function PaymentCancelPage() {
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-4xl p-6">
        <Card className="border-amber-200 bg-amber-50 text-center">
          <CardContent className="pt-6">
            <h1 className="text-2xl font-bold text-amber-800">Payment Cancelled</h1>
            <p className="mt-2 text-amber-800">
              Your payment was not completed. You can try again from the policies page.
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
