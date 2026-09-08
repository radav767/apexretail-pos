import assert from "node:assert/strict";
import { applyDiscounts } from "../src/discounts.ts";

const line = { selling_price: "4.00", quantity: "0.250", line_total: "1.00" };
assert.deepEqual(applyDiscounts([line]), { items: [line], discount_amount: "0.00", total: "1.00" });
assert.equal(applyDiscounts([{ ...line, line_discount: "0.20" }]).items[0].line_total, "0.80");
const sale = applyDiscounts([line, line, line], "0.10");
assert.deepEqual(sale.items.map(x => x.line_total), ["0.97", "0.97", "0.96"]);
assert.equal(sale.discount_amount, "0.10");
assert.equal(sale.total, "2.90");
assert.equal(applyDiscounts([{ ...line, line_discount: "0.20" }], "0.10").discount_amount, "0.30");
for (const value of ["-1", "NaN", "Infinity", "0.001", "1", "2"]) {
  assert.throws(() => applyDiscounts([line], value));
}
assert.throws(() => applyDiscounts([{ ...line, line_discount: "1" }]));
console.log("PASS: no discount, line discount, sale allocation, combined discounts, invalid amounts");
