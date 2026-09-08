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
