import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/sales-responsive.css", import.meta.url), "utf8");
const receiptFormatter = readFileSync(new URL("../src/printing/receiptFormatter.ts", import.meta.url), "utf8");
const customerApi = readFileSync(new URL("../src/customerApi.ts", import.meta.url), "utf8");

test("credit checkout requires online customer selection and authoritative sale API", () => {
  assert.match(app, /Credit sales require an online connection/);
  assert.match(app, /searchCustomers\(companyId, query/);
  assert.match(customerApi, /api\.get\(`\/customers\/\$\{companyId\}`/);
  assert.match(app, /customer_id:\s*saleCustomer\?\.id/);
  assert.match(app, /await api\.post\("\/sales", payload\)/);
  assert.match(app, /Confirm Credit Sale/);
});

test("credit cannot enter offline sale queue", () => {
  assert.match(app, /paymentMethod === "credit"[\s\S]*Credit sales are online-only and cannot be queued/);
  assert.match(app, /paymentMethod !== "credit" &&[\s\S]*isNetworkFailure/);
});

test("duplicate submit is guarded and reuses one credit client sale id", () => {
  assert.match(app, /saleSubmissionInFlightRef\.current/);
  assert.match(app, /creditClientSaleIdRef\.current \|\| createClientSaleId\(\)/);
  assert.match(app, /disabled=\{processing \|\| Boolean\(creditProjection\.error\)\}/);
});

test("credit dialog exposes policy, projection and responsive phone layout", () => {
  for (const label of ["Current outstanding", "Credit limit", "Available credit", "Sale total", "Projected balance", "Credit terms", "Due date"]) {
    assert.match(app, new RegExp(label));
  }
  assert.match(css, /\.pos-credit-dialog/);
  assert.match(css, /@media \(max-width: 560px\)[\s\S]*\.pos-credit-summary[\s\S]*grid-template-columns:\s*1fr/);
  assert.match(css, /@media \(max-width: 390px\)/);
});

test("credit customer and due date are shown and printed on the normal receipt", () => {
  assert.match(app, /receipt\.customer_name_snapshot/);
  assert.match(app, /receipt\.credit_due_date/);
  assert.match(receiptFormatter, /Customer:/);
  assert.match(receiptFormatter, /Credit due:/);
  assert.match(receiptFormatter, /Credit sale outstanding/);
});

test("cash, card and mobile remain enabled payment choices", () => {
  assert.match(app, /\["cash", "card", "mobile", "credit"\]/);
  assert.match(app, /if \(paymentMethod === "cash"\)/);
});
