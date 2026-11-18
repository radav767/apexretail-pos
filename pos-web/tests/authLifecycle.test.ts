import assert from "node:assert/strict";
import test from "node:test";
import { AxiosError } from "axios";
import type { InternalAxiosRequestConfig } from "axios";
import { api } from "../src/api/client.ts";
import { registerCurrentDevice } from "../src/device.ts";
import { advanceAuthenticationEpoch, captureAuthentication, createBootstrapScope, runBootstrapSteps } from "../src/api/authLifecycle.ts";

class MemoryStorage {
  entries = new Map<string, string>();
  getItem(key: string) { return this.entries.get(key) || null; }
  setItem(key: string, value: string) { this.entries.set(key, value); }
  removeItem(key: string) { this.entries.delete(key); }
  clear() { this.entries.clear(); }
}

const storage = new MemoryStorage();
Object.defineProperty(globalThis, "localStorage", { value: storage, configurable: true });
const events: Event[] = [];
Object.defineProperty(globalThis, "window", { value: { dispatchEvent: (event: Event) => { events.push(event); return true; } }, configurable: true });
if (typeof CustomEvent === "undefined") {
  Object.defineProperty(globalThis, "CustomEvent", { value: class extends Event {
    detail: unknown;
    constructor(type: string, options?: CustomEventInit) { super(type); this.detail = options?.detail; }
  } });
}

function reset() {
  storage.clear(); events.length = 0; advanceAuthenticationEpoch();
  storage.setItem("token", "owner-A"); storage.setItem("company_id", "company-A");
}
function unauthorized(config: InternalAxiosRequestConfig): AxiosError {
  return new AxiosError("Authentication required", "ERR_BAD_REQUEST", config, undefined,
    { status: 401, statusText: "Unauthorized", data: { detail: "Authentication required" }, headers: {}, config });
}
function ok(config: InternalAxiosRequestConfig, data: unknown = {}) {
  return { status: 200, statusText: "OK", data, headers: {}, config };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

test("late subscription 401 cannot invalidate a newer PIN session or replay as owner", async () => {
  reset(); storage.setItem("employee_token", "expired-employee"); storage.setItem("employee_id", "employee-A");
  const reply = deferred<void>(); let calls = 0;
  api.defaults.adapter = async config => { calls += 1; await reply.promise; throw unauthorized(config); };
  const old = api.get("/subscriptions/company-A");
  storage.setItem("employee_token", "fresh-employee"); advanceAuthenticationEpoch();
  reply.resolve();
  await assert.rejects(old, error => {
    assert.equal(JSON.stringify((error as AxiosError).config).includes("owner-A"), false);
    return /Authentication required/.test((error as Error).message);
  });
  assert.equal(storage.getItem("employee_token"), "fresh-employee");
  assert.equal(events.length, 0); assert.equal(calls, 1);
});

test("current employee 401 invalidates only that employee; current owner 401 requests owner sign-in", async () => {
  reset(); storage.setItem("employee_token", "employee-A"); storage.setItem("employee_id", "employee-A");
  api.defaults.adapter = async config => { throw unauthorized(config); };
  await assert.rejects(api.get("/subscriptions/company-A"));
  assert.equal(storage.getItem("employee_token"), null);
  assert.equal(storage.getItem("token"), "owner-A");
  assert.equal((events[0] as CustomEvent).detail.kind, "employee");
  events.length = 0;
  await assert.rejects(api.get("/subscriptions/company-A"));
  assert.equal(storage.getItem("token"), null);
  assert.equal((events[0] as CustomEvent).detail.kind, "owner");
});

test("login rejection or an unauthenticated late 401 does not clear a newer owner session", async () => {
  reset(); api.defaults.adapter = async config => { throw unauthorized(config); };
  await assert.rejects(api.post("/auth/login", { email: "test@example.com", password: "incorrect-test-only" }));
  assert.equal(storage.getItem("token"), "owner-A"); assert.equal(events.length, 0);
  storage.removeItem("token");
  const reply = deferred<void>();
  api.defaults.adapter = async config => { await reply.promise; throw unauthorized(config); };
  const old = api.get("/subscriptions/company-A");
  storage.setItem("token", "owner-B"); advanceAuthenticationEpoch(); reply.resolve();
  await assert.rejects(old);
  assert.equal(storage.getItem("token"), "owner-B"); assert.equal(events.length, 0);
});

test("startup stops between awaits after logout rather than sending an unauthorized subscription request", async () => {
  reset(); const scope = createBootstrapScope(); const response = deferred<void>(); let subscriptionRequests = 0;
  api.defaults.adapter = async config => { subscriptionRequests += 1; throw unauthorized(config); };
  const started = runBootstrapSteps(scope.isCurrent, [() => response.promise, () => api.get("/subscriptions/company-A")]);
  storage.removeItem("token"); advanceAuthenticationEpoch(); response.resolve();
  assert.equal(await started, false); assert.equal(subscriptionRequests, 0);
});

test("a current startup subscription failure is propagated and not hidden", async () => {
  reset(); const scope = createBootstrapScope();
  api.defaults.adapter = async config => { throw unauthorized(config); };
  // A non-HTTP error does not itself change authentication, so it must propagate.
  await assert.rejects(runBootstrapSteps(scope.isCurrent, [async () => { throw new Error("subscription unavailable"); }]), /subscription unavailable/);
  await assert.rejects(runBootstrapSteps(scope.isCurrent, [() => api.get("/subscriptions/company-A")]), /Authentication required/);
});

test("registration completes before heartbeat readiness and stale registration cannot replace company identity", async () => {
  reset(); storage.setItem("device_key", "key-A"); storage.setItem("device_company_id", "company-A");
  const reply = deferred<void>(); const calls: string[] = [];
  api.defaults.adapter = async config => {
    calls.push(config.url || "");
    if (config.url === "/devices/register") { await reply.promise; return ok(config, { id: "device-A", device_key: "key-A", branch_id: "branch-A" }); }
    assert.equal(storage.getItem("device_id"), "device-A"); return ok(config);
  };
  const scope = createBootstrapScope();
  const initialization = (async () => {
    await registerCurrentDevice("company-A", scope.isCurrent);
    if (scope.isCurrent()) await api.post("/devices/heartbeat", { device_id: storage.getItem("device_id") });
  })();
  assert.deepEqual(calls, ["/devices/register"]);
  reply.resolve(); await initialization;
  assert.deepEqual(calls, ["/devices/register", "/devices/heartbeat"]);
  reset(); storage.setItem("device_key", "key-A");
  const late = deferred<void>();
  api.defaults.adapter = async config => { await late.promise; return ok(config, { id: "old-device", device_key: "old-key" }); };
  const oldScope = createBootstrapScope(); const pending = registerCurrentDevice("company-A", oldScope.isCurrent);
  storage.setItem("company_id", "company-B"); storage.setItem("device_key", "key-B"); advanceAuthenticationEpoch(); late.resolve();
  assert.equal(await pending, undefined); assert.equal(storage.getItem("device_key"), "key-B");
});

test("re-login with an identical JWT still invalidates old startup generations", () => {
  reset(); const scope = createBootstrapScope(); const previous = captureAuthentication();
  advanceAuthenticationEpoch();
  assert.equal(scope.isCurrent(), false); assert.notEqual(captureAuthentication().epoch, previous.epoch);
});
