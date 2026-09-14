import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import {
  formatDashboardMoney,
  type DashboardMetric,
  type DashboardPhase3Summary,
} from "../src/dashboard.js";
import { DashboardPanel } from "../src/DashboardPanel.js";


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
};

test("dashboard renders ranges, shop filter, and metrics", () => {
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
    "Cost of Sales",
    "Gross Profit",
    "Refunds",
    "Discounts",
    "Sales and gross-profit trend",
    "Top products",
    "Coffee",
    "Top categories",
    "Drinks",
    "Export CSV",
  ]) {
    assert.match(markup, new RegExp(label));
  }

  for (const amount of ["Z$150.00", "Z$120.00", "Z$72.00", "Z$48.00", "Z$30.00"]) {
    assert.ok(markup.includes(amount));
  }
  assert.ok(markup.includes("Unavailable"));
  assert.ok(markup.includes("Historical discounts are unknown."));
  assert.ok(markup.includes("Showing 2026-08-01 to 2026-08-31 for one shop"));
  assert.ok(markup.includes('value="2026-08-01"'));
  assert.ok(markup.includes('value="2026-08-31"'));
  assert.ok(!markup.includes("Contributing sales"));
  assert.ok(!markup.includes("Sales and Receipts"));
  assert.ok(!markup.includes("transaction records"));
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
