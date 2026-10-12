export function normalizePositiveDecimal(value: string): string | null {
  const trimmed = value.trim();
  if (!/^\d+(?:\.\d+)?$/.test(trimmed)) return null;
  const [whole, fraction = ""] = trimmed.split(".");
  const normalizedWhole = whole.replace(/^0+(?=\d)/, "") || "0";
  return fraction ? `${normalizedWhole}.${fraction}` : normalizedWhole;
}

export function positiveRateError(value: string): string | null {
  const normalized = normalizePositiveDecimal(value);
  if (normalized === null) return "Enter a valid decimal exchange rate.";
  if (/^0(?:\.0+)?$/.test(normalized)) return "Exchange rate must be greater than zero.";
  const fraction = normalized.split(".")[1] || "";
  if (fraction.length > 10) return "Exchange rate supports at most 10 decimal places.";
  const digits = normalized.replace(".", "").replace(/^0+/, "");
  if (digits.length > 20) return "Exchange rate supports at most 20 significant digits.";
  return null;
}

export function multiplyDecimalStrings(left: string, right: string, decimalPlaces: number): string {
  const a = normalizePositiveDecimal(left);
  const b = normalizePositiveDecimal(right);
  if (a === null || b === null) return "—";
  const parts = (value: string) => {
    const [whole, fraction = ""] = value.split(".");
    return { integer: BigInt(`${whole}${fraction}`), scale: fraction.length };
  };
  const lhs = parts(a);
  const rhs = parts(b);
  let product = lhs.integer * rhs.integer;
  const scale = lhs.scale + rhs.scale;
  if (scale > decimalPlaces) {
    const divisor = 10n ** BigInt(scale - decimalPlaces);
    product = (product + divisor / 2n) / divisor;
  } else if (scale < decimalPlaces) {
    product *= 10n ** BigInt(decimalPlaces - scale);
  }
  const digits = product.toString().padStart(decimalPlaces + 1, "0");
  if (decimalPlaces === 0) return digits;
  return `${digits.slice(0, -decimalPlaces)}.${digits.slice(-decimalPlaces)}`;
}
