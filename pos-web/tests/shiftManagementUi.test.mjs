import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../src/ShiftManagementPage.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const modulePage = readFileSync(new URL("../src/PosModulePage.tsx", import.meta.url), "utf8");
const formatter = readFileSync(new URL("../src/printing/receiptFormatter.ts", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/shift-management.css", import.meta.url), "utf8");

test("Shift Management is nested under Sales Management and not a top-level menu entry", () => {
  assert.doesNotMatch(app, /showPosModule\("Shift Management"\)/);
  assert.match(app, /showPosModule\("Sales Management"\)/);
  assert.match(modulePage, /activeModule === "Sales Management"[\s\S]*<ShiftManagementPage/);
  assert.match(modulePage, /<h2>Sales History<\/h2>/);
});

test("Sales automatically checks and gates on the authenticated cashier's current shift", () => {
  assert.match(app, /api\.get\("\/shifts\/current"\)/);
  assert.match(app, /activePosModule === "Sales"[\s\S]*!currentShift/);
  assert.match(app, /offline_shift_token: currentShift\?\.offline_shift_token/);
});

test("open/current/close and cashier history use authoritative shift APIs", () => {
  for (const route of ["/shifts/current", "/shifts/open", "/shifts/my-history", "/shifts/mine/", "/shifts/"]) {
    assert.ok(page.includes(route), `missing API route ${route}`);
  }
  assert.match(page, /idempotency_key: idempotencyKey\(\)/);
  assert.match(page, /counted_balances/);
  assert.match(page, /opening_balances/);
});

test("cash movements are online-only and never queued or represented as sales/expenses", () => {
  assert.match(page, /await isDeviceOnline\(\)/);
  assert.match(page, /No changes were saved or queued/);
  assert.match(page, /cash-movements/);
  assert.match(page, /Cash in/);
  assert.match(page, /Cash out/);
  assert.match(page, /existing offline sales remain available/i);
  assert.doesNotMatch(page, /offlineSales|queueOfflineSale|postExpense|create_sale/);
});

test("physical currency cards, drawer counts, variance, and shift history are shown", () => {
  for (const text of ["Opening", "Current expected cash", "Counted", "Variance", "Shift History", "Cash movement history"]) {
    assert.ok(page.includes(text), `missing ${text}`);
  }
  assert.match(page, /filter\(\(row\) => row\.cash_accepted\)/);
  assert.match(page, /I have physically counted/);
});

test("shift print template is informational, not a sales receipt", () => {
  assert.match(app, /document_type: "shift_summary"/);
  assert.match(formatter, /SHIFT SUMMARY - NOT A SALES RECEIPT/);
  assert.match(page, /Printing does not create a financial transaction/);
});

test("closed shift success workflow exposes the required actions", () => {
  assert.match(page, /SHIFT CLOSED SUCCESSFULLY/);
  for (const label of ["View Z Report", "Print Z Report", "Return to Sales"]) {
    assert.match(page, new RegExp(label, "i"));
  }
  assert.match(page, /setClosedShift\(response\.data\)/);
});

test("shift management exposes all operational sections", () => {
  for (const label of ["Current Shift", "Open Shift", "Cash In / Cash Out", "Close Shift", "Shift History", "Z Reports"]) {
    assert.match(page, new RegExp(label));
  }
});

test("Z Reports use backend immutable JSON, PDF, and audited reprint APIs", () => {
  assert.match(page, /`\/shifts\/\$\{target\.id\}\/z-report`/);
  assert.match(page, /`\/shifts\/\$\{target\.id\}\/z-report\.pdf`/);
  assert.match(page, /params: \{ reprint: true \}/);
  assert.match(page, /responseType: "arraybuffer"/);
  assert.match(page, /Immutable closing snapshot/);
});

test("thermal printing uses backend layout at the configured paper width", () => {
  assert.match(app, /`\/shifts\/\$\{shift\.id\}\/z-report\/thermal`/);
  assert.match(app, /paper_width: printerConfig\.paperWidth/);
  assert.match(app, /authoritativeHtml/);
  assert.match(app, /buildEscPosPayload\(snapshot, printerConfig\)/);
});

test("Z Report dialogs remain responsive for handheld layouts", () => {
  assert.match(css, /@media\(max-width:900px\)/);
  assert.match(css, /@media\(max-width:720px\)/);
  assert.match(css, /\.pos-z-report-summary/);
  assert.match(css, /\.pos-z-report-pdf/);
  assert.match(css, /@media\(max-width:390px\)/);
  assert.match(css, /env\(safe-area-inset-top\)/);
  assert.match(css, /env\(safe-area-inset-bottom\)/);
});
