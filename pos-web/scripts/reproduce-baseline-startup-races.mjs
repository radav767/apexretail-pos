import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = resolve(import.meta.dirname, "..");
const baseline = readFileSync(resolve(root, "../../baseline/src/api/client.ts"), "utf8");
const compiled = ts.transpileModule(baseline.replace("import.meta.env.VITE_API_BASE_URL", "undefined"), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
}).outputText;
const file = resolve(root, ".baseline-client-reproduction.mjs");
writeFileSync(file, compiled);
const values = new Map([["token", "test-owner"], ["company_id", "test-company"],
  ["employee_token", "test-expired-employee"], ["employee_id", "test-employee"]]);
globalThis.localStorage = { getItem: k => values.get(k) || null, setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) };
let invalidations = 0;
globalThis.window = { dispatchEvent: () => { invalidations += 1; } };
globalThis.CustomEvent = class { constructor(type) { this.type = type; } };
const { api } = await import(pathToFileURL(file).href);
let rejectOld;
api.defaults.adapter = config => new Promise((_, reject) => { rejectOld = () => reject({ response: { status: 401 }, config }); });
const pending = api.get("/subscriptions/test-company").catch(() => {});
values.set("employee_token", "test-fresh-employee");
rejectOld(); await pending;
assert.equal(values.get("employee_token"), undefined);
assert.equal(invalidations, 1);
console.log("Reproduced baseline: an old subscription 401 clears a newly authenticated employee session.");

values.clear(); values.set("token", "test-owner"); values.set("company_id", "test-company");
let finishSettings;
api.defaults.adapter = config => {
  if (config.url === "/settings/test-company") return new Promise(resolve => {
    finishSettings = () => resolve({ status: 200, data: {}, headers: {}, config });
  });
  if (!config.headers.Authorization) return Promise.reject({ response: { status: 401 }, config });
  return Promise.resolve({ status: 200, data: {}, headers: {}, config });
};
const startup = (async () => {
  await api.get("/settings/test-company");
  return api.get("/subscriptions/test-company");
})();
values.delete("token"); // The deployed logout clears credentials without cancelling this chain.
finishSettings();
await assert.rejects(startup, error => error.response.status === 401);
values.set("token", "test-owner-after-retry");
assert.equal((await api.get("/subscriptions/test-company")).status, 200);
console.log("Reproduced baseline: startup continues after logout and sends subscription without credentials; a fresh retry succeeds.");

let registered = false, finishRegistration;
api.defaults.adapter = config => {
  if (config.url === "/devices/register") return new Promise(resolve => { finishRegistration = () => {
    registered = true; resolve({ status: 200, data: {}, headers: {}, config });
  }; });
  if (!registered) return Promise.reject({ response: { status: 404 }, config });
  return Promise.resolve({ status: 200, data: {}, headers: {}, config });
};
// The deployed App starts these operations in separate effects with the same guards.
const registration = api.post("/devices/register");
await assert.rejects(api.post("/devices/heartbeat"), error => error.response.status === 404);
finishRegistration(); await registration;
assert.equal((await api.post("/devices/heartbeat")).status, 200);
console.log("Reproduced baseline: concurrent heartbeat gets 404; after registration the same heartbeat succeeds.");
