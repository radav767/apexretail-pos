export type SalesHistoryActor = {
  role?: string | null;
  permissions?: Record<string, boolean>;
};

export type SalesHistorySale = {
  original_sale_id?: string | null;
  status?: string | null;
};

const PRIVILEGED_ROLES = new Set([
  "owner",
  "administrator",
  "admin",
]);

export function isPrivilegedSalesActor(
  actor: SalesHistoryActor | null,
): boolean {
  return PRIVILEGED_ROLES.has(
    String(actor?.role || "").toLowerCase(),
  );
}

export function canViewSaleReceipt(
  actor: SalesHistoryActor | null,
): boolean {
  return (
    isPrivilegedSalesActor(actor) ||
    actor?.permissions?.sales === true
  );
}

export function canRefundSale(
  actor: SalesHistoryActor | null,
): boolean {
  return (
    isPrivilegedSalesActor(actor) ||
    actor?.permissions?.refunds === true
  );
}

export function isRefundableSale(
  sale: SalesHistorySale,
): boolean {
  return (
    !sale.original_sale_id &&
    ["completed", "partially_refunded"].includes(
      String(sale.status || "completed"),
    )
  );
}

export function saleStatusLabel(
  sale: SalesHistorySale,
): string {
  if (sale.original_sale_id) {
    return "Refund transaction";
  }

  const labels: Record<string, string> = {
    completed: "Completed",
    partially_refunded: "Partially refunded",
    refunded: "Fully refunded",
  };

  const status = String(sale.status || "completed");
  return labels[status] || status.replaceAll("_", " ");
}

export function validateRefundQuantity(
  requestedValue: string,
  remainingValue: string | number,
): string | null {
  const requested = Number(requestedValue);
  const remaining = Number(remainingValue);

  if (!Number.isFinite(requested) || requested <= 0) {
    return "Refund quantity must be greater than zero.";
  }

  if (!Number.isFinite(remaining) || requested > remaining) {
    return "Refund quantity exceeds the remaining refundable quantity.";
  }

  return null;
}
