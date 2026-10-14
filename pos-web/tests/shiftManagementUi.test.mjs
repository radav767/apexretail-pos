import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../src/ShiftManagementPage.tsx", import.meta.url), "utf8");
const modulePage = readFileSync(new URL("../src/PosModulePage.tsx", import.meta.url), "utf8");
const formatter = readFileSync(new URL("../src/printing/receiptFormatter.ts", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/shift-management.css", import.meta.url), "utf8");

test("Shift Management is reachable from the cashier menu and module router", () => {
  assert.match(app, /showPosModule\("Shift Management"\)/);
  assert.match(app, /"Shift Management".*"Products"/);
  assert.match(modulePage, /activeModule === "Shift Management"/);
  assert.match(modulePage, /<ShiftManagementPage/);
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
  for (const text of ["Opening", "Current expected cash", "Counted", "Variance", "Recent shifts", "Cash movement history"]) {
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

test("tablet, phone, narrow-phone, and safe-area layouts are defined", () => {
  assert.match(css, /@media\(max-width:900px\)/);
  assert.match(css, /@media\(max-width:720px\)/);
  assert.match(css, /@media\(max-width:390px\)/);
  assert.match(css, /env\(safe-area-inset-top\)/);
  assert.match(css, /env\(safe-area-inset-bottom\)/);
});
