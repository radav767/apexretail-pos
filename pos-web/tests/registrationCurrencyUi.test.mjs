import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");

test("registration loads the authoritative supported-currency catalog", () => {
  assert.match(appSource, /api\.get\("\/auth\/registration-currencies"\)/);
  assert.match(appSource, /const \[baseCurrencyCode, setBaseCurrencyCode\] = useState\(""\)/);
  assert.match(appSource, /<option value="">/);
  assert.match(appSource, /Select base currency/);
});

test("registration refuses to submit without an explicit base currency", () => {
  assert.match(appSource, /if \(!selectedCurrency\)/);
  assert.match(appSource, /base currency: Select a base currency/);
  assert.match(appSource, /disabled=\{authLoading \|\| registrationCurrenciesLoading \|\| Boolean\(registrationCurrenciesError\)\}/);
});

test("registration sends the complete server-approved currency definition", () => {
  assert.match(appSource, /base_currency_code: selectedCurrency\.code/);
  assert.match(appSource, /base_currency_symbol: selectedCurrency\.symbol/);
  assert.match(appSource, /base_currency_decimal_places: selectedCurrency\.decimal_places/);
  assert.match(appSource, /cannot be changed after financial activity begins/);
});
