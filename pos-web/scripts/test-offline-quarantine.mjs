import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const rows = new Map();
const posts = [];
let nextError = null;

const database = {
  isDBOpen: async () => ({ result: true }),
  execute: async () => {},
  run: async (sql, args = []) => {
    if (sql.includes("INSERT OR IGNORE")) {
      if (!rows.has(args[0])) {
        rows.set(args[0], {
          client_sale_id: args[0], payload_json: args[1], status: "pending",
          attempts: 0, last_error: null, error_code: null,
          error_evidence_json: null, quarantined_at: null,
          created_at: args[2], updated_at: args[3],
        });
      }
    } else if (sql.includes("attempts = attempts + 1")) {
      const row = rows.get(args[1]);
      row.status = "syncing";
      row.attempts += 1;
      row.updated_at = args[0];
    } else if (sql.includes("SET status = ?")) {
      const row = rows.get(args[6]);
      Object.assign(row, {
        status: args[0], last_error: args[1], error_code: args[2],
        error_evidence_json: args[3], quarantined_at: args[4], updated_at: args[5],
      });
    } else if (sql.includes("WHERE status = 'syncing'")) {
      for (const row of rows.values()) {
        if (row.status === "syncing") row.status = "pending";
      }
    } else if (sql.includes("DELETE FROM offline_sales")) {
      rows.delete(args[0]);
    }
  },
  query: async (sql) => {
    if (sql.includes("PRAGMA table_info")) {
      return { values: ["error_code", "error_evidence_json", "quarantined_at"]
        .map((name) => ({ name })) };
    }
    if (sql.includes("COUNT(*)")) {
      return { values: [{ total: [...rows.values()].filter((row) =>
        ["pending", "failed", "syncing", "quarantined"].includes(row.status)).length }] };
    }
    if (sql.includes("status = 'quarantined'")) {
      return { values: [...rows.values()].filter((row) => row.status === "quarantined") };
    }
    return { values: [...rows.values()].filter((row) =>
      ["pending", "failed"].includes(row.status) && row.attempts < 20) };
  },
};

globalThis.__offlineMocks = {
  Capacitor: { getPlatform: () => "android" },
  Network: { getStatus: async () => ({ connected: true }), addListener: async () => ({ remove: async () => {} }) },
  CapacitorSQLite: {},
  SQLiteConnection: class {
    async checkConnectionsConsistency() {}
    async isConnection() { return { result: true }; }
    async retrieveConnection() { return database; }
  },
  api: { post: async (_url, payload) => {
    posts.push(structuredClone(payload));
    if (nextError) {
      const error = nextError;
      nextError = null;
      throw error;
    }
    return { data: payload };
  } },
};

let source = readFileSync(new URL("../src/offline/offlineSales.ts", import.meta.url), "utf8");
source = source.replace(/import[\s\S]*?from ["'][^"']+["'];/g, "");
source = "const { Capacitor, Network, CapacitorSQLite, SQLiteConnection, api } = globalThis.__offlineMocks;\n" + source;
const js = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2023, module: ts.ModuleKind.ESNext },
}).outputText;
const loadModule = (suffix) => import(`data:text/javascript;base64,${Buffer.from(`${js}\n//# sourceURL=offline-${suffix}.mjs`).toString("base64")}`);

const first = await loadModule("first");
for (const error of [
  { response: { status: 401, data: { detail: "Token expired" } } },
  { response: { status: 403, data: { detail: "Temporary authentication failure" } } },
  { response: { status: 500, data: { detail: "Temporary server failure" } } },
  { code: "ECONNABORTED", message: "timeout" },
]) {
  assert.equal(first.isTerminalAuthorityFailure(error), false);
}
for (const code of ["terminal_identity_revoked", "terminal_assignment_changed", "terminal_decommissioned"]) {
  assert.equal(first.isTerminalAuthorityFailure({ response: { status: 409, data: { code } } }), true);
}

const payload = {
  client_sale_id: "quarantine-sale-1", company_id: "company-1",
  branch_id: "old-branch", device_id: "deleted-terminal",
  assignment_revision: 2, payment_method: "cash",
  items: [{ product_id: "product-1", quantity: "1" }],
};
await first.queueOfflineSale(payload);
await first.queueOfflineSale({ ...payload, branch_id: "must-not-overwrite" });
nextError = {
  response: {
    status: 403,
    data: {
      code: "terminal_identity_revoked",
      detail: "This terminal identity was permanently deleted",
    },
  },
};
const quarantined = await first.syncPendingOfflineSales();
assert.equal(quarantined.quarantined, 1);
assert.equal(posts.length, 1);
assert.deepEqual(posts[0], payload);

await first.syncPendingOfflineSales();
assert.equal(posts.length, 1, "quarantined rows must not retry automatically");

const relaunched = await loadModule("relaunched");
await relaunched.initializeOfflineSales();
const visible = await relaunched.getQuarantinedOfflineSales();
assert.equal(visible.length, 1);
assert.deepEqual(visible[0].payload, payload);
assert.equal(visible[0].error_code, "terminal_identity_revoked");
assert.equal(visible[0].error_evidence.http_status, 403);
const recovery = JSON.parse(await relaunched.exportQuarantinedOfflineSales());
assert.equal(recovery.format, "apexretail-offline-sale-quarantine-v1");
assert.deepEqual(recovery.sales[0].payload, payload);

const temporary = { ...payload, client_sale_id: "temporary-auth-sale" };
await relaunched.queueOfflineSale(temporary);
nextError = { response: { status: 401, data: { detail: "Session refresh required" } } };
const failed = await relaunched.syncPendingOfflineSales();
assert.equal(failed.quarantined, 1, "ordinary authentication failure must remain retryable");
await relaunched.syncPendingOfflineSales();
assert.equal(rows.has(temporary.client_sale_id), false);
assert.equal(posts.filter((post) => post.client_sale_id === temporary.client_sale_id).length, 2);

console.log("PASS: explicit quarantine classification, persistence, no auto-retry, evidence export, payload preservation, and idempotent client IDs");
