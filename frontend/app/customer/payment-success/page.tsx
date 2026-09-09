"use client";

import Link from "next/link";
import Nav from "@/components/Nav";

export default function PaymentSuccessPage() {
  return (
    <>
      <Nav />
      <main style={{ padding: "2rem", fontFamily: "system-ui, sans-serif", maxWidth: 600, margin: "0 auto", textAlign: "center" }}>
        <div style={{ padding: "2rem", backgroundColor: "#d4edda", borderRadius: 8, marginBottom: "1.5rem" }}>
          <h1 style={{ color: "#155724" }}>Payment Successful</h1>
          <p style={{ color: "#155724" }}>
            Your premium payment has been received. Your policy is now being activated.
          </p>
          <p style={{ fontSize: "0.85rem", color: "#666" }}>
            It may take a moment for the webhook to process. Refresh the policies page to see the updated status.
          </p>
        </div>
        <Link href="/customer/policies" style={{ color: "#0275d8" }}>
          Back to My Policies
        </Link>
      </main>
    </>
  );
}
