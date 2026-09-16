import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");

test("Dashboard and Sales History remain separate destinations", () => {
  assert.match(app, />\s*Dashboard\s*</);
  assert.match(app, />\s*Sales History\s*</);
  assert.match(app, /page === "dashboard" && \(\s*<DashboardPanel/);
  assert.match(app, /page === "sales" && \(\s*<SalesHistoryPage/);
});

test("login survives reload and logout clears persisted identity", () => {
  assert.match(app, /Boolean\(localStorage\.getItem\("backoffice_token"\)\)/);
  assert.match(app, /localStorage\.getItem\("backoffice_company_id"\)/);
  assert.match(app, /localStorage\.removeItem\("backoffice_token"\)/);
  assert.match(app, /localStorage\.removeItem\("backoffice_company_id"\)/);
});

test("mobile menu opens, closes after navigation, and contains Logout", () => {
  assert.match(app, /aria-expanded=\{mobileMenuOpen\}/);
  assert.match(app, /setMobileMenuOpen\(\(open\) => !open\)/);
  assert.match(app, /function navigateTo[\s\S]*setMobileMenuOpen\(false\)/);
  assert.match(app, /className="logout-nav-button"/);
  assert.match(css, /\.sidebar nav \{\s*display: none;/);
  assert.match(css, /\.sidebar nav\.mobile-open \{\s*display: grid;/);
  assert.match(css, /@media \(max-width: 390px\)/);
  assert.match(css, /@media \(min-width: 761px\)/);
});

test("Dashboard drill-down uses filtered paginated routes and stays separate from Sales History", () => {
  assert.match(app, /analytics-v3\/\$\{companyId\}\/sales/);
  assert.match(app, /analytics-v3\/\$\{companyId\}\/sales\.csv/);
  assert.match(app, /limit: 25, offset/);
  assert.match(app, /dimension_key: request\.dimensionKey/);
  assert.match(app, /page === "dashboard" && drilldownRequest/);
  assert.match(app, /page === "sales" && \(/);
  assert.match(css, /\.dashboard-dialog-backdrop/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*\.dashboard-dialog/);
});
