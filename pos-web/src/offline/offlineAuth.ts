import { Network } from "@capacitor/network";

const STORAGE_KEY = "apexpos_offline_cashiers_v1";

export type CachedOfflineCashier = {
  company_id: string;
  branch_id: string;
  employee_id: string;
  name: string;
  role: string;
  permissions: Record<string, boolean>;
  access_token?: string;
  pin_hash: string;
  updated_at: string;
};

function readRecords(): CachedOfflineCashier[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);

    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);

    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeRecords(records: CachedOfflineCashier[]) {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(records),
  );
}

async function hashPin(pin: string): Promise<string> {
  const value = `ApexRetail-POS:${pin}`;

  if (
    globalThis.crypto?.subtle &&
    typeof TextEncoder !== "undefined"
  ) {
    const encoded = new TextEncoder().encode(value);

    const digest = await globalThis.crypto.subtle.digest(
      "SHA-256",
      encoded,
    );

    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  }

  // Fallback for older Android WebViews.
  let hash = 2166136261;

  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }

  return `fallback-${(hash >>> 0).toString(16)}`;
}

export async function isDeviceOnline(): Promise<boolean> {
  try {
    const status = await Network.getStatus();
    return Boolean(status.connected);
  } catch {
    return navigator.onLine;
  }
}

export async function cacheOfflineCashier(
  companyId: string,
  branchId: string,
  pin: string,
  employee: {
    id: string;
    name?: string;
    role?: string;
    branch_id?: string;
    permissions?: Record<string, boolean>;
    access_token?: string;
  },
): Promise<void> {
  const normalizedPin = pin.trim();

  if (!/^\d{4}$/.test(normalizedPin)) {
    return;
  }

  if (!companyId || !branchId || !employee.id) {
    return;
  }

  const pinHash = await hashPin(normalizedPin);

  const record: CachedOfflineCashier = {
    company_id: companyId,
    branch_id: employee.branch_id || branchId,
    employee_id: employee.id,
    name: employee.name || "Employee",
    role: employee.role || "cashier",
    permissions: employee.permissions || {},
    access_token: employee.access_token || "",
    pin_hash: pinHash,
    updated_at: new Date().toISOString(),
  };

  const existing = readRecords().filter(
    (item) =>
      !(
        item.company_id === companyId &&
        item.branch_id === record.branch_id &&
        item.employee_id === record.employee_id
      ),
  );

  existing.push(record);

  writeRecords(existing);
}

export async function authenticateOfflineCashier(
  companyId: string,
  branchId: string,
  pin: string,
): Promise<CachedOfflineCashier | null> {
  const normalizedPin = pin.trim();

  if (
    !companyId ||
    !branchId ||
    !/^\d{4}$/.test(normalizedPin)
  ) {
    return null;
  }

  const pinHash = await hashPin(normalizedPin);

  const record = readRecords().find(
    (item) =>
      item.company_id === companyId &&
      item.branch_id === branchId &&
      item.pin_hash === pinHash,
  );

  return record || null;
}
