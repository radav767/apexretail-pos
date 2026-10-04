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
  assert.match(page, /cashier\?\.permissions\?\.customers_manage/);
  assert.match(page, /canManageCredit \? policy/);
  assert.match(page, /credit_enabled: false, unlimited_credit: false, credit_limit: null, credit_terms_days: 0/);
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

test("financial histories display server-resolved actor names with identifier fallback", () => {
  assert.match(page, /row\.actor_name \|\| row\.actor_id \|\| "Unknown"/);
  assert.equal((page.match(/row\.actor_name \|\| row\.actor_id \|\| "Unknown"/g) || []).length, 3);
  assert.match(page, /type Settlement = \{[^\n]*actor_name\?: string \| null/);
  assert.match(page, /type Expense = \{[^\n]*actor_name\?: string \| null/);
});

test("Customers list uses the shared mobile header clearance", () => {
  assert.match(page, /activeModule === "Customers"/);
  assert.match(page, /<h2>Customers<\/h2>/);
  assert.match(page, /className="pos-module-overlay financial-module"/);
  assert.match(css, /\.financial-module\.pos-module-overlay\s*\{[\s\S]*padding:\s*var\(--financial-mobile-header-clearance\)/);
});

test("Add and Edit Customer forms remain scrollable above the safe area", () => {
  assert.match(page, /editingCustomer \? "Edit Customer" : "Add Customer"/);
  assert.match(page, /className="financial-form-scroll"/);
  assert.match(css, /\.financial-modal \.financial-form-scroll\s*\{[\s\S]*overflow-y:\s*auto/);
  assert.match(css, /\.financial-modal \.financial-actions\s*\{[\s\S]*safe-area-inset-bottom/);
});

test("Customer detail starts below the same responsive module header", () => {
  assert.match(page, /Select a customer to view the account/);
  assert.match(page, /className="financial-title"/);
  assert.match(page, /Transaction & credit history/);
  assert.match(css, /\.financial-module \.pos-module-container\s*\{[\s\S]*padding:\s*0/);
});

test("Credit Settlements uses the shared responsive financial page", () => {
  assert.match(page, /activeModule === "Credit Settlements"/);
  assert.match(page, /<h3>Open receivables<\/h3>/);
  assert.match(page, /<h3>Settlement history<\/h3>/);
  assert.match(css, /@media \(max-width: 720px\)/);
});

test("Expenses uses the shared responsive financial page", () => {
  assert.match(page, /activeModule === "Expenses"/);
  assert.match(page, /<h2>Add Expense<\/h2>/);
  assert.match(page, /<h2>Today’s expenses<\/h2>/);
  assert.match(css, /@media \(max-width: 390px\)/);
});

test("financial pages reserve hamburger and safe-area space at 720px and 390px", () => {
  assert.match(css, /--financial-mobile-header-clearance:\s*calc\(88px \+ env\(safe-area-inset-top\)\)/);
  assert.match(css, /scroll-padding-block:\s*var\(--financial-mobile-header-clearance\)/);
  assert.match(css, /\.financial-modal-backdrop\s*\{[\s\S]*padding:\s*var\(--financial-mobile-header-clearance\)/);
  assert.match(css, /padding:\s*var\(--financial-mobile-header-clearance\) 12px calc\(24px \+ env\(safe-area-inset-bottom\)\)/);
});
