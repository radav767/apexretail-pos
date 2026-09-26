import assert from "node:assert/strict";
import test from "node:test";
import { categoryBreakdown, expenseAmountError, expenseFinancialEffect, expenseSummary, matchesExpenseScope } from "../src/pages/expenseLogic";

const rows = [
  { company_id: "company-a", branch_id: "branch-a", category_id: "cat-a", actor_user_id: "user-a", employee_id: null, amount: "20", payment_method: "cash", reference: "CASH-1", description: "Fuel", occurred_at: "2026-09-01T10:00:00Z", category_name: "Travel" },
  { company_id: "company-a", branch_id: "branch-a", category_id: "cat-b", actor_user_id: "user-a", employee_id: null, amount: "30", payment_method: "card", reference: "CARD-1", description: "Power", occurred_at: "2026-09-02T10:00:00Z", category_name: "Utilities" },
  { company_id: "company-a", branch_id: "branch-b", category_id: "cat-b", actor_user_id: null, employee_id: "employee-a", amount: "40", payment_method: "mobile", reference: "MOB-1", description: "Data", occurred_at: "2026-09-03T10:00:00Z", category_name: "Utilities" },
];

test("expense amounts must be positive", () => {
  assert.match(expenseAmountError("0") || "", /greater than zero/);
  assert.match(expenseAmountError("-1") || "", /greater than zero/);
  assert.equal(expenseAmountError("0.01"), null);
});

test("cash, card and mobile expenses retain payment classification", () => {
  assert.deepEqual(expenseSummary(rows), { total: 90, cash: 20, card: 30, mobile: 40 });
});

test("expenses reduce net profit, cash movement and never sales revenue", () => {
  assert.deepEqual(expenseFinancialEffect("20", "cash"), { salesRevenueChange: 0, operatingExpensesChange: 20, netProfitChange: -20, expectedCashMovementChange: -20 });
  assert.equal(expenseFinancialEffect("30", "card").expectedCashMovementChange, 0);
});

test("company and branch scoping excludes foreign rows", () => {
  assert.equal(matchesExpenseScope(rows[0], "company-a", "branch-a"), true);
  assert.equal(matchesExpenseScope(rows[0], "company-b"), false);
  assert.equal(matchesExpenseScope(rows[0], "company-a", "branch-b"), false);
});

test("category breakdown aggregates and sorts selected expenses", () => {
  assert.deepEqual(categoryBreakdown(rows), [
    { categoryId: "cat-b", name: "Utilities", amount: 70 },
    { categoryId: "cat-a", name: "Travel", amount: 20 },
  ]);
});
