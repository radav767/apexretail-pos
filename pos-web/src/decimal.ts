const QTY_SCALE = 1000n;
const MONEY_SCALE = 100n;

function parseFixed(
  value: string | number,
  scale: bigint,
): bigint {
  const raw = String(value ?? "0").trim();
  if (!raw) {
    return 0n;
  }
  const negative = raw.startsWith("-");
  const normalized = negative ? raw.slice(1) : raw;
  const [wholePart, fractionPart = ""] = normalized.split(".");
  const digits = String(scale).length - 1;
  const fraction = `${fractionPart}${"0".repeat(digits)}`.slice(0, digits);
  const combined = `${wholePart || "0"}${fraction}`.replace(/^0+(?=\d)/, "");
  const result = BigInt(combined || "0");
  return negative ? -result : result;
}

function formatFixed(
  value: bigint,
  scale: bigint,
  digits: number,
  trim = false,
): string {
  const negative = value < 0n;
  const absolute = negative ? -value : value;
  const whole = absolute / scale;
  const fraction = String(absolute % scale).padStart(digits, "0");
  const result = `${negative ? "-" : ""}${whole}.${fraction}`;
  return trim ? result.replace(/\.?0+$/, "") : result;
}

function divideRounded(
  numerator: bigint,
  denominator: bigint,
): bigint {
  if (denominator === 0n) {
    return 0n;
  }
  const negative = (numerator < 0n) !== (denominator < 0n);
  const absoluteNumerator = numerator < 0n ? -numerator : numerator;
  const absoluteDenominator = denominator < 0n ? -denominator : denominator;
  const quotient = absoluteNumerator / absoluteDenominator;
  const remainder = absoluteNumerator % absoluteDenominator;
  const rounded =
    remainder * 2n >= absoluteDenominator
      ? quotient + 1n
      : quotient;
  return negative ? -rounded : rounded;
}

function powerOfTen(digits: number): bigint {
  if (!Number.isInteger(digits) || digits < 0 || digits > 24) {
    throw new Error("Unsupported currency precision");
  }
  return 10n ** BigInt(digits);
}

function parseCurrencyUnits(value: string, decimalPlaces: number): bigint {
  if (!Number.isInteger(decimalPlaces) || decimalPlaces < 0 || decimalPlaces > 4) {
    throw new Error("Unsupported currency precision");
  }
  const normalized = value.trim();
  if (!/^-?\d+(?:\.\d*)?$/.test(normalized)) {
    throw new Error("Enter a valid amount");
  }
  const negative = normalized.startsWith("-");
  const unsigned = negative ? normalized.slice(1) : normalized;
  const [whole, fraction = ""] = unsigned.split(".");
  if (fraction.length > decimalPlaces) {
    throw new Error("Amount exceeds the currency decimal precision");
  }
  const units = BigInt(whole) * powerOfTen(decimalPlaces)
    + BigInt((fraction + "0".repeat(decimalPlaces)).slice(0, decimalPlaces) || "0");
  return negative ? -units : units;
}

function formatCurrencyUnits(value: bigint, decimalPlaces: number): string {
  if (!Number.isInteger(decimalPlaces) || decimalPlaces < 0 || decimalPlaces > 4) {
    throw new Error("Unsupported currency precision");
  }
  const scale = powerOfTen(decimalPlaces);
  const negative = value < 0n;
  const absolute = negative ? -value : value;
  if (decimalPlaces === 0) return `${negative ? "-" : ""}${absolute}`;
  return `${negative ? "-" : ""}${absolute / scale}.${String(absolute % scale).padStart(decimalPlaces, "0")}`;
}

/** Convert a base-currency amount using foreign units per one base unit. */
export function convertBaseToForeign(
  baseAmount: string,
  baseDecimalPlaces: number,
  rate: string,
  foreignDecimalPlaces: number,
): string {
  if (!/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(rate.trim())) {
    throw new Error("Exchange rate is invalid");
  }
  const rateText = rate.trim();
  const rateFractionDigits = rateText.split(".")[1]?.length || 0;
  if (rateFractionDigits > 10 || BigInt(rateText.replace(".", "")) <= 0n) {
    throw new Error("Exchange rate is invalid");
  }
  const baseUnits = parseCurrencyUnits(baseAmount, baseDecimalPlaces);
  const rateNumerator = BigInt(rateText.replace(".", ""));
  const numerator = baseUnits * rateNumerator * powerOfTen(foreignDecimalPlaces);
  const denominator = powerOfTen(baseDecimalPlaces) * powerOfTen(rateFractionDigits);
  return formatCurrencyUnits(divideRounded(numerator, denominator), foreignDecimalPlaces);
}

export function subtractCurrencyAmounts(
  left: string,
  right: string,
  decimalPlaces: number,
): string {
  return formatCurrencyUnits(
    parseCurrencyUnits(left, decimalPlaces) - parseCurrencyUnits(right, decimalPlaces),
    decimalPlaces,
  );
}

export function isCurrencyAmountAtLeast(
  left: string,
  right: string,
  decimalPlaces: number,
): boolean {
  return parseCurrencyUnits(left, decimalPlaces) >= parseCurrencyUnits(right, decimalPlaces);
}

export function parseMoneyToCents(value: string | number): bigint {
  return parseFixed(value, MONEY_SCALE);
}

export function formatCents(value: bigint): string {
  return formatFixed(value, MONEY_SCALE, 2, false);
}

export function parseQuantityToMillis(value: string | number): bigint {
  return parseFixed(value, QTY_SCALE);
}

export function formatMillis(value: bigint, trim = true): string {
  return formatFixed(value, QTY_SCALE, 3, trim);
}

export function multiplyPriceByQuantity(
  unitPrice: string | number,
  quantity: string | number,
): string {
  const cents = parseMoneyToCents(unitPrice);
  const millis = parseQuantityToMillis(quantity);
  return formatCents(divideRounded(cents * millis, QTY_SCALE));
}

export function quantityFromAmount(
  amount: string | number,
  unitPrice: string | number,
): string {
  const cents = parseMoneyToCents(amount);
  const unitPriceCents = parseMoneyToCents(unitPrice);
  return formatMillis(
    divideRounded(cents * QTY_SCALE, unitPriceCents),
    false,
  );
}

export function subtractQuantities(
  left: string | number,
  right: string | number,
): string {
  return formatMillis(
    parseQuantityToMillis(left) - parseQuantityToMillis(right),
    false,
  );
}
