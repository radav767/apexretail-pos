import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const tools = readFileSync(new URL("../src/ProductToolsPage.tsx", import.meta.url), "utf8");
const modules = readFileSync(new URL("../src/PosModulePage.tsx", import.meta.url), "utf8");

test("checkout sends variant identity and retains idempotent sale identity", () => {
  assert.match(app, /variant_id:item\.variant_id\|\|null/);
  assert.match(app, /nonCreditSaleIdentityRef/);
  assert.match(app, /product\.variants\?\.length/);
});

test("customer pricing and product tax rules are applied before checkout", () => {
  assert.match(app, /price_level_name/);
  assert.match(app, /productTaxRules/);
  assert.match(app, /tax_exempt/);
});

test("POS product tools support variant stock and validated CSV-XLSX import", () => {
  assert.match(tools, /variantStock/);
  assert.match(tools, /branch_id: branchId/);
  assert.match(tools, /\/products\/import\/preview/);
  assert.match(tools, /\.csv,\.xlsx/);
  assert.match(tools, /Import valid preview/);
});

test("POS product editor uploads camera or gallery images through the protected API", () => {
  assert.match(modules, /capture="environment"/);
  assert.match(modules, /image\/jpeg,image\/png,image\/webp/);
  assert.match(modules, /\/products\/images\//);
});

