import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../src/FinancialModules.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/financial-modules.css", import.meta.url), "utf8");
const customerApi = readFileSync(new URL("../src/customerApi.ts", import.meta.url), "utf8");

test("POS navigation exposes operational financial modules without changing logout", () => {
  for (const label of ["Customers", "Credit Settlements", "Expenses"]) assert.match(app, new RegExp(`showPosModule\\(\\"${label}\\"\\)`));
  assert.match(app, /clearAuthenticationPreservingDeviceIdentity/);
  assert.match(app, /Log out/);
});

test("customer workflow shares authoritative customer search with credit checkout", () => {
  assert.match(app, /searchCustomers\(companyId, query/);
  assert.match(page, /searchCustomers\(companyId, search/);
  assert.match(customerApi, /api\.get\(`\/customers\/\$\{companyId\}`/);
  assert.match(page, /Manager credit configuration/);
  assert.match(page, /Credit settings and active status require manager permission/);
});

test("settlements are online, idempotent, validated and printable", () => {
  assert.match(page, /Credit settlements are online-only/);
  assert.match(page, /settlement cannot exceed|Settlement cannot exceed/);
  assert.match(page, /idempotency_key: settlementKey\.current/);
  assert.match(page, /printSettlement\(/);
  assert.match(page, /Balance after|After/);
});

test("expenses use session branch and server-derived cashier", () => {
  assert.match(page, /branch_id: branchId/);
  assert.doesNotMatch(page, /employee_id:/);
  assert.match(page, /Branch and cashier are recorded automatically/);
  assert.match(page, /idempotency_key: expenseKey\.current/);
});

test("financial modules cover tablet, phone and narrow phone layouts", () => {
  assert.match(css, /@media\(max-width:720px\)/);
  assert.match(css, /@media\(max-width:390px\)/);
});
