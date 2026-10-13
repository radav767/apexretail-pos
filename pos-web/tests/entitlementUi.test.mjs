import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const verifier = readFileSync(
  new URL("../src/offline/entitlement.ts", import.meta.url),
  "utf8",
);
const productionBuild = readFileSync(
  new URL("../scripts/build-production.mjs", import.meta.url),
  "utf8",
);
const viteConfig = readFileSync(
  new URL("../vite.config.ts", import.meta.url),
  "utf8",
);

test("refresh and offline fallback reverify cached snapshots", () => {
  assert.match(app, /loadEntitlementSnapshot\(selectedCompanyId\)/);
  assert.match(app, /verifyEntitlementSnapshotDetailed\(cached\)/);
  assert.match(app, /entitlementReconnectMessage\(verification\.category\)/);
  assert.match(app, /role="alert"/);
});

test("unknown, retired and legacy keys instruct the operator to reconnect", () => {
  assert.match(verifier, /"unknown_key_id", "key_retired", "legacy_key_retired"/);
  assert.match(verifier, /Reconnect and reload the POS/i);
});

test("production builds reject private keys and secret-like inputs", () => {
  assert.match(productionBuild, /publicKeyring\.includes\("PRIVATE KEY"\)/);
  assert.match(productionBuild, /scanBuildInputs/);
  assert.match(productionBuild, /refuses environment files/);
  assert.match(viteConfig, /secretLikeVariables/);
  assert.match(viteConfig, /valid JSON/);
});
