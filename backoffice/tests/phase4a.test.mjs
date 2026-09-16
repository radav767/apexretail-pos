import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const sales = readFileSync(new URL("../src/pages/SalesHistoryPage.tsx", import.meta.url), "utf8");
const inventory = readFileSync(new URL("../src/pages/InventoryPage.tsx", import.meta.url), "utf8");
const products = readFileSync(new URL("../src/pages/ProductsPage.tsx", import.meta.url), "utf8");
const reportsCss = readFileSync(new URL("../src/pages/reports.css", import.meta.url), "utf8");
const pos = readFileSync(new URL("../../pos-web/src/PosModulePage.tsx", import.meta.url), "utf8");
const backofficeApi = readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8");
const posApi = readFileSync(new URL("../../pos-web/src/api/client.ts", import.meta.url), "utf8");
const backendMain = readFileSync(new URL("../../backend/app/main.py", import.meta.url), "utf8");
const backofficeApp = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const posApp = readFileSync(new URL("../../pos-web/src/App.tsx", import.meta.url), "utf8");

test("Sales History has every required view and preserves filters in one state", () => {
  for (const label of ["Individual sales and receipts","Sales by cashier","Sales by product","Sales by category","Sales by payment type","Sales by shop/branch","Credit sales","Refunds and cancellations"]) assert.ok(sales.includes(label));
  for (const filter of ["date_from","shop_id","branch_id","cashier_id","product_id","category_id","payment_method"]) assert.ok(sales.includes(filter));
  assert.ok(sales.includes("Export CSV")); assert.ok(sales.includes("Previous")); assert.ok(sales.includes("Next"));
});

test("inventory labels current-price projections and POS does not show monetary stock valuation", () => {
  for (const label of ["Quantity on hand","Stock selling value","Stock cost value","Projected gross profit","Margin","not historical realized profit"]) assert.ok(inventory.includes(label));
  assert.ok(!pos.includes('title="Stock Value"'));
  assert.ok(!pos.includes('>Cost Value</th>'));
  assert.ok(!inventory.includes('api.get(`/inventory/valuation/${companyId}`)'));
  assert.ok(products.includes('cost_price: form.cost_price || null'));
  assert.ok(pos.includes('cost_price: productForm.cost_price || null'));
});

test("Sales History markup and CSS remain usable at required viewport widths", () => {
  assert.match(sales, /<label>Report view<select aria-label="Report view"/);
  assert.match(reportsCss, /\.reports-filter-grid\s*{[^}]*repeat\(auto-fit, minmax\(165px, 1fr\)\)/s);
  assert.match(reportsCss, /\.reports-table-wrapper\s*{[^}]*overflow-x:\s*auto/s);

  for (const { width, height } of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
    { width: 320, height: 568 },
  ]) {
    const contentWidth = width <= 560 ? width - 36 : width - 48;
    assert.ok(contentWidth > 0, `${width}x${height} retains a positive content width`);
    assert.ok(height >= 568, `${width}x${height} permits vertical document scrolling`);
    if (width <= 560) {
      assert.match(reportsCss, /@media \(max-width: 560px\)[\s\S]*?padding:\s*18px/);
      assert.match(reportsCss, /@media \(max-width: 560px\)[\s\S]*?grid-template-columns:\s*1fr/);
    }
  }
});

test("local previews can override the API without changing the production default", () => {
  for (const client of [backofficeApi, posApi]) {
    assert.ok(client.includes("import.meta.env.VITE_API_BASE_URL"));
    assert.ok(client.includes('"https://api.apexpos.cloud/api"'));
    assert.ok(client.indexOf("VITE_API_BASE_URL") < client.indexOf("https://api.apexpos.cloud/api"));
  }
  assert.ok(backendMain.includes('"http://localhost:5173"'));
  assert.ok(backendMain.includes('"http://localhost:5174"'));
  assert.ok(backofficeApp.includes('get("page")'));
  assert.ok(posApp.includes('get("module")'));
});
