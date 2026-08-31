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
