import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/sales-responsive.css", import.meta.url), "utf8");

test("checkout exposes one sale discount input and no line discount input", () => {
  assert.doesNotMatch(app, />Item discount</);
  assert.doesNotMatch(app, />Line discount</);
  assert.match(app, /<span>Sale discount<\/span>/);
  assert.equal((app.match(/aria-label="Sale discount"/g) || []).length, 1);
});

test("queued offline sales carry an origin timestamp and are not assigned a shift during sync", () => {
  assert.match(app, /client_created_at: new Date\(\)\.toISOString\(\)/);
  assert.match(app, /queueOfflineSale\(queuedPayload\)/);
  assert.match(app, /shift_id\?: string \| null/);
});

test("zero-value discount summaries are conditional", () => {
  assert.match(app, /Number\(discounted\.sale_discount_amount\) > 0/);
  assert.doesNotMatch(app, /Item discounts applied:/);
  assert.match(app, /Sale discount applied:/);
});

test("sale discount feeds the displayed subtotal and total exactly once", () => {
  assert.equal((app.match(/applyDiscounts\(cart,/g) || []).length, 1);
  assert.match(app, /const cartAmount = Number\(discounted\.total\)/);
  assert.match(app, /let subtotal = cartAmount/);
  assert.match(app, /let total = cartAmount/);
});

test("cart controls use bounded responsive grids without horizontal scrolling", () => {
  assert.match(css, /\.pos-cart-row\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) auto 34px/);
  assert.doesNotMatch(css, /\.pos-item-discount-field/);
  assert.match(css, /\.pos-sales-cart[\s\S]*overflow-x:\s*hidden/);
  assert.match(css, /@media \(max-width: 390px\)/);
});
