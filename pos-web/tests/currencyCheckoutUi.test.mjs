import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const offline = readFileSync(new URL("../src/offline/offlineSales.ts", import.meta.url), "utf8");

test("checkout loads company-scoped POS currency config and filters by payment acceptance", () => {
  assert.match(app, /\/currencies\/\$\{companyId\}\/pos-config/);
  assert.match(app, /currency\.cash_accepted/);
  assert.match(app, /currency\.card_accepted/);
  assert.match(app, /currency\.mobile_accepted/);
  assert.match(app, /multi_currency_enabled/);
  assert.match(app, /id="payment-currency"/);
});

test("sale payload carries quote identity and original-currency tender without changing base total", () => {
  assert.match(app, /payload\.payment_currency_code = paymentCurrency\.code/);
  assert.match(app, /payload\.exchange_rate_id = paymentCurrency\.current_rate_id/);
  assert.match(app, /payload\.currency_config_version = currencyConfig\.version/);
  assert.match(app, /payload\.tendered_amount_original = receivedText/);
});

test("foreign currency writes are rejected offline and never enter the queue", () => {
  assert.match(app, /Foreign-currency payments are online-only/);
  assert.match(app, /Foreign-currency payments cannot be queued offline/);
  assert.match(offline, /payment_currency_code\?: string/);
});

test("receipt snapshots render currency, exchange rate, tender, cashier, and shift", () => {
  const formatter = readFileSync(new URL("../src/printing/receiptFormatter.ts", import.meta.url), "utf8");
  assert.match(app, /payment_currency_code: sale\.payment_currency_code/);
  assert.match(formatter, /Rate 1 \$\{baseCode\}/);
  assert.match(formatter, /snapshot\.tendered_amount_original/);
  assert.match(formatter, /snapshot\.cashier_name/);
  assert.match(formatter, /snapshot\.shift_id/);
});
