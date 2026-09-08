import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import {
  formatDashboardMoney,
  type DashboardMetric,
  type DashboardPhase2Summary,
} from "../src/dashboard.js";
import { DashboardPanel } from "../src/DashboardPanel.js";


const available = (value: string): DashboardMetric => ({
  available: true,
  value,
  reason: null,
  missing_persistence: null,
});

const summary: DashboardPhase2Summary = {
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
};

test("dashboard renders ranges, shop filter, and metrics", () => {
  const markup = renderToStaticMarkup(
    <DashboardPanel
      summary={summary}
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
});

test("unknown metrics never format as zero", () => {
  assert.equal(formatDashboardMoney(summary.metrics.discounts, "$", 2), "Unavailable");
  assert.equal(formatDashboardMoney(available("0"), "$", 2), "$0.00");
});


test("shop choices remain available while metrics are loading", () => {
  const markup = renderToStaticMarkup(
    <DashboardPanel
      summary={null}
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
