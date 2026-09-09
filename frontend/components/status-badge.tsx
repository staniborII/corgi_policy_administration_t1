import { Badge } from "@/components/ui/badge";

const STATUS_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  ACTIVE: "default",
  APPLIED: "default",
  APPROVED: "default",
  SUCCEEDED: "default",
  VERIFIED: "default",
  COMPLETED: "default",
  PAID: "default",
  RESOLVED: "default",
  SETTLED: "default",

  DRAFT: "secondary",
  OPEN: "secondary",
  RUNNING: "secondary",
  PROCESSING: "secondary",

  PENDING: "outline",
  PENDING_PAYMENT: "outline",
  PENDING_APPROVAL: "outline",
  PENDING_CUSTOMER_APPROVAL: "outline",
  UNDER_REVIEW: "outline",
  RESERVED: "outline",
  PAYMENT_PENDING: "outline",
  PARTIALLY_PAID: "outline",
  ACKNOWLEDGED: "outline",

  CANCELLED: "destructive",
  FAILED: "destructive",
  RETURNED: "destructive",
  EXPIRED: "destructive",
  REVERSED: "destructive",
  CLOSED: "destructive",
  MISSING_IN_LEDGER: "destructive",
  MISSING_IN_PROVIDER: "destructive",
  AMOUNT_MISMATCH: "destructive",
  STATUS_MISMATCH: "destructive",
  DUPLICATE_MATCH: "destructive",
  STALE_UNRESOLVED: "destructive",
};

export function StatusBadge({ status }: { status: string }) {
  const variant = STATUS_VARIANTS[status] ?? "secondary";
  return (
    <Badge variant={variant}>
      {status.replace(/_/g, " ")}
    </Badge>
  );
}
