import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import {
  formatDashboardMoney,
  type DashboardMetric,
  type DashboardPhase3Summary,
} from "../src/dashboard.js";
import { DashboardPanel } from "../src/DashboardPanel.js";
import { DashboardDrilldownDialog } from "../src/DashboardDrilldownDialog.js";


const available = (value: string): DashboardMetric => ({
  available: true,
  value,
  reason: null,
  missing_persistence: null,
});

const summary: DashboardPhase3Summary = {
  range_key: "custom",
  date_from: "2026-08-01",
  date_to: "2026-08-31",
  reporting_timezone: "Africa/Harare",
  shop_id: "shop-2",
  currency_symbol: "Z$",
  decimal_places: 2,
  shops: [
    { id: "shop-1", name: "Harare" },
    { id: "shop-2", name: "Bulawayo" },
  ],
  metrics: {
    gross_sales: available("150.00"),
    net_sales: available("120.00"),
    cost_of_sales: available("72.00"),
    gross_profit: available("48.00"),
    refunds: available("30.00"),
    discounts: {
      available: false,
      value: null,
      reason: "Historical discounts are unknown.",
      missing_persistence: "sales.discount_amount",
    },
  },
  financial_summary: {
    gross_sales: "150.00", net_sales: "120.00", cost_of_sales: "72.00",
    gross_profit: "48.00", discounts: "5.00", operating_expenses: "18.00",
    net_profit: "30.00", cash_sales: "40.00", card_sales: "35.00",
    mobile_sales: "20.00", credit_sales: "25.00", credit_settlements: "12.00",
    outstanding_receivables: "13.00", cash_settlements: "6.00",
    card_settlements: "4.00", mobile_settlements: "2.00", cash_expenses: "8.00",
    card_expenses: "6.00", mobile_expenses: "4.00", expected_cash_movement: "38.00",
  },
  granularity: "day",
  comparison: {
    date_from: "2026-07-01",
    date_to: "2026-07-31",
    metrics: {
      gross_sales: { available: true, amount: "25.00", percentage: "20.00", reason: null },
      net_sales: { available: true, amount: "20.00", percentage: "20.00", reason: null },
      cost_of_sales: { available: true, amount: "12.00", percentage: "20.00", reason: null },
      gross_profit: { available: true, amount: "8.00", percentage: "20.00", reason: null },
      refunds: { available: true, amount: "5.00", percentage: "20.00", reason: null },
      discounts: { available: false, amount: null, percentage: null, reason: "Historical discounts are unknown." },
    },
  },
  trends: [{
    period_start: "2026-08-01", period_end: "2026-08-01",
    metrics: {
      gross_sales: available("150.00"), net_sales: available("120.00"),
      cost_of_sales: available("72.00"), gross_profit: available("48.00"),
      refunds: available("30.00"), discounts: available("5.00"),
    },
  }],
  top_products: [{ id: "p1", name: "Coffee", revenue: "80", quantity: "4", gross_profit: "30" }],
  top_categories: [{ id: "c1", name: "Drinks", revenue: "80", quantity: "4", gross_profit: "30" }],
  payment_methods: [], shop_breakdown: [], cashier_breakdown: [],
  discount_breakdown: [], refund_breakdown: [],
};

const analyticsProps = {
  granularity: "day" as const,
  onGranularityChange: () => undefined,
  onExport: () => undefined,
  onOpenDrilldown: () => undefined,
  feature: "home" as const,
  onFeatureChange: () => undefined,
  onNavigatePage: () => undefined,
};

test("dashboard home renders the compact financial summary and feature navigation", () => {
  const markup = renderToStaticMarkup(
    <DashboardPanel
      summary={summary}
      {...analyticsProps}
      rangeKey="custom"
      selectedShopId="shop-2"
      customDateFrom="2026-08-01"
      customDateTo="2026-08-31"
      onRangeChange={() => undefined}
      onShopChange={() => undefined}
      onDateFromChange={() => undefined}
      onDateToChange={() => undefined}
    />,
  );

  for (const label of [
    "Today",
    "Yesterday",
    "Last 7 days",
    "Last month",
    "Custom date range",
    "All shops",
    "Harare",
    "Bulawayo",
    "Gross Sales",
    "Net Sales",
    "Gross Profit",
    "Net Profit",
    "Sales Analytics",
    "Payment Methods",
    "Top Products",
    "Financial Reports",
    "Sales History",
    "Inventory",
    "Employees",
    "Cashier Shifts",
  ]) {
    assert.match(markup, new RegExp(label));
  }

  for (const amount of ["Z$150.00", "Z$120.00", "Z$48.00", "Z$30.00"]) {
    assert.ok(markup.includes(amount));
  }
  assert.ok(markup.includes('value="2026-08-01"'));
  assert.ok(markup.includes('value="2026-08-31"'));
  assert.ok(markup.includes("dashboard-drilldown-trigger"));
  assert.equal((markup.match(/dashboard-feature-icon/g) || []).length, 8);
  assert.ok(!markup.includes("Sales trend"));
});

test("dashboard analytics features render only their selected content", () => {
  const common = {
    ...analyticsProps, summary, rangeKey: "today" as const, selectedShopId: "",
    customDateFrom: "2026-08-01", customDateTo: "2026-08-31",
    onRangeChange: () => undefined, onShopChange: () => undefined,
    onDateFromChange: () => undefined, onDateToChange: () => undefined,
  };
  const sales = renderToStaticMarkup(<DashboardPanel {...common} feature="sales-analytics" />);
  assert.match(sales, /Sales trend/);
  assert.match(sales, /Revenue comparison/);
  assert.doesNotMatch(sales, /Payment breakdown/);
  const payments = renderToStaticMarkup(<DashboardPanel {...common} feature="payment-methods" />);
  assert.match(payments, /Payment breakdown/);
  assert.match(payments, /Cash sales/);
  assert.doesNotMatch(payments, /Revenue comparison/);
  const products = renderToStaticMarkup(<DashboardPanel {...common} feature="top-products" />);
  assert.match(products, /Top-selling products/);
  assert.match(products, /Category performance/);
  assert.match(products, /Coffee/);
});

test("drill-down renders totals, rows, pagination, empty, loading, and errors", () => {
  const request = { title: "Net Sales contributing sales", metric: "net_sales" as const };
  const data = {
    total: 1, limit: 25, offset: 0, metrics: summary.metrics,
    rows: [{
      id: "sale-1", receipt_number: "R-1", created_at: "2026-08-01T10:00:00Z",
      shop_name: "Bulawayo", cashier_name: "Cashier", payment_method: "cash",
      status: "completed", gross_sales: "150", refunds: "30", net_sales: "120",
      gross_profit: "48", discounts: available("5"),
    }],
  };
  const common = {
    request, currencySymbol: "Z$", decimalPlaces: 2,
    reportingTimezone: "Africa/Harare", onClose: () => undefined,
    onPage: () => undefined, onExport: () => undefined,
  };
  const loaded = renderToStaticMarkup(<DashboardDrilldownDialog {...common} data={data} loading={false} error="" />);
  assert.match(loaded, /1 contributing transaction/);
  assert.match(loaded, /Z\$120\.00/);
  assert.match(loaded, /R-1/);
  assert.match(loaded, /1–1 of 1/);
  assert.match(renderToStaticMarkup(<DashboardDrilldownDialog {...common} data={null} loading error="" />), /Loading contributing sales/);
  assert.match(renderToStaticMarkup(<DashboardDrilldownDialog {...common} data={null} loading={false} error="Permission denied" />), /Permission denied/);
  assert.match(renderToStaticMarkup(<DashboardDrilldownDialog {...common} data={{ ...data, total: 0, rows: [] }} loading={false} error="" />), /No contributing sales match/);
});

test("unknown metrics never format as zero", () => {
  assert.equal(formatDashboardMoney(summary.metrics.discounts, "$", 2), "Unavailable");
  assert.equal(formatDashboardMoney(available("0"), "$", 2), "$0.00");
});


test("shop choices remain available while metrics are loading", () => {
  const markup = renderToStaticMarkup(
    <DashboardPanel
      summary={null}
      {...analyticsProps}
      shops={summary.shops}
      rangeKey="today"
      selectedShopId="shop-2"
      customDateFrom="2026-08-01"
      customDateTo="2026-08-31"
      onRangeChange={() => undefined}
      onShopChange={() => undefined}
      onDateFromChange={() => undefined}
      onDateToChange={() => undefined}
    />,
  );
  assert.ok(markup.includes("Bulawayo"));
  assert.ok(markup.includes('value="shop-2" selected=""'));
  assert.ok(!markup.includes("Z$150.00"));
  assert.ok(!markup.includes('type="date"'));
});
