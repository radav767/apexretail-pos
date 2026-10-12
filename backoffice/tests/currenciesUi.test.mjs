import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const settings = readFileSync(new URL("../src/pages/SettingsPage.tsx", import.meta.url), "utf8");
const panel = readFileSync(new URL("../src/pages/CurrencySettingsPanel.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/pages/currencies.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("Currencies is a dedicated Settings section while mobile navigation and logout remain intact", () => {
  assert.match(settings, /id: "currencies"/);
  assert.match(settings, /<CurrencySettingsPanel companyId=\{companyId\}/);
  assert.match(settings, /Manage currencies/);
  assert.match(app, /aria-expanded=\{mobileMenuOpen\}/);
  assert.match(app, /className="logout-nav-button"/);
});

test("currency administration uses scoped Phase 1 APIs and immutable rate history", () => {
  assert.match(panel, /`\/currencies\/\$\{companyId\}`/);
  assert.match(panel, /`\/currencies\/\$\{companyId\}\/rates\/history`/);
  assert.match(panel, /\/currencies\/rates/);
  assert.match(panel, /\/currencies\/configuration\/\$\{companyId\}/);
  assert.match(panel, /set-base/);
  assert.match(panel, /multi_currency_enabled/);
  assert.match(panel, /Cash/);
  assert.match(panel, /Card/);
  assert.match(panel, /Mobile/);
  assert.match(panel, /Immutable rate history/);
  assert.doesNotMatch(panel, /api\.delete/);
});

test("conversion preview avoids JavaScript Number arithmetic for rates", () => {
  assert.match(panel, /multiplyDecimalStrings\("10", rate/);
  assert.match(panel, /foreign_units_per_base: rate\.trim\(\)/);
  assert.doesNotMatch(panel, /Number\(rate\)/);
  assert.match(panel, /1 \{base\?\.code/);
  assert.match(panel, /10 \{base\?\.code/);
});

test("currency layouts cover desktop, tablet, 720px phone and 390px narrow phone", () => {
  assert.match(css, /grid-template-columns: repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(css, /@media \(max-width: 900px\)/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /@media \(max-width: 390px\)/);
  assert.match(css, /env\(safe-area-inset-bottom\)/);
  assert.match(css, /\.currency-table td::before/);
});
