import { formatCents, multiplyPriceByQuantity, parseMoneyToCents } from "./decimal.ts";

export type DiscountLine = {
  selling_price: string;
  quantity: string;
  line_total: string;
  line_discount?: string;
};

function discountCents(value: string): bigint {
  if (!/^\d+(\.\d{1,2})?$/.test(value)) {
    throw new Error("Enter a discount amount with at most two decimal places");
  }
  return parseMoneyToCents(value);
}

// Allocate whole cents across lines before tax. Refunds then use paid line totals.
export function applyDiscounts<T extends DiscountLine>(items: T[], saleDiscount = "0") {
  const lines = items.map((item) => {
    const gross = parseMoneyToCents(multiplyPriceByQuantity(item.selling_price, item.quantity));
    const reduction = discountCents(item.line_discount || "0");
    if (reduction >= gross) throw new Error("Line discount must be less than the line amount");
    return { item, gross, net: gross - reduction };
  });
  const subtotal = lines.reduce((sum, line) => sum + line.net, 0n);
  const reduction = discountCents(saleDiscount || "0");
  if (reduction > 0n && reduction >= subtotal) throw new Error("Sale discount must be less than the sale amount");
  let cumulative = 0n;
  let allocated = 0n;
  const discountedItems = lines.map(({ item, net }) => {
    cumulative += net;
    const next = subtotal ? reduction * cumulative / subtotal : 0n;
    const paid = net - (next - allocated);
    allocated = next;
    if (paid <= 0n) throw new Error("Discount must leave at least one cent on every line");
    return { ...item, line_total: formatCents(paid) };
  });
  return {
    items: discountedItems,
    discount_amount: formatCents(lines.reduce((sum, line) => sum + line.gross - line.net, reduction)),
    total: formatCents(subtotal - reduction),
  };
}
