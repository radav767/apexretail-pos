import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../src/pages/CreditSettlementsPage.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/pages/credit-settlements.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("Credit Settlements is responsive navigation without changing hamburger or logout", () => {
  assert.match(app, />\s*Credit Management\s*</);
  assert.match(app, /page === "credit-settlements" && \(\s*<CreditSettlementsPage/);
  assert.match(app, /function navigateTo[\s\S]*setMobileMenuOpen\(false\)/);
  assert.match(app, /className="logout-nav-button"/);
  assert.match(css, /@media \(max-width: 1100px\)/);
  assert.match(css, /@media \(max-width: 720px\)[\s\S]*\.credit-responsive-table thead\s*{\s*display: none;/);
  assert.match(css, /@media \(max-width: 390px\)/);
});

test("Backoffice is a read-only outstanding, ageing and settlement report", () => {
  assert.doesNotMatch(page, /api\.post\("\/credit\/settlements"/);
  assert.match(page, /Cashiers post settlements in POS/);
  assert.match(page, /Outstanding credit & ageing report/);
  for (const bucket of ["current", "1–30", "31–60", "61–90", "90+"]) assert.ok(page.includes(bucket));
});

test("history and filters cover customer, branch, method, date, status and audit user", () => {
  for (const label of ["Search customer", "Customer", "Sale / settlement reference", "Branch", "Method", "Status", "Date from", "Date to", "Settlement report", "User"]) assert.ok(page.includes(label));
});

test("credit reports send filters and pagination to the server", () => {
  for (const value of ["customer_id", "branch_id", "payment_method", "start_at", "end_at", "search", "page_size:25"]) assert.ok(page.includes(value));
  assert.match(page, /unpackPage<Receivable>/);
  assert.match(page, /unpackPage<Settlement>/);
  assert.match(page, /<Pagination meta=\{receivablePage\}/);
  assert.match(page, /<Pagination meta=\{settlementPage\}/);
  assert.doesNotMatch(page, /limit:500/);
});

test("settlement report prefers the resolved actor name and safely falls back to IDs", () => {
  assert.match(page, /row\.actor_name\|\|row\.actor_id\|\|row\.cashier_employee_id\|\|row\.actor_user_id\|\|"Unknown"/);
});
