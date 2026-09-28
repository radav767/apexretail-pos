import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const reports = readFileSync(new URL("../src/pages/ReportsPage.tsx", import.meta.url), "utf8");

test("financial reporting uses the authoritative summary endpoint", () => {
  assert.match(reports, /\/reports\/financial-summary\/\$\{companyId\}/);
  for (const label of ["Operating Expenses", "Net Profit", "Cash Settlements", "Cash Expenses", "Expected Cash Movement"]) {
    assert.ok(reports.includes(label));
  }
});

test("expense and cash treatment is explicit", () => {
  assert.match(reports, /excluded from sales revenue/);
  assert.match(reports, /Cash sales plus settlements less cash expenses/);
});
