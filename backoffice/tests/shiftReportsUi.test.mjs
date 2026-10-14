import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../src/pages/ShiftReportsPage.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/pages/shift-reports.css", import.meta.url), "utf8");

test("Shift Reports is registered in Backoffice navigation and page rendering", () => {
  assert.match(app, /"shift-reports"/);
  assert.match(app, /Shift Reports/);
  assert.match(app, /<ShiftReportsPage companyId=\{companyId\}/);
  assert.match(app, /Cashier Shift Reports/);
});

test("report uses company-scoped paginated shift, details, filter, and CSV endpoints", () => {
  assert.match(page, /`\/shifts\/company\/\$\{companyId\}`/);
  assert.match(page, /`\/shifts\/company\/\$\{companyId\}\/filters`/);
  assert.match(page, /`\/shifts\/company\/\$\{companyId\}\/\$\{shift\.id\}`/);
  assert.match(page, /`\/shifts\/company\/\$\{companyId\}\/export\.csv`/);
  assert.match(page, /page_size: 25/);
});

test("date presets, cashier, branch, register, and status filters are provided", () => {
  for (const label of ["Today", "Yesterday", "This week", "This month", "Custom", "Cashier", "Shop / branch", "Register / device", "Status"]) {
    assert.ok(page.includes(label), `missing ${label}`);
  }
  assert.match(page, /start_at: start/);
  assert.match(page, /end_at: end/);
  assert.match(page, /employee_id: filters\.employeeId/);
  assert.match(page, /branch_id: filters\.branchId/);
  assert.match(page, /device_id: filters\.deviceId/);
});

test("cash reconciliation keeps each physical currency separate", () => {
  assert.match(page, /variance_by_currency/);
  assert.match(page, /Total variance by physical currency/);
  assert.match(page, /Never converted or combined across currencies/);
  assert.match(page, /Cash reconciliation by physical currency/);
  assert.match(page, /currency_code/);
  assert.match(page, /Expected/);
  assert.match(page, /Counted/);
});

test("shift detail and summary include payment totals and cash movements", () => {
  for (const label of ["Total shifts", "Open shifts", "Closed shifts", "Total sales", "Cash received", "Gross sales", "Net sales", "Cash sales", "Card sales", "Mobile sales", "Credit sales", "Cash settlements", "Cash paid out", "Refunds", "Cash expenses"]) {
    assert.ok(page.includes(label), `missing ${label}`);
  }
  assert.match(page, /View/);
  assert.match(page, /role="dialog"/);
});

test("Shift Reports remains responsive at tablet, 720px phone, and narrow phone sizes", () => {
  assert.match(css, /@media \(max-width:1100px\)/);
  assert.match(css, /@media \(max-width:760px\)/);
  assert.match(css, /@media \(max-width:390px\)/);
  assert.match(css, /\.shift-table td::before/);
});
