"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const staffLinks = [
  { href: "/staff/brokers", label: "Brokers" },
  { href: "/staff/policies", label: "Policies" },
  { href: "/staff/claims", label: "Claims" },
  { href: "/staff/payments", label: "Payments" },
  { href: "/staff/statements", label: "Statements" },
  { href: "/staff/reconciliation", label: "Reconciliation" },
];

const customerLinks = [
  { href: "/customer/policies", label: "My Policies" },
  { href: "/customer/claims", label: "My Claims" },
];

export default function Nav() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  if (!user) return null;

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  const links = user.role === "STAFF" ? staffLinks : customerLinks;

  return (
    <nav className="flex items-center gap-1 border-b px-4 py-2 text-sm">
      <span className="mr-2 text-base font-bold">Corgi</span>
      {links.map(({ href, label }) => {
        const isActive = pathname === href || pathname.startsWith(href + "/");
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              isActive
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            {label}
          </Link>
        );
      })}
      <span className="ml-auto text-sm text-muted-foreground">
        {user.first_name || user.username} ({user.role})
      </span>
      <Button variant="ghost" size="sm" onClick={handleLogout}>
        Logout
      </Button>
    </nav>
  );
}
