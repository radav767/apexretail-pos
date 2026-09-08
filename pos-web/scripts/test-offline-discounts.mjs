import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

// Exercise the real queue and synchronization code with an in-memory SQLite bridge.
const rows = new Map();
let failures = 0;
const sent = [];
const database = {
  isDBOpen: async () => ({ result: true }), execute: async () => {},
  run: async (sql, args = []) => {
    if (sql.includes("INSERT OR IGNORE")) {
      if (!rows.has(args[0])) rows.set(args[0], { client_sale_id: args[0], payload_json: args[1], attempts: 0, status: "pending" });
    } else if (sql.includes("DELETE FROM")) rows.delete(args[0]);
    else if (sql.includes("attempts = attempts + 1")) rows.get(args[1]).attempts++;
  },
  query: async (sql) => ({ values: sql.includes("COUNT(*)") ? [{ total: rows.size }] : [...rows.values()] }),
};
globalThis.__offlineMocks = {
  Capacitor: { getPlatform: () => "android" },
  Network: { getStatus: async () => ({ connected: true }) },
  CapacitorSQLite: {},
  SQLiteConnection: class {
    async checkConnectionsConsistency() {}
    async isConnection() { return { result: true }; }
    async retrieveConnection() { return database; }
  },
  api: { post: async (_url, payload) => {
    sent.push(payload);
    if (failures-- > 0) throw new Error("Network unavailable");
    return { data: payload };
  } },
};
let source = readFileSync(new URL("../src/offline/offlineSales.ts", import.meta.url), "utf8");
source = source.replace(/import[\s\S]*?from ["'][^"']+["'];/g, "");
source = "const { Capacitor, Network, CapacitorSQLite, SQLiteConnection, api } = globalThis.__offlineMocks;\n" + source;
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2023, module: ts.ModuleKind.ESNext } }).outputText;
const { queueOfflineSale, syncPendingOfflineSales } = await import(`data:text/javascript;base64,${Buffer.from(js).toString("base64")}`);
for (const discount of [undefined, null, "0.00", "0.20"]) {
  const payload = { client_sale_id: `sale-${discount}`, company_id: "company", payment_method: "cash", items: [] };
  if (discount !== undefined) payload.discount_amount = discount;
  await queueOfflineSale(payload);
  await queueOfflineSale({ ...payload, discount_amount: "99.00" });
  failures = 1;
  assert.equal((await syncPendingOfflineSales()).failed, 1);
  assert.equal(rows.size, 1);
  const results = await Promise.all([syncPendingOfflineSales(), syncPendingOfflineSales()]);
  assert.equal(results[0].synced, 1);
  assert.equal(rows.size, 0);
  assert.deepEqual(sent.at(-1), payload);
  assert.deepEqual(sent.at(-2), payload);
}
console.log("PASS: SQLite queue, duplicate enqueue, network failure, retry, concurrent sync, legacy omitted/null and explicit discounts");
