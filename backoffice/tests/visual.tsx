import { createRoot } from "react-dom/client";
import { useState } from "react";
import "../src/App.css";
import "../src/theme.css";
import "../src/ui-system.css";
import "../src/premium-theme.css";
import { DashboardDrilldownDialog } from "../src/DashboardDrilldownDialog";
import { DashboardPanel, type DashboardFeature } from "../src/DashboardPanel";
import type { DashboardDrilldownRequest, DashboardMetric, DashboardPhase3Summary } from "../src/dashboard";
import { AppIcon, type AppIconName } from "../src/components/AppIcon";

const metric = (value: string): DashboardMetric => ({ available: true, value, reason: null, missing_persistence: null });
const summary: DashboardPhase3Summary = {
  range_key: "today", date_from: "2026-09-14", date_to: "2026-09-14",
  reporting_timezone: "Africa/Harare", shop_id: null, currency_symbol: "$", decimal_places: 2,
  shops: [{ id: "one", name: "Harare Central" }],
  metrics: { gross_sales: metric("1580"), net_sales: metric("1420"), cost_of_sales: metric("810"), gross_profit: metric("610"), discounts: metric("60"), refunds: metric("100") },
  financial_summary: {
    gross_sales: "1580", net_sales: "1420", cost_of_sales: "810", gross_profit: "610",
    discounts: "60", operating_expenses: "125", net_profit: "485", cash_sales: "680",
    card_sales: "470", mobile_sales: "270", credit_sales: "160", credit_settlements: "85",
    outstanding_receivables: "340", cash_settlements: "45", card_settlements: "20",
    mobile_settlements: "20", cash_expenses: "75", card_expenses: "30",
    mobile_expenses: "20", expected_cash_movement: "650",
  },
  granularity: "day",
  comparison: { date_from: "2026-09-13", date_to: "2026-09-13", metrics: Object.fromEntries(["gross_sales","net_sales","cost_of_sales","gross_profit","discounts","refunds"].map((key) => [key, { available: true, amount: "20", percentage: "1.4", reason: null }])) },
  trends: [
    ["2026-09-08", "760", "290"], ["2026-09-09", "980", "380"],
    ["2026-09-10", "890", "340"], ["2026-09-11", "1210", "490"],
    ["2026-09-12", "1160", "460"], ["2026-09-13", "1340", "550"],
    ["2026-09-14", "1420", "610"],
  ].map(([day, sales, profit]) => ({ period_start: day, period_end: day, metrics: { gross_sales: metric(sales), net_sales: metric(sales), cost_of_sales: metric(String(Number(sales) - Number(profit))), gross_profit: metric(profit), discounts: metric("20"), refunds: metric("0") } })),
  top_products: [
    { id: "p1", name: "Premium Coffee", revenue: "580", quantity: "42", gross_profit: "260" },
    { id: "p2", name: "Fresh Bread", revenue: "460", quantity: "68", gross_profit: "180" },
    { id: "p3", name: "Orange Juice", revenue: "330", quantity: "31", gross_profit: "142" },
    { id: "p4", name: "Farm Milk", revenue: "250", quantity: "29", gross_profit: "94" },
  ],
  top_categories: [{ id: "c", name: "Beverages", revenue: "740", quantity: "58", gross_profit: "310" }],
  payment_methods: [
    { key: "cash", name: "Cash", transactions: 31, gross_sales: "680", refunds: "0", net_sales: "680", gross_profit: "290", discounts: metric("12") },
    { key: "card", name: "Card", transactions: 22, gross_sales: "470", refunds: "0", net_sales: "470", gross_profit: "202", discounts: metric("8") },
    { key: "mobile", name: "Mobile", transactions: 14, gross_sales: "270", refunds: "0", net_sales: "270", gross_profit: "118", discounts: metric("0") },
  ], shop_breakdown: [], cashier_breakdown: [], discount_breakdown: [], refund_breakdown: [],
};

const params = new URLSearchParams(location.search);
const destinations: Array<[string, AppIconName]> = [["Dashboard", "dashboard"], ["Sales History", "sales"], ["Cashier Shifts", "shifts"], ["Customer Accounts", "customers"], ["Products", "products"], ["Inventory", "inventory"], ["Employees", "employees"], ["Reports", "reports"], ["Shops & Devices", "devices"], ["Settings", "settings"]];
function Harness() {
  const [menuOpen, setMenuOpen] = useState(params.get("menu") === "open");
  const [page, setPage] = useState<"dashboard" | "sales">(
    params.get("page") === "sales" ? "sales" : "dashboard",
  );
  const [feature, setFeature] = useState<DashboardFeature>(() => {
    const requested = params.get("feature");
    return (["sales-analytics", "payment-methods", "top-products"] as DashboardFeature[]).includes(requested as DashboardFeature)
      ? requested as DashboardFeature : "home";
  });
  const [loggedIn, setLoggedIn] = useState(true);
  const [drilldown, setDrilldown] = useState<DashboardDrilldownRequest | null>(
    params.get("drilldown") === "open"
      ? { title: "Net Sales contributing sales", metric: "net_sales" }
      : null,
  );
  const [drilldownOffset, setDrilldownOffset] = useState(0);
  const drilldownData = {
    total: 27, limit: 25, offset: drilldownOffset, metrics: summary.metrics,
    rows: Array.from(
      { length: drilldownOffset === 0 ? 25 : 2 },
      (_, index) => {
        const rowNumber = drilldownOffset + index + 1;
        return {
          id: `sale-${rowNumber}`,
          receipt_number: `APR-${String(rowNumber).padStart(3, "0")}`,
          created_at: `2026-09-14T${String(10 + (index % 8)).padStart(2, "0")}:15:00Z`,
          shop_name: "Harare Central", cashier_name: "Tariro",
          payment_method: "cash", status: "completed",
          gross_sales: "68", refunds: "0", net_sales: "62",
          gross_profit: "28", discounts: metric("6"),
        };
      },
    ),
  };

  function navigate(name: string) {
    if (name === "Dashboard") { setPage("dashboard"); setFeature("home"); }
    if (name === "Sales History") setPage("sales");
    setMenuOpen(false);
  }

  if (!loggedIn) {
    return <main style={{ maxWidth: 560, margin: "80px auto", padding: 24, fontFamily: "Inter, sans-serif" }}>
      <section className="panel">
        <h1>Logged out of synthetic preview</h1>
        <p>The Logout control responded correctly. No real session was used.</p>
        <button type="button" onClick={() => setLoggedIn(true)}>Restore fixture preview</button>
      </section>
    </main>;
  }

  return <div className="backoffice-shell">
    <aside className="sidebar">
      <div className="sidebar-header"><div className="sidebar-brand"><div className="logo-mark small">A</div><div><strong>ApexRetail</strong><span>Backoffice preview</span></div></div><button type="button" className="mobile-menu-toggle" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}><AppIcon name="menu" /> Menu</button></div>
      <nav className={menuOpen ? "mobile-open" : ""}>{destinations.map(([name, icon]) => <button type="button" key={name} onClick={() => navigate(name)} className={(page === "dashboard" && name === "Dashboard") || (page === "sales" && name === "Sales History") ? "active" : ""}><AppIcon name={icon} /><span>{name}</span></button>)}<button type="button" className="logout-nav-button" onClick={() => setLoggedIn(false)}><AppIcon name="logout" /><span>Log out</span></button></nav>
      <button type="button" className="logout-button" onClick={() => setLoggedIn(false)}><AppIcon name="logout" /><span>Log out</span></button>
    </aside>
    <main className="content"><header className="topbar"><div><h1>{page === "dashboard" ? feature === "sales-analytics" ? "Sales Analytics" : "Business Dashboard" : "Sales History"}</h1><p>Safe synthetic fixture data — no production API calls</p></div><button className="refresh-button">Refresh</button></header>
      {page === "dashboard" ? <DashboardPanel summary={summary} shops={summary.shops} rangeKey="today" granularity="day" selectedShopId="" customDateFrom="" customDateTo="" onRangeChange={() => {}} onGranularityChange={() => {}} onShopChange={() => {}} onDateFromChange={() => {}} onDateToChange={() => {}} onExport={() => {}} onOpenDrilldown={setDrilldown} feature={feature} onFeatureChange={setFeature} onNavigatePage={() => {}} /> : <section className="panel"><div className="panel-header"><div><h2>Sales and Receipts</h2><p>2 transaction records loaded</p></div></div><div className="table-wrapper"><table><thead><tr><th>Receipt</th><th>Date</th><th>Payment</th><th>Total</th><th>Status</th></tr></thead><tbody><tr><td>APR-001</td><td>9/14/2026</td><td>CASH</td><td>$42.00</td><td>completed</td></tr></tbody></table></div></section>}
    </main>
    {page === "dashboard" && drilldown && <DashboardDrilldownDialog
      request={drilldown} data={drilldownData} loading={false} error=""
      currencySymbol="$" decimalPlaces={2} reportingTimezone="Africa/Harare"
      onClose={() => setDrilldown(null)} onPage={setDrilldownOffset} onExport={() => {}}
    />}
  </div>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
