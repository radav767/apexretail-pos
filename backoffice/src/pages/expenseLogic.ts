export type ExpenseLogicRow = {
  company_id: string;
  branch_id: string;
  category_id: string;
  actor_user_id: string | null;
  employee_id: string | null;
  actor_id?: string | null;
  actor_name?: string | null;
  amount: string | number;
  payment_method: string;
  reference: string | null;
  description: string;
  occurred_at: string;
  category_name?: string | null;
};

export function expenseAmountError(value: string | number): string | null {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) return "Expense amount must be greater than zero.";
  return null;
}

export function expenseSummary(rows: ExpenseLogicRow[]) {
  return rows.reduce((summary, row) => {
    const amount = Number(row.amount || 0);
    summary.total += amount;
    if (row.payment_method === "cash") summary.cash += amount;
    if (row.payment_method === "card") summary.card += amount;
    if (row.payment_method === "mobile") summary.mobile += amount;
    return summary;
  }, { total: 0, cash: 0, card: 0, mobile: 0 });
}

export function expenseFinancialEffect(amountValue: string | number, paymentMethod: string) {
  const amount = Number(amountValue || 0);
  return {
    salesRevenueChange: 0,
    operatingExpensesChange: amount,
    netProfitChange: -amount,
    expectedCashMovementChange: paymentMethod === "cash" ? -amount : 0,
  };
}

export function categoryBreakdown(rows: ExpenseLogicRow[]) {
  const totals = new Map<string, { categoryId: string; name: string; amount: number }>();
  rows.forEach((row) => {
    const current = totals.get(row.category_id) || { categoryId: row.category_id, name: row.category_name || "Uncategorised", amount: 0 };
    current.amount += Number(row.amount || 0);
    totals.set(row.category_id, current);
  });
  return [...totals.values()].sort((left, right) => right.amount - left.amount || left.name.localeCompare(right.name));
}

export function matchesExpenseScope(row: ExpenseLogicRow, companyId: string, branchId = "") {
  return row.company_id === companyId && (!branchId || row.branch_id === branchId);
}
