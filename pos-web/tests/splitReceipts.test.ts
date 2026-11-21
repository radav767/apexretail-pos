import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { buildReceiptHtml, buildEscPosPayload } from "../src/printing/receiptFormatter.ts";
import { splitPaymentRows } from "../src/printing/splitReceipt.ts";
import type { PrinterConfig, ReceiptSnapshot } from "../src/printing/types.ts";

const fixtures = JSON.parse(readFileSync(process.env.PHASE11_SPLIT_RECEIPT_FIXTURES!, "utf8")) as Record<string, ReceiptSnapshot>;
const base: PrinterConfig = { enabled: true, connectionType: "system", selectedPrinterId: "", selectedPrinterName: "", paperWidth: "80mm", copies: 1, autoPrint: false, cutPaper: false };
for (const [kind, snapshot] of Object.entries(fixtures)) {
  const rows = splitPaymentRows(snapshot.split_accounting, snapshot.total_amount, snapshot.payment_method);
  assert.deepEqual(rows, (snapshot.split_accounting as unknown as { rows: string[][] }).rows, "API/queue/browser/thermal disclosure must agree");
  for (const paperWidth of ["58mm", "80mm"] as const) {
    const config = { ...base, paperWidth };
    const html = buildReceiptHtml(snapshot, config), thermal = new TextDecoder().decode(buildEscPosPayload(snapshot, config));
    for (const [label, value] of rows) {
      assert.ok(html.includes(label) && html.includes(value), `${kind}/${paperWidth}: ${label}/${value}`);
      assert.ok(thermal.includes(value), `${kind}/${paperWidth} retains exact original amount`);
    }
    assert.ok(!html.includes("<span>Paid</span>"), "no scalar paid amount for mixed/debt allocations");
    assert.ok(!html.includes("Split detail unavailable"));
    if (process.env.PHASE11_SPLIT_HTML_DIR) writeFileSync(`${process.env.PHASE11_SPLIT_HTML_DIR}/${kind}-${paperWidth}.html`, html);
  }
  const malformed = structuredClone(snapshot);malformed.split_accounting!.legs[0].applied_base = "999.00";
  assert.equal(splitPaymentRows(malformed.split_accounting, malformed.total_amount, malformed.payment_method)[0][1], "UNAVAILABLE");
  const missing = { ...snapshot, split_accounting: undefined };
  const html = buildReceiptHtml(missing, base);assert.ok(html.includes("Review original receipt") && !html.includes("<span>Paid</span>"));
  const unsafe=structuredClone(snapshot);unsafe.split_accounting!.legs[0].currency_code='<img src=x>';
  const safeHtml=buildReceiptHtml(unsafe,base);assert.ok(safeHtml.includes('UNAVAILABLE') && !safeHtml.includes('<img src=x>'));
}
const large=structuredClone(fixtures.original);large.total_amount='9999999999.99';
const cash=large.split_accounting!.legs.find(r=>r.method==='cash')!;cash.applied_base='9999999995.99';cash.applied_original='9999999995.99';cash.tendered_original='9999999997.99';cash.change_original='2.00';
const longPrint=new TextDecoder().decode(buildEscPosPayload(large,{...base,paperWidth:'58mm'}));
assert.ok(longPrint.includes('Original unpaid credit'),'narrow output cannot truncate credit identification');
assert.ok(longPrint.includes('9999999995.99 USD'),'narrow output cannot truncate original amount');
console.log("PASS: real persisted API/queue disclosure equals 58/80mm HTML and thermal amounts; incomplete split evidence fails closed");
