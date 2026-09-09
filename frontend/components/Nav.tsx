"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";

export default function Nav() {
  const { user, logout } = useAuth();
  const router = useRouter();

  if (!user) return null;

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <nav style={{
      display: "flex", gap: "1rem", alignItems: "center",
      padding: "0.75rem 1.5rem",
      borderBottom: "1px solid #ddd",
      fontFamily: "system-ui, sans-serif",
      fontSize: "0.9rem",
    }}>
      <strong>Corgi</strong>
      {user.role === "STAFF" && (
        <>
          <Link href="/staff/brokers">Brokers</Link>
          <Link href="/staff/policies">Policies</Link>
          <Link href="/staff/claims">Claims</Link>
          <Link href="/staff/payments">Payments</Link>
          <Link href="/staff/statements">Statements</Link>
        </>
      )}
      {user.role === "CUSTOMER" && (
        <>
          <Link href="/customer/policies">My Policies</Link>
          <Link href="/customer/claims">My Claims</Link>
        </>
      )}
      <span style={{ marginLeft: "auto" }}>
        {user.first_name || user.username} ({user.role})
      </span>
      <button onClick={handleLogout} style={{ cursor: "pointer" }}>Logout</button>
    </nav>
  );
}
