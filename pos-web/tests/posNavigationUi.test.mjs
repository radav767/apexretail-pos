import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const navigation = readFileSync(new URL("../src/components/PosNavigation.tsx", import.meta.url), "utf8");
const header = readFileSync(new URL("../src/components/PosSessionHeader.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const theme = readFileSync(new URL("../src/premium-theme.css", import.meta.url), "utf8");

test("POS navigation follows the approved hierarchy without numbered controls", () => {
  const labels = ["Sales", "Sales Management", "Customers", "Expenses", "Products", "Inventory", "Reports", "Settings"];
  let cursor = -1;
  for (const label of labels) {
    const next = navigation.indexOf(`label: "${label}"`, cursor + 1);
    assert.ok(next > cursor, `${label} is missing or out of order`);
    cursor = next;
  }
  for (const child of ["Transaction History", "Shift Management", "Credit Settlement", "Goods Received (GRN)", "Stock Adjustments", "Stock Transfers", "Sales Summary", "Sales Reports", "Top Selling Products"]) {
    assert.ok(navigation.includes(child), `missing submenu ${child}`);
  }
  assert.doesNotMatch(navigation, />\s*\d+\s*</);
});

test("navigation remains permission-aware and preserves existing module routing", () => {
  assert.match(navigation, /canManageProducts/);
  assert.match(navigation, /canManageInventory/);
  assert.match(navigation, /canManageExpenses/);
  assert.match(navigation, /canManageCredit/);
  assert.match(app, /onNavigate=\{showPosModule\}/);
  assert.match(app, /onBackoffice=\{openBackoffice\}/);
  assert.match(app, /onLogout=\{logout\}/);
});

test("header uses live session, location, shift and clock values", () => {
  assert.match(header, /cashierName/);
  assert.match(header, /shopName/);
  assert.match(header, /branchName/);
  assert.match(header, /shiftStatus/);
  assert.match(header, /setInterval/);
  assert.match(app, /localStorage\.getItem\("shop_name"\)/);
  assert.match(app, /currentShift\?\.status/);
});

test("dark-green shell is responsive without horizontal overflow", () => {
  assert.match(theme, /--brand-leaf: #07583b/);
  assert.match(theme, /--brand-leaf-fresh: #16864d/);
  assert.match(theme, /\.pos-nav-children/);
  assert.match(theme, /@media \(min-width: 1024px\)/);
  assert.match(theme, /@media \(max-width: 720px\)/);
  assert.match(theme, /overflow-x: hidden/);
});
