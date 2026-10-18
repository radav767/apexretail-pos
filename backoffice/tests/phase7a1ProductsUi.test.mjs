import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const products = readFileSync(new URL("../src/pages/ProductsPage.tsx", import.meta.url), "utf8");
const customers = readFileSync(new URL("../src/pages/CustomersPage.tsx", import.meta.url), "utf8");

test("product editor supports secure image upload and product tax policy", () => {
  assert.match(products, /image\/jpeg,image\/png,image\/webp/);
  assert.match(products, /\/products\/images\//);
  assert.match(products, /tax_exempt/);
  assert.match(products, /tax_rate/);
});

test("variants expose pricing and branch stock fields", () => {
  for (const name of ["variantCost", "variantPrice", "variantStock", "variantReorder"]) {
    assert.match(products, new RegExp(name));
  }
  assert.match(products, /branch_id: form\.branch_id/);
});

test("imports use server preview validation for CSV and XLSX", () => {
  assert.match(products, /\/products\/import\/preview/);
  assert.match(products, /\.csv,\.xlsx/);
  assert.match(products, /Correct all import errors/);
});

test("customer forms expose assigned price level", () => {
  assert.match(customers, /price_level_name/);
  assert.match(customers, /Retail \/ standard/);
});

