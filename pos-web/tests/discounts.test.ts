import assert from "node:assert/strict";
import { applyDiscounts } from "../src/discounts.ts";

const line = { selling_price: "4.00", quantity: "0.250", line_total: "1.00" };
const none = applyDiscounts([line]);
assert.equal(none.items[0].line_total, "1.00");
assert.equal(none.items[0].line_discount_amount, "0.00");
assert.equal(none.line_discount_total, "0.00");
assert.equal(none.sale_discount_amount, "0.00");
assert.equal(none.discount_amount, "0.00");
assert.equal(none.total, "1.00");
const lineOnly = applyDiscounts([{ ...line, line_discount: "0.20" }]);
assert.equal(lineOnly.items[0].line_total, "0.80");
assert.equal(lineOnly.items[0].line_discount_amount, "0.20");
assert.equal(lineOnly.line_discount_total, "0.20");
assert.equal(lineOnly.sale_discount_amount, "0.00");
assert.equal(lineOnly.discount_amount, "0.20");
assert.equal(lineOnly.total, "0.80");
const sale = applyDiscounts([line, line, line], "0.10");
assert.deepEqual(sale.items.map(x => x.line_total), ["0.97", "0.97", "0.96"]);
assert.equal(sale.discount_amount, "0.10");
assert.equal(sale.line_discount_total, "0.00");
assert.equal(sale.sale_discount_amount, "0.10");
assert.equal(sale.total, "2.90");
const combined = applyDiscounts([{ ...line, line_discount: "0.20" }], "0.10");
assert.equal(combined.items[0].line_total, "0.70");
assert.equal(combined.items[0].line_discount_amount, "0.20");
assert.equal(combined.line_discount_total, "0.20");
assert.equal(combined.sale_discount_amount, "0.10");
assert.equal(combined.discount_amount, "0.30");
assert.equal(combined.total, "0.70");
for (const value of ["-1", "NaN", "Infinity", "0.001", "1", "2"]) {
  assert.throws(() => applyDiscounts([line], value));
}
assert.throws(() => applyDiscounts([{ ...line, line_discount: "1" }]));
console.log("PASS: no discount, single line discount, sale-wide allocation, combined discounts, exact totals, invalid amounts");
