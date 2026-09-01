import assert from "node:assert/strict";
import test from "node:test";

import {
  canRefundSale,
  canViewSaleReceipt,
  isRefundableSale,
  saleStatusLabel,
  validateRefundQuantity,
} from "../src/salesHistory.ts";

test("owners and administrators can view, reprint, and refund", () => {
  for (const role of ["owner", "administrator", "admin"]) {
    assert.equal(canViewSaleReceipt({ role }), true);
    assert.equal(canRefundSale({ role }), true);
  }
});

test("employee actions require their specific permissions", () => {
  const salesOnly = {
    role: "cashier",
    permissions: { sales: true, refunds: false },
  };
  const refundsOnly = {
    role: "cashier",
    permissions: { sales: false, refunds: true },
  };

  assert.equal(canViewSaleReceipt(salesOnly), true);
  assert.equal(canRefundSale(salesOnly), false);
  assert.equal(canViewSaleReceipt(refundsOnly), false);
  assert.equal(canRefundSale(refundsOnly), true);
});

test("only completed original sales with remaining state are refundable", () => {
  assert.equal(isRefundableSale({ status: "completed" }), true);
  assert.equal(isRefundableSale({ status: "partially_refunded" }), true);
  assert.equal(isRefundableSale({ status: "refunded" }), false);
  assert.equal(
    isRefundableSale({
      status: "refunded",
      original_sale_id: "original-sale",
    }),
    false,
  );
});

test("partial and full refund states have explicit labels", () => {
  assert.equal(
    saleStatusLabel({ status: "partially_refunded" }),
    "Partially refunded",
  );
  assert.equal(
    saleStatusLabel({ status: "refunded" }),
    "Fully refunded",
  );
  assert.equal(
    saleStatusLabel({ status: "refunded", original_sale_id: "sale" }),
    "Refund transaction",
  );
});

test("refund quantities cannot exceed the remaining quantity", () => {
  assert.equal(validateRefundQuantity("1.5", "2.000"), null);
  assert.match(
    validateRefundQuantity("2.001", "2.000") || "",
    /exceeds/,
  );
  assert.match(validateRefundQuantity("0", "2") || "", /greater/);
});
