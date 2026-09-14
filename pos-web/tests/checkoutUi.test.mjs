import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/sales-responsive.css", import.meta.url), "utf8");

test("checkout uses distinct item and whole-sale discount labels", () => {
  assert.match(app, />Item discount</);
  assert.match(app, />Whole-sale discount</);
  assert.doesNotMatch(app, />Line discount</);
  assert.doesNotMatch(app, />Sale discount</);
});

test("zero-value discount summaries are conditional", () => {
  assert.match(app, /Number\(discounted\.line_discount_total\) > 0/);
  assert.match(app, /Number\(discounted\.sale_discount_amount\) > 0/);
  assert.match(app, /Item discounts applied:/);
  assert.match(app, /Whole-sale discount applied:/);
});

test("cart controls use bounded responsive grids without horizontal scrolling", () => {
  assert.match(css, /\.pos-cart-row\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) auto 34px/);
  assert.match(css, /\.pos-item-discount-field[\s\S]*grid-column:\s*1 \/ -1/);
  assert.match(css, /\.pos-sales-cart[\s\S]*overflow-x:\s*hidden/);
  assert.match(css, /@media \(max-width: 390px\)/);
});
