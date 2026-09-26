import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../src/pages/CustomersPage.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/pages/customers.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("Customers is a distinct Backoffice destination without changing logout behavior", () => {
  assert.match(app, /import CustomersPage/);
  assert.match(app, />\s*Customers\s*</);
  assert.match(app, /page === "customers" && \(\s*<CustomersPage/);
  assert.match(app, /function navigateTo[\s\S]*setMobileMenuOpen\(false\)/);
  assert.match(app, /className="logout-nav-button"/);
});

test("customer list, editor and explicit credit policy use Phase 1 APIs", () => {
  for (const endpoint of [
    "/customers/${companyId}",
    "/customers/${companyId}/${customerId}/transactions",
    "/credit/${companyId}/receivables",
    "/credit/${companyId}/settlements",
  ]) assert.ok(page.includes(endpoint));
  for (const field of [
    "customer_code", "credit_enabled", "unlimited_credit", "credit_limit",
    "credit_terms_days", "outstanding_balance", "available_credit",
  ]) assert.ok(page.includes(field));
  assert.match(page, /Name, phone or customer code/);
  assert.match(page, /Credit remains disabled unless it is explicitly enabled/);
});

test("customer details expose history, receivables and settlements", () => {
  assert.match(page, /History \(\{transactions\.length\}\)/);
  assert.match(page, /Receivables \(\{receivables\.length\}\)/);
  assert.match(page, /Settlements \(\{settlements\.length\}\)/);
  assert.match(page, /You do not have permission to view settlement history/);
});

test("Customers remains usable at desktop, tablet and phone widths", () => {
  assert.match(css, /grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\)/);
  assert.match(css, /@media \(max-width: 1100px\)/);
  assert.match(css, /@media \(max-width: 720px\)[\s\S]*\.customer-table thead\s*{\s*display: none;/);
  assert.match(css, /@media \(max-width: 390px\)/);
  assert.match(css, /max-height:\s*calc\(100vh - 20px\)/);
});
