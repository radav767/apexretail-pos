import assert from "node:assert/strict";
import test from "node:test";
import {
  clearAuthenticationPreservingDeviceIdentity,
  getOrCreateDeviceKey,
  getPinLoginDeviceIdentity,
  rememberDeviceIdentity,
  type DeviceIdentityStorage,
} from "../src/deviceIdentity.ts";

class MemoryStorage implements DeviceIdentityStorage {
  constructor(private values = new Map<string, string>()) {}
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
  clear() { this.values.clear(); }
}

function preparedDevice(storage = new MemoryStorage()) {
  const key = getOrCreateDeviceKey("company-a", storage);
  rememberDeviceIdentity("company-a", key, "terminal-a", storage);
  storage.setItem("employee_token", "session-a");
  storage.setItem("employee_id", "cashier-a");
  return { storage, key };
}

test("same-device reload, Back navigation, restart, and in-place upgrade retain identity", () => {
  const { storage, key } = preparedDevice();
  for (const lifecycle of ["reload", "back", "restart", "upgrade"]) {
    assert.equal(getOrCreateDeviceKey("company-a", storage), key, lifecycle);
    assert.equal(getPinLoginDeviceIdentity("company-a", storage).device_id, "terminal-a");
  }
});

test("repeated login and a second tab reuse the device and current session", () => {
  const sharedValues = new Map<string, string>();
  const firstTab = new MemoryStorage(sharedValues);
  const secondTab = new MemoryStorage(sharedValues);
  const { key } = preparedDevice(firstTab);
  assert.deepEqual(getPinLoginDeviceIdentity("company-a", firstTab), {
    device_id: "terminal-a", device_key: key, session_token: "session-a",
  });
  assert.deepEqual(
    getPinLoginDeviceIdentity("company-a", secondTab),
    getPinLoginDeviceIdentity("company-a", firstTab),
  );
});

test("expired authentication and offline recovery do not replace device identity", () => {
  const { storage, key } = preparedDevice();
  storage.removeItem("employee_token");
  storage.removeItem("employee_id");
  const recovered = getPinLoginDeviceIdentity("company-a", storage);
  assert.equal(recovered.device_key, key);
  assert.equal(recovered.device_id, "terminal-a");
  assert.equal(recovered.session_token, undefined);
});

test("full logout removes authentication but preserves the terminal identity", () => {
  const { storage, key } = preparedDevice();
  storage.setItem("token", "owner-token");
  storage.setItem("shop_id", "shop-a");
  storage.setItem("branch_id", "branch-a");
  storage.setItem("branch_name", "Main Branch");
  clearAuthenticationPreservingDeviceIdentity(storage);
  assert.equal(storage.getItem("token"), null);
  assert.equal(storage.getItem("employee_token"), null);
  assert.equal(storage.getItem("device_key"), key);
  assert.equal(storage.getItem("device_id"), "terminal-a");
  assert.equal(storage.getItem("shop_id"), "shop-a");
  assert.equal(storage.getItem("branch_id"), "branch-a");
  assert.equal(storage.getItem("branch_name"), "Main Branch");
});

test("a genuinely different browser gets a different identity", () => {
  const first = preparedDevice();
  const secondStorage = new MemoryStorage();
  const secondKey = getOrCreateDeviceKey("company-a", secondStorage);
  assert.notEqual(secondKey, first.key);
  assert.equal(getPinLoginDeviceIdentity("company-a", secondStorage).device_id, undefined);
});

test("switching tenants rotates identity instead of crossing tenant ownership", () => {
  const { storage, key } = preparedDevice();
  const nextKey = getOrCreateDeviceKey("company-b", storage);
  assert.notEqual(nextKey, key);
  assert.equal(storage.getItem("device_id"), null);
  assert.equal(storage.getItem("device_company_id"), "company-b");
});
