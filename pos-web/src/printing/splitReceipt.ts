/** Frozen receipt allocation disclosure; never infers a payment from a scalar total. */
export type SplitAccounting = {
  version: "split-receipt-v2";
  scope: "recorded accounting only";
  provider_confirmed: false;
  original_sale_id: string | null;
  base_code: string;
  legs: Array<{
    id: string; kind: "cash_payment" | "unpaid_credit" | "cash_refund" | "debt_reduction";
    method: "cash" | "credit"; currency_code: string; currency_places: number;
    applied_base: string; applied_original: string; tendered_original: string | null;
    change_original: string | null; rate: string; currency_config_version: number;
  }>;
};

function units(value: string, places: number): bigint {
  if (!Number.isInteger(places) || places < 0 || places > 4 || !/^\d{1,18}(\.\d{1,10})?$/.test(value)) throw Error("Invalid receipt amount");
  const [whole, fraction = ""] = value.split(".");
  if (/[1-9]/.test(fraction.slice(places))) throw Error("Invalid receipt precision");
  return BigInt(whole) * 10n ** BigInt(places) + BigInt(fraction.slice(0, places).padEnd(places, "0") || "0");
}
function formatted(value: string, places: number, code: string): string {
  const n = units(value, places), divisor = 10n ** BigInt(places);
  return `${n / divisor}${places ? `.${(n % divisor).toString().padStart(places, "0")}` : ""} ${code}`;
}

export function splitPaymentRows(accounting: SplitAccounting | null | undefined, total: string, method: string): Array<[string, string]> {
  try {
    if (!accounting || accounting.version !== "split-receipt-v2" || accounting.provider_confirmed !== false || accounting.scope !== "recorded accounting only" || !/^[A-Z0-9]{3,8}$/.test(accounting.base_code)) throw Error("Missing original receipt evidence");
    const refund = method === "split_refund", legs = accounting.legs;
    if (!["split", "split_refund"].includes(method) || !legs.length || legs.length > 20 || (!refund && legs.length < 2) || new Set(legs.map(r => r.id)).size !== legs.length) throw Error("Invalid receipt allocations");
    if (refund !== total.startsWith("-") || legs.reduce((sum, r) => sum + units(r.applied_base, 2), 0n) !== units(total.replace(/^-/, ""), 2)) throw Error("Receipt allocation sum differs");
    const rows: Array<[string, string]> = [["Payment", refund ? "SPLIT REFUND" : "SPLIT"], ["Scope", "Recorded accounting only"]];
    for (const leg of legs) {
      if (!/^[A-Z0-9]{3,8}$/.test(leg.currency_code) || !/^\d{1,10}(\.\d{1,10})?$/.test(leg.rate) || /^0(?:\.0+)?$/.test(leg.rate) || !Number.isInteger(leg.currency_config_version) || leg.currency_config_version < 1 || units(leg.applied_base, 2) <= 0n || units(leg.applied_original, leg.currency_places) <= 0n) throw Error("Invalid original leg");
      const cash = leg.method === "cash";
      if (leg.kind !== (cash ? refund ? "cash_refund" : "cash_payment" : refund ? "debt_reduction" : "unpaid_credit")) throw Error("Invalid original method");
      if (!cash && (leg.method !== "credit" || leg.currency_code !== accounting.base_code || units(leg.applied_original, 2) !== units(leg.applied_base, 2))) throw Error("Invalid debt allocation");
      rows.push([cash ? refund ? "Cash refund" : "Cash payment" : refund ? "Debt reduction" : "Original unpaid credit", formatted(leg.applied_original, leg.currency_places, leg.currency_code)]);
      rows.push([refund ? "Base reversal" : "Applied base", formatted(leg.applied_base, 2, accounting.base_code)]);
      if (cash && !refund) {
        if (leg.tendered_original == null || leg.change_original == null || units(leg.tendered_original, leg.currency_places) - units(leg.change_original, leg.currency_places) !== units(leg.applied_original, leg.currency_places)) throw Error("Invalid original cash change");
        rows.push(["Tendered", formatted(leg.tendered_original, leg.currency_places, leg.currency_code)], ["Change", formatted(leg.change_original, leg.currency_places, leg.currency_code)]);
      }
      if (cash && leg.currency_code !== accounting.base_code) rows.push([`Rate 1 ${accounting.base_code}`, `${leg.rate} ${leg.currency_code}`]);
    }
    return rows;
  } catch {
    return [["Split detail", "UNAVAILABLE"], ["Action", "Review original receipt"]];
  }
}
