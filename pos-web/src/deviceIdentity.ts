export type DeviceIdentityStorage = Pick<
  Storage,
  "getItem" | "setItem" | "removeItem" | "clear"
>;

export type PinLoginDeviceIdentity = {
  device_id?: string;
  device_key: string;
  session_token?: string;
};

const DEVICE_KEY = "device_key";
const DEVICE_ID = "device_id";
const DEVICE_COMPANY_ID = "device_company_id";
const DEVICE_ASSIGNMENT_KEYS = [
  "shop_id",
  "shop_name",
  "branch_id",
  "branch_name",
  "pos_name",
  "pos_number",
  "shop_address_snapshot",
] as const;

function storageOrDefault(storage?: DeviceIdentityStorage) {
  return storage || localStorage;
}

export function getOrCreateDeviceKey(
  companyId?: string,
  suppliedStorage?: DeviceIdentityStorage,
): string {
  const storage = storageOrDefault(suppliedStorage);
  const boundCompanyId = storage.getItem(DEVICE_COMPANY_ID);

  if (companyId && boundCompanyId && boundCompanyId !== companyId) {
    storage.removeItem(DEVICE_KEY);
    storage.removeItem(DEVICE_ID);
  }

  const existing = storage.getItem(DEVICE_KEY);
  if (existing) {
    if (companyId) storage.setItem(DEVICE_COMPANY_ID, companyId);
    return existing;
  }

  const generated = globalThis.crypto?.randomUUID?.()
    || `web-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  storage.setItem(DEVICE_KEY, generated);
  if (companyId) storage.setItem(DEVICE_COMPANY_ID, companyId);
  return generated;
}

export function rememberDeviceIdentity(
  companyId: string,
  deviceKey: string,
  deviceId?: string,
  suppliedStorage?: DeviceIdentityStorage,
) {
  const storage = storageOrDefault(suppliedStorage);
  storage.setItem(DEVICE_COMPANY_ID, companyId);
  storage.setItem(DEVICE_KEY, deviceKey);
  if (deviceId) storage.setItem(DEVICE_ID, deviceId);
}

export function getPinLoginDeviceIdentity(
  companyId: string,
  suppliedStorage?: DeviceIdentityStorage,
): PinLoginDeviceIdentity {
  const storage = storageOrDefault(suppliedStorage);
  const deviceKey = getOrCreateDeviceKey(companyId, storage);
  const deviceId = storage.getItem(DEVICE_ID) || undefined;
  const sessionToken = storage.getItem("employee_token") || undefined;
  return {
    device_key: deviceKey,
    ...(deviceId ? { device_id: deviceId } : {}),
    ...(sessionToken ? { session_token: sessionToken } : {}),
  };
}

export function clearAuthenticationPreservingDeviceIdentity(
  suppliedStorage?: DeviceIdentityStorage,
) {
  const storage = storageOrDefault(suppliedStorage);
  const retainedEntries = [
    DEVICE_COMPANY_ID,
    DEVICE_KEY,
    DEVICE_ID,
    ...DEVICE_ASSIGNMENT_KEYS,
  ].map((key) => [key, storage.getItem(key)] as const);
  storage.clear();
  for (const [key, value] of retainedEntries) {
    if (value) storage.setItem(key, value);
  }
}
