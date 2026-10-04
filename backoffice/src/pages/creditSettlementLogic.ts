export type ReceivableStatus = "open" | "partially_paid" | "paid" | "overdue";

export type ReceivableFilterRow = {
  company_id: string;
  customer_id: string;
  branch_id: string;
  original_amount: string | number;
  amount_settled: string | number;
  outstanding_balance: string | number;
  due_date: string;
  created_at: string;
  status: string;
};

export type SettlementFilterRow = {
  company_id: string;
  customer_id: string;
  receivable_id: string;
  branch_id: string;
  payment_method: string;
  received_at: string;
  actor_id?: string | null;
  actor_name?: string | null;
};

export function settlementAmountError(value: string | number, outstanding: string | number): string | null {
  const payment = Number(value);
  const balance = Number(outstanding);
  if (!Number.isFinite(payment) || payment <= 0) return "Settlement amount must be greater than zero.";
  if (payment > balance) return "Settlement amount cannot exceed the outstanding balance.";
  return null;
}

export function balanceAfterSettlement(value: string | number, outstanding: string | number): number {
  const error = settlementAmountError(value, outstanding);
  if (error) return Number(outstanding);
  return Math.max(0, Number((Number(outstanding) - Number(value)).toFixed(2)));
}

export function receivableDisplayStatus(receivable: ReceivableFilterRow, today = new Date()): ReceivableStatus {
  if (Number(receivable.outstanding_balance) <= 0 || receivable.status.toLowerCase() === "paid") return "paid";
  const due = new Date(`${receivable.due_date}T23:59:59`);
  if (due.getTime() < today.getTime()) return "overdue";
  if (Number(receivable.amount_settled) > 0 || receivable.status.toLowerCase() === "partially_paid") return "partially_paid";
  return "open";
}

export function inDateRange(value: string, dateFrom: string, dateTo: string): boolean {
  const date = value.slice(0, 10);
  return (!dateFrom || date >= dateFrom) && (!dateTo || date <= dateTo);
}

export function matchesReceivableFilters(
  receivable: ReceivableFilterRow,
  filters: { companyId: string; customerId: string; branchId: string; status: string; dateFrom: string; dateTo: string },
  today = new Date(),
): boolean {
  if (receivable.company_id !== filters.companyId) return false;
  if (filters.customerId && receivable.customer_id !== filters.customerId) return false;
  if (filters.branchId && receivable.branch_id !== filters.branchId) return false;
  const status = receivableDisplayStatus(receivable, today);
  if (filters.status === "outstanding" && status === "paid") return false;
  if (filters.status && filters.status !== "all" && filters.status !== "outstanding" && status !== filters.status) return false;
  return inDateRange(receivable.created_at, filters.dateFrom, filters.dateTo);
}

export function matchesSettlementFilters(
  settlement: SettlementFilterRow,
  filters: { companyId: string; customerId: string; branchId: string; paymentMethod: string; dateFrom: string; dateTo: string; status: string },
  receivable?: ReceivableFilterRow,
  today = new Date(),
): boolean {
  if (settlement.company_id !== filters.companyId) return false;
  if (filters.customerId && settlement.customer_id !== filters.customerId) return false;
  if (filters.branchId && settlement.branch_id !== filters.branchId) return false;
  if (filters.paymentMethod && settlement.payment_method !== filters.paymentMethod) return false;
  if (!inDateRange(settlement.received_at, filters.dateFrom, filters.dateTo)) return false;
  if (filters.status && filters.status !== "all") {
    if (!receivable) return false;
    const status = receivableDisplayStatus(receivable, today);
    if (filters.status === "outstanding") return status !== "paid";
    return status === filters.status;
  }
  return true;
}
