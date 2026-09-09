"use client";

import Link from "next/link";
import Nav from "@/components/Nav";

export default function PaymentCancelPage() {
  return (
    <>
      <Nav />
      <main style={{ padding: "2rem", fontFamily: "system-ui, sans-serif", maxWidth: 600, margin: "0 auto", textAlign: "center" }}>
        <div style={{ padding: "2rem", backgroundColor: "#fff3cd", borderRadius: 8, marginBottom: "1.5rem" }}>
          <h1 style={{ color: "#856404" }}>Payment Cancelled</h1>
          <p style={{ color: "#856404" }}>
            Your payment was not completed. You can try again from the policies page.
          </p>
        </div>
        <Link href="/customer/policies" style={{ color: "#0275d8" }}>
          Back to My Policies
        </Link>
      </main>
    </>
  );
}
