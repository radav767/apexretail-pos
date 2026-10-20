import { parseQuantityToMillis, formatMillis } from "../decimal";

export function accumulatedWeightedQuantity(current: string, added: string, stock: string): string {
  const addition = parseQuantityToMillis(added);
  const total = parseQuantityToMillis(current) + addition;
  if (addition <= 0n || total > parseQuantityToMillis(stock)) throw new Error("Combined quantity exceeds available stock or is invalid");
  return formatMillis(total, false);
}

export type PriceLevel = { name: string; price: string; minimum_quantity: string; active?: boolean };
/** Select a configured price; monetary arithmetic stays in existing helpers. */
export function checkoutPrice(levels: PriceLevel[] | undefined, customerLevel: string | null | undefined, quantity: string, base: string): string {
  const name = customerLevel?.trim().toLowerCase();
  if (!name) return base;
  return (levels || []).filter(level => level.active !== false && level.name.trim().toLowerCase() === name
    && Number(level.minimum_quantity) <= Number(quantity))
    .sort((a, b) => Number(b.minimum_quantity) - Number(a.minimum_quantity))[0]?.price ?? base;
}
