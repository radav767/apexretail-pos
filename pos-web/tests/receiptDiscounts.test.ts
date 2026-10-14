import assert from "node:assert/strict";
import { buildEscPosPayload, buildReceiptHtml } from "../src/printing/receiptFormatter.ts";
import type { PrinterConfig, ReceiptSnapshot } from "../src/printing/types.ts";

const config: PrinterConfig = {
  enabled: true,
  connectionType: "system",
  selectedPrinterId: "",
  selectedPrinterName: "",
  paperWidth: "80mm",
  copies: 1,
  autoPrint: false,
  cutPaper: false,
};

const base: ReceiptSnapshot = {
  id: "sale-1",
  receipt_number: "APR-1",
  company_id: "company-1",
  business_name: "ApexRetail",
  created_at: "2026-09-14T00:00:00Z",
  total_amount: "7.00",
  amount_received: "7.00",
  change_due: "0.00",
  payment_method: "cash",
  shift_id: "phase3-test-shift",
  status: "completed",
  items: [{
    name: "Coffee",
    quantity: "2",
    unit_price: "5.00",
    line_total: "7.00",
    line_discount_amount: "2.00",
  }],
  discount_amount: "3.00",
  sale_discount_amount: "1.00",
};

function count(haystack: string, needle: string) {
  return haystack.split(needle).length - 1;
}

for (const rendered of [
  buildReceiptHtml(base, config),
  new TextDecoder().decode(buildEscPosPayload(base, config)),
]) {
  assert.equal(count(rendered, "Line discount"), 1);
  assert.equal(count(rendered, "Sale-wide discount"), 1);
  assert.equal(count(rendered, "Discount (combined)"), 0);
  assert.match(rendered, /Items before discounts/);
  assert.match(rendered, /10\.00/);
  assert.match(rendered, /7\.00/);
  assert.match(rendered, /Shift: phase3-test-shift/);
}

const lineOnly = { ...base, total_amount: "8.00", discount_amount: "2.00", sale_discount_amount: "0.00" };
const lineHtml = buildReceiptHtml(lineOnly, config);
assert.equal(count(lineHtml, "Line discount"), 1);
assert.equal(count(lineHtml, "Sale-wide discount"), 0);

const saleOnly = {
  ...base,
  total_amount: "9.00",
  discount_amount: "1.00",
  sale_discount_amount: "1.00",
  items: [{ ...base.items[0], line_total: "9.00", line_discount_amount: "0.00" }],
};
const saleHtml = buildReceiptHtml(saleOnly, config);
assert.equal(count(saleHtml, "Line discount"), 0);
assert.equal(count(saleHtml, "Sale-wide discount"), 1);

const legacy = { ...base, sale_discount_amount: null, items: [{ ...base.items[0], line_discount_amount: null }] };
const legacyHtml = buildReceiptHtml(legacy, config);
assert.equal(count(legacyHtml, "Discount (combined)"), 1);
assert.equal(count(legacyHtml, "Line discount"), 0);
assert.equal(count(legacyHtml, "Sale-wide discount"), 0);

console.log("PASS: checkout, archived/reprint formatter, single and combined discount labels render once");
