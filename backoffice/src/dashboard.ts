export type DashboardRangeKey =
  | "today"
  | "yesterday"
  | "last_7_days"
  | "last_month"
  | "custom";

export type DashboardMetric = {
  available: boolean;
  value: string | null;
  reason: string | null;
  missing_persistence: string | null;
};

export type DashboardPhase2Summary = {
  range_key: DashboardRangeKey;
  date_from: string;
  date_to: string;
  reporting_timezone: string;
  shop_id: string | null;
  currency_symbol: string;
  decimal_places: number;
  shops: Array<{ id: string; name: string }>;
  metrics: {
    gross_sales: DashboardMetric;
    net_sales: DashboardMetric;
    cost_of_sales: DashboardMetric;
    gross_profit: DashboardMetric;
    discounts: DashboardMetric;
    refunds: DashboardMetric;
  };
};

export type DashboardFinancialSummary = {
  gross_sales: string | number;
  net_sales: string | number;
  cost_of_sales: string | number;
  gross_profit: string | number;
  discounts: string | number;
  operating_expenses: string | number;
  net_profit: string | number;
  cash_sales: string | number;
  card_sales: string | number;
  mobile_sales: string | number;
  credit_sales: string | number;
  credit_settlements: string | number;
  outstanding_receivables: string | number;
  cash_settlements: string | number;
  card_settlements: string | number;
  mobile_settlements: string | number;
  cash_expenses: string | number;
  card_expenses: string | number;
  mobile_expenses: string | number;
  expected_cash_movement: string | number;
};

export type DashboardChange = {
  available: boolean;
  amount: string | null;
  percentage: string | null;
  reason: string | null;
};

export type DashboardRankedRow = {
  id: string | null;
  name: string;
  revenue: string;
  quantity: string;
  gross_profit: string;
};

export type DashboardBreakdownRow = {
  key: string;
  name: string;
  transactions: number;
  gross_sales: string;
  refunds: string;
  net_sales: string;
  gross_profit: string;
  discounts: DashboardMetric;
};

export type DashboardPhase3Summary = DashboardPhase2Summary & {
  financial_summary: DashboardFinancialSummary;
  granularity: "day" | "week" | "month";
  comparison: {
    date_from: string;
    date_to: string;
    metrics: Record<string, DashboardChange>;
  };
  trends: Array<{
    period_start: string;
    period_end: string;
    metrics: DashboardPhase2Summary["metrics"];
  }>;
  top_products: DashboardRankedRow[];
  top_categories: DashboardRankedRow[];
  payment_methods: DashboardBreakdownRow[];
  shop_breakdown: DashboardBreakdownRow[];
  cashier_breakdown: DashboardBreakdownRow[];
  discount_breakdown: DashboardBreakdownRow[];
  refund_breakdown: DashboardBreakdownRow[];
};

export type DashboardMetricKey = keyof DashboardPhase2Summary["metrics"];

export type DashboardDimension =
  | "product"
  | "category"
  | "payment"
  | "shop"
  | "cashier"
  | "discount"
  | "refund";

export type DashboardDrilldownRequest = {
  title: string;
  metric: DashboardMetricKey;
  dimension?: DashboardDimension;
  dimensionKey?: string;
  dateFrom?: string;
  dateTo?: string;
};

export type DashboardDrilldown = {
  total: number;
  limit: number;
  offset: number;
  metrics: DashboardPhase2Summary["metrics"];
  rows: Array<{
    id: string;
    receipt_number: string;
    created_at: string;
    shop_name: string;
    cashier_name: string;
    payment_method: string;
    status: string;
    gross_sales: string;
    refunds: string;
    net_sales: string;
    gross_profit: string;
    discounts: DashboardMetric;
  }>;
};

export const dashboardRangeOptions: Array<{
  key: DashboardRangeKey;
  label: string;
}> = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "last_7_days", label: "Last 7 days" },
  { key: "last_month", label: "Last month" },
  { key: "custom", label: "Custom date range" },
];

export function formatDashboardMoney(
  metric: DashboardMetric,
  currencySymbol: string,
  decimalPlaces: number,
): string {
  if (!metric.available || metric.value === null) {
    return "Unavailable";
  }

  return `${currencySymbol}${Number(metric.value).toFixed(decimalPlaces)}`;
}
