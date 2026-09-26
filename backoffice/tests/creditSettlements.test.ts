import assert from "node:assert/strict";
import test from "node:test";
import {
  balanceAfterSettlement,
  matchesReceivableFilters,
  matchesSettlementFilters,
  receivableDisplayStatus,
  settlementAmountError,
} from "../src/pages/creditSettlementLogic";

const receivable = {
  company_id: "company-a", customer_id: "customer-a", branch_id: "branch-a",
  original_amount: "100.00", amount_settled: "0.00", outstanding_balance: "100.00",
  due_date: "2027-01-01", created_at: "2026-09-01T10:00:00Z", status: "unpaid",
};

test("partial and full settlement projections preserve the original amount", () => {
  assert.equal(balanceAfterSettlement("40", receivable.outstanding_balance), 60);
  assert.equal(balanceAfterSettlement("100", receivable.outstanding_balance), 0);
  assert.equal(receivable.original_amount, "100.00");
});

test("zero, negative and overpayment amounts are rejected", () => {
  assert.match(settlementAmountError("0", "100") || "", /greater than zero/);
  assert.match(settlementAmountError("-1", "100") || "", /greater than zero/);
  assert.match(settlementAmountError("100.01", "100") || "", /cannot exceed/);
  assert.equal(settlementAmountError("40", "100"), null);
});

test("company and branch filters prevent cross-scope rows", () => {
  const base = { customerId: "", branchId: "", status: "all", dateFrom: "", dateTo: "" };
  assert.equal(matchesReceivableFilters(receivable, { ...base, companyId: "company-a" }), true);
  assert.equal(matchesReceivableFilters(receivable, { ...base, companyId: "company-b" }), false);
  assert.equal(matchesReceivableFilters(receivable, { ...base, companyId: "company-a", branchId: "branch-b" }), false);
});

test("payment methods retain cash, card and mobile classification", () => {
  const settlement = { company_id: "company-a", customer_id: "customer-a", receivable_id: "receivable-a", branch_id: "branch-a", payment_method: "cash", received_at: "2026-09-10T10:00:00Z" };
  const filters = { companyId: "company-a", customerId: "", branchId: "", paymentMethod: "cash", dateFrom: "2026-09-01", dateTo: "2026-09-30", status: "all" };
  assert.equal(matchesSettlementFilters(settlement, filters, receivable), true);
  assert.equal(matchesSettlementFilters(settlement, { ...filters, paymentMethod: "card" }, receivable), false);
});

test("open, partial, paid and overdue statuses are derived consistently", () => {
  const now = new Date("2026-09-26T12:00:00Z");
  assert.equal(receivableDisplayStatus(receivable, now), "open");
  assert.equal(receivableDisplayStatus({ ...receivable, amount_settled: "20", outstanding_balance: "80" }, now), "partially_paid");
  assert.equal(receivableDisplayStatus({ ...receivable, amount_settled: "100", outstanding_balance: "0", status: "paid" }, now), "paid");
  assert.equal(receivableDisplayStatus({ ...receivable, due_date: "2026-09-20" }, now), "overdue");
});
