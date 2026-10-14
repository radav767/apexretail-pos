import assert from "node:assert/strict";
import test from "node:test";
import {
  convertBaseToForeign,
  convertForeignToBase,
  isCurrencyAmountAtLeast,
  subtractCurrencyAmounts,
} from "../src/decimal.ts";
import type { PrinterConfig, ReceiptSnapshot } from "../src/printing/types.ts";
import { buildEscPosPayload, buildReceiptHtml } from "../src/printing/receiptFormatter.ts";

test("foreign conversion uses exact decimal arithmetic and configured precision", () => {
  assert.equal(convertBaseToForeign("10.00", 2, "18.5000000000", 2), "185.00");
  assert.equal(convertBaseToForeign("0.05", 2, "1.5", 2), "0.08");
  assert.equal(convertBaseToForeign("10.000", 3, "0.3333333333", 0), "3");
  assert.equal(convertForeignToBase("185.00", 2, "18.50", 2), "10.00");
  assert.equal(convertForeignToBase("3", 0, "0.3333333333", 3), "9.000");
});

test("cash tender and change stay in their physical currency", () => {
  const due = convertBaseToForeign("10.00", 2, "18.50", 2);
  assert.equal(isCurrencyAmountAtLeast("200.00", due, 2), true);
  assert.equal(subtractCurrencyAmounts("200.00", due, 2), "15.00");
  assert.equal(isCurrencyAmountAtLeast("184.99", due, 2), false);
});

test("invalid rates and excess input precision fail closed", () => {
  assert.throws(() => convertBaseToForeign("10.00", 2, "0", 2));
  assert.throws(() => convertBaseToForeign("10.00", 2, "-1", 2));
  assert.throws(() => convertBaseToForeign("10.001", 2, "2", 2));
});

test("thermal and browser receipts show immutable foreign payment snapshots", () => {
  const receipt: ReceiptSnapshot = {
    id: "sale-1", receipt_number: "R-1", company_id: "company-1",
    business_name: "Test Shop", created_at: "2026-10-14T10:00:00Z",
    total_amount: "10.00", amount_received: "10.00", change_due: "0.00",
    base_currency_code: "USD", payment_currency_code: "ZAR",
    exchange_rate_snapshot: "18.50", payment_amount_original: "185.00",
    tendered_amount_original: "200.00", change_amount_original: "15.00",
    payment_method: "cash", status: "completed", cashier_name: "Cashier A",
    shift_id: "shift-1", items: [],
  };
  const config: PrinterConfig = {
    enabled: true, connectionType: "system", selectedPrinterId: "",
    selectedPrinterName: "", paperWidth: "58mm", copies: 1, autoPrint: false,
    cutPaper: false,
  };
  const html = buildReceiptHtml(receipt, config);
  const thermal = new TextDecoder().decode(buildEscPosPayload(receipt, config));
  for (const rendered of [html, thermal]) {
    assert.match(rendered, /USD/);
    assert.match(rendered, /ZAR/);
    assert.match(rendered, /18\.50/);
    assert.match(rendered, /185\.00/);
    assert.match(rendered, /200\.00/);
    assert.match(rendered, /15\.00/);
    assert.match(rendered, /Cashier A/);
    assert.match(rendered, /shift-1/);
  }
});
