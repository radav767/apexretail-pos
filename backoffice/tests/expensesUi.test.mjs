import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../src/pages/ExpensesPage.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/pages/expenses.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("Expenses navigation preserves hamburger and Logout behavior", () => {
  assert.match(app, />\s*Expense Reports\s*</);
  assert.match(app, /page === "expenses" && \(\s*<ExpensesPage/);
  assert.match(app, /function navigateTo[\s\S]*setMobileMenuOpen\(false\)/);
  assert.match(app, /className="logout-nav-button"/);
});

test("expense report omits cashier posting while retaining category administration", () => {
  assert.doesNotMatch(page, /api\.post\("\/expenses"/);
  assert.match(page, /api\.post\("\/expenses\/categories"/);
  assert.match(page, /api\.patch\(`\/expenses\/categories\/\$\{companyId\}/);
  assert.match(page, /api\.delete\(`\/expenses\/categories\/\$\{companyId\}/);
  assert.match(page, /Categories referenced by posted expenses cannot be deleted/);
  assert.match(page, /Cashiers post expenses in POS/);
});

test("expense filters and audit history expose required fields", () => {
  for (const label of ["Date from", "Date to", "Branch", "Category", "Payment method", "User / actor", "Search reference or note", "Status"]) assert.ok(page.includes(label));
  assert.match(page, /Mobile \/ Transfer/);
  assert.match(page, />Posted</);
});

test("expense report and actor filter display resolved staff names", () => {
  assert.match(page, /expense\.actor_name \|\| expense\.actor_id \|\| expense\.employee_id/);
  assert.match(page, /options\.set\(`employee:\$\{expense\.employee_id\}`, expense\.actor_name/);
});

test("expense report uses server filters, totals and bounded pagination", () => {
  for (const value of ["start_at", "end_at", "branch_id", "category_id", "payment_method", "search", "page_size: 25"]) assert.ok(page.includes(value));
  assert.match(page, /unpackPage<Expense>/);
  assert.match(page, /<Pagination meta=\{expensePage\}/);
  assert.doesNotMatch(page, /limit: 500/);
});

test("expense layouts cover desktop, tablet, phone and narrow phone", () => {
  assert.match(css, /grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\)/);
  assert.match(css, /@media \(max-width: 1100px\)/);
  assert.match(css, /@media \(max-width: 720px\)[\s\S]*\.expense-responsive-table thead\s*{\s*display: none;/);
  assert.match(css, /@media \(max-width: 390px\)/);
});
