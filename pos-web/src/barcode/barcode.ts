export const SUPPORTED_BARCODE_FORMATS = [
  "ean_13",
  "ean_8",
  "upc_a",
  "upc_e",
  "code_128",
  "code_39",
] as const;

export type BarcodeProduct = {
  id: string;
  name: string;
  barcode?: string | null;
  active?: boolean;
};

export function normalizeBarcode(value: string): string {
  return value.trim();
}

export type BarcodeResolution<T> =
  | { status: "found"; barcode: string; product: T }
  | { status: "not_found"; barcode: string }
  | { status: "ambiguous"; barcode: string };

export function resolveBarcodeProduct<T extends BarcodeProduct>(
  products: readonly T[],
  rawBarcode: string,
): BarcodeResolution<T> {
  const barcode = normalizeBarcode(rawBarcode);
  const matches = products.filter(
    (product) =>
      product.active !== false &&
      product.barcode != null &&
      normalizeBarcode(product.barcode) === barcode,
  );

  if (matches.length === 1) {
    return { status: "found", barcode, product: matches[0] };
  }
  if (matches.length > 1) {
    return { status: "ambiguous", barcode };
  }
  return { status: "not_found", barcode };
}

export function createDuplicateScanGate(cooldownMs = 1_000) {
  let lastValue = "";
  let lastAcceptedAt = Number.NEGATIVE_INFINITY;

  return (rawValue: string, now = Date.now()): string | null => {
    const value = normalizeBarcode(rawValue);
    if (!value) return null;
    if (value === lastValue && now - lastAcceptedAt < cooldownMs) {
      return null;
    }
    lastValue = value;
    lastAcceptedAt = now;
    return value;
  };
}
