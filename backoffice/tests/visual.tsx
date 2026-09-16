import { createRoot } from "react-dom/client";
import { useState } from "react";
import "../src/App.css";
import { DashboardDrilldownDialog } from "../src/DashboardDrilldownDialog";
import { DashboardPanel } from "../src/DashboardPanel";
import type { DashboardDrilldownRequest, DashboardMetric, DashboardPhase3Summary } from "../src/dashboard";

const metric = (value: string): DashboardMetric => ({ available: true, value, reason: null, missing_persistence: null });
const summary: DashboardPhase3Summary = {
  range_key: "today", date_from: "2026-09-14", date_to: "2026-09-14",
  reporting_timezone: "Africa/Harare", shop_id: null, currency_symbol: "$", decimal_places: 2,
  shops: [{ id: "one", name: "Harare Central" }],
  metrics: { gross_sales: metric("1580"), net_sales: metric("1420"), cost_of_sales: metric("810"), gross_profit: metric("610"), discounts: metric("60"), refunds: metric("100") },
  granularity: "day",
  comparison: { date_from: "2026-09-13", date_to: "2026-09-13", metrics: Object.fromEntries(["gross_sales","net_sales","cost_of_sales","gross_profit","discounts","refunds"].map((key) => [key, { available: true, amount: "20", percentage: "1.4", reason: null }])) },
  trends: [{ period_start: "2026-09-14", period_end: "2026-09-14", metrics: { gross_sales: metric("1580"), net_sales: metric("1420"), cost_of_sales: metric("810"), gross_profit: metric("610"), discounts: metric("60"), refunds: metric("100") } }],
  top_products: [{ id: "p", name: "Coffee", revenue: "580", quantity: "42", gross_profit: "260" }],
  top_categories: [{ id: "c", name: "Beverages", revenue: "740", quantity: "58", gross_profit: "310" }],
  payment_methods: [], shop_breakdown: [], cashier_breakdown: [], discount_breakdown: [], refund_breakdown: [],
};

const params = new URLSearchParams(location.search);
const destinations = ["Dashboard", "Sales History", "Products", "Inventory", "Employees", "Reports", "Devices/POS", "Settings"];
function Harness() {
  const [menuOpen, setMenuOpen] = useState(params.get("menu") === "open");
  const [page, setPage] = useState<"dashboard" | "sales">(
    params.get("page") === "sales" ? "sales" : "dashboard",
  );
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
    if (name === "Dashboard") setPage("dashboard");
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
      <div className="sidebar-header"><div className="sidebar-brand"><div className="logo-mark small">A</div><div><strong>ApexRetail</strong><span>Backoffice fixture</span></div></div><button type="button" className="mobile-menu-toggle" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>Menu</button></div>
      <nav className={menuOpen ? "mobile-open" : ""}>{destinations.map((name) => <button type="button" key={name} onClick={() => navigate(name)} className={(page === "dashboard" && name === "Dashboard") || (page === "sales" && name === "Sales History") ? "active" : ""}>{name}</button>)}<button type="button" className="logout-nav-button" onClick={() => setLoggedIn(false)}>Log out</button></nav>
      <button type="button" className="logout-button" onClick={() => setLoggedIn(false)}>Log out</button>
    </aside>
    <main className="content"><header className="topbar"><div><h1>{page === "dashboard" ? "Business Dashboard" : "Sales History"}</h1><p>Safe synthetic fixture data — no production API calls</p></div><button className="refresh-button">Refresh</button></header>
      {page === "dashboard" ? <DashboardPanel summary={summary} shops={summary.shops} rangeKey="today" granularity="day" selectedShopId="" customDateFrom="" customDateTo="" onRangeChange={() => {}} onGranularityChange={() => {}} onShopChange={() => {}} onDateFromChange={() => {}} onDateToChange={() => {}} onExport={() => {}} onOpenDrilldown={setDrilldown} /> : <section className="panel"><div className="panel-header"><div><h2>Sales and Receipts</h2><p>2 transaction records loaded</p></div></div><div className="table-wrapper"><table><thead><tr><th>Receipt</th><th>Date</th><th>Payment</th><th>Total</th><th>Status</th></tr></thead><tbody><tr><td>APR-001</td><td>9/14/2026</td><td>CASH</td><td>$42.00</td><td>completed</td></tr></tbody></table></div></section>}
    </main>
    {page === "dashboard" && drilldown && <DashboardDrilldownDialog
      request={drilldown} data={drilldownData} loading={false} error=""
      currencySymbol="$" decimalPlaces={2} reportingTimezone="Africa/Harare"
      onClose={() => setDrilldown(null)} onPage={setDrilldownOffset} onExport={() => {}}
    />}
  </div>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
