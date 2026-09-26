import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../src/pages/CreditSettlementsPage.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/pages/credit-settlements.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("Credit Settlements is responsive navigation without changing hamburger or logout", () => {
  assert.match(app, />\s*Credit Settlements\s*</);
  assert.match(app, /page === "credit-settlements" && \(\s*<CreditSettlementsPage/);
  assert.match(app, /function navigateTo[\s\S]*setMobileMenuOpen\(false\)/);
  assert.match(app, /className="logout-nav-button"/);
  assert.match(css, /@media \(max-width: 1100px\)/);
  assert.match(css, /@media \(max-width: 720px\)[\s\S]*\.credit-responsive-table thead\s*{\s*display: none;/);
  assert.match(css, /@media \(max-width: 390px\)/);
});

test("workflow posts online to the authoritative Phase 1 settlement API", () => {
  assert.match(page, /api\.post\("\/credit\/settlements"/);
  assert.match(page, /Credit settlements are online-only/);
  assert.match(page, /idempotency_key: requestKey\(\)/);
  assert.match(page, /Balance before/);
  assert.match(page, /Balance after/);
  assert.match(page, /Confirm immutable settlement/);
  assert.match(page, /original sale amount remains unchanged/);
});

test("customer account data refreshes immediately after posting", () => {
  assert.match(page, /await loadData\(true\)/);
  assert.match(page, /Customer balances and history are now up to date/);
  assert.match(page, /apex:credit-settlement-posted/);
});

test("history and filters cover customer, branch, method, date, status and audit user", () => {
  for (const label of ["Search customer", "Select customer", "Branch", "Payment method", "Account status", "Date from", "Date to", "Settlement history", "User"]) assert.ok(page.includes(label));
  assert.match(page, /cash payment will increase expected cash-on-hand/);
});
