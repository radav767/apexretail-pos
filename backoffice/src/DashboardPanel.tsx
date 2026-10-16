import {
  dashboardRangeOptions, formatDashboardMoney,
  type DashboardBreakdownRow, type DashboardMetric,
  type DashboardDrilldownRequest, type DashboardMetricKey,
  type DashboardPhase3Summary, type DashboardRangeKey, type DashboardRankedRow,
} from "./dashboard";
import {
  PaymentDonutChart,
  RankedBarChart,
  RevenueTrendChart,
} from "./components/AnalyticsCharts";
import { AppIcon, type AppIconName } from "./components/AppIcon";

export type ExportSection = "trends" | "top_products" | "top_categories" | "payment_methods" | "shop_breakdown" | "cashier_breakdown" | "discount_breakdown" | "refund_breakdown";
export type DashboardFeature = "home" | "sales-analytics" | "payment-methods" | "top-products";

type Props = {
  summary: DashboardPhase3Summary | null;
  shops?: DashboardPhase3Summary["shops"];
  rangeKey: DashboardRangeKey;
  granularity: "day" | "week" | "month";
  selectedShopId: string;
  customDateFrom: string;
  customDateTo: string;
  onRangeChange: (value: DashboardRangeKey) => void;
  onGranularityChange: (value: Props["granularity"]) => void;
  onShopChange: (value: string) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onExport: (section: ExportSection) => void;
  onOpenDrilldown: (request: DashboardDrilldownRequest) => void;
  feature: DashboardFeature;
  onFeatureChange: (feature: DashboardFeature) => void;
  onNavigatePage: (page: "reports" | "sales" | "inventory" | "employees" | "shift-reports") => void;
};

const money = (value: string | number, summary: DashboardPhase3Summary) =>
  `${summary.currency_symbol}${Number(value).toFixed(summary.decimal_places)}`;

function ExportButton({ section, onExport }: { section: ExportSection; onExport: Props["onExport"] }) {
  return <button type="button" className="dashboard-export" onClick={() => onExport(section)}>Export CSV</button>;
}

function RankedTable({ title, rows, summary, section, dimension, onExport, onOpenDrilldown }: { title: string; rows: DashboardRankedRow[]; summary: DashboardPhase3Summary; section: ExportSection; dimension: "product" | "category"; onExport: Props["onExport"]; onOpenDrilldown: Props["onOpenDrilldown"] }) {
  return <section className="panel analytics-panel">
    <div className="panel-header"><div><h2>{title}</h2><p>Ranked by revenue</p></div><ExportButton section={section} onExport={onExport} /></div>
    <div className="analytics-table-wrap"><table className="analytics-table"><caption className="sr-only">{title}</caption><thead><tr><th>Name</th><th>Revenue</th><th>Quantity</th><th>Gross profit</th></tr></thead><tbody>
      {rows.length ? rows.map((row) => <tr key={`${row.id}-${row.name}`}><th scope="row"><button type="button" className="dashboard-detail-link" onClick={() => onOpenDrilldown({ title: `${title}: ${row.name}`, metric: "net_sales", dimension, dimensionKey: row.id || "unassigned" })}>{row.name}</button></th><td>{money(row.revenue, summary)}</td><td>{Number(row.quantity).toFixed(3)}</td><td>{money(row.gross_profit, summary)}</td></tr>) : <tr><td colSpan={4}>No contributing sales</td></tr>}
    </tbody></table></div>
  </section>;
}

function BreakdownTable({ title, rows, summary, section, metric = "net_sales", dimension, onExport, onOpenDrilldown }: { title: string; rows: DashboardBreakdownRow[]; summary: DashboardPhase3Summary; section: ExportSection; metric?: DashboardMetricKey; dimension: "payment" | "shop" | "cashier" | "discount" | "refund"; onExport: Props["onExport"]; onOpenDrilldown: Props["onOpenDrilldown"] }) {
  return <section className="panel analytics-panel">
    <div className="panel-header"><div><h2>{title}</h2><p>Selected reporting population</p></div><ExportButton section={section} onExport={onExport} /></div>
    <div className="analytics-table-wrap"><table className="analytics-table"><caption className="sr-only">{title}</caption><thead><tr><th>Name</th><th>Transactions</th><th>Gross</th><th>Refunds</th><th>Net</th><th>Profit</th><th>Discounts</th></tr></thead><tbody>
      {rows.length ? rows.map((row) => <tr key={row.key}><th scope="row"><button type="button" className="dashboard-detail-link" onClick={() => onOpenDrilldown({ title: `${title}: ${row.name}`, metric, dimension, dimensionKey: row.key })}>{row.name}</button></th><td>{row.transactions}</td><td>{money(row.gross_sales, summary)}</td><td>{money(row.refunds, summary)}</td><td>{money(row.net_sales, summary)}</td><td>{money(row.gross_profit, summary)}</td><td>{formatDashboardMoney(row.discounts, summary.currency_symbol, summary.decimal_places)}</td></tr>) : <tr><td colSpan={7}>No contributing sales</td></tr>}
    </tbody></table></div>
  </section>;
}

export function DashboardPanel(props: Props) {
  const { summary, shops, rangeKey, granularity, selectedShopId, customDateFrom, customDateTo, onRangeChange, onGranularityChange, onShopChange, onDateFromChange, onDateToChange, onExport, onOpenDrilldown, feature, onFeatureChange, onNavigatePage } = props;
  const featureButtons: Array<{ title: string; detail: string; icon: AppIconName; feature?: DashboardFeature; page?: Parameters<Props["onNavigatePage"]>[0] }> = [
    { title: "Sales Analytics", detail: "Trends and revenue comparisons", icon: "dashboard", feature: "sales-analytics" },
    { title: "Payment Methods", detail: "Cash, card and mobile payments", icon: "credit", feature: "payment-methods" },
    { title: "Top Products", detail: "Product and category performance", icon: "products", feature: "top-products" },
    { title: "Financial Reports", detail: "Profit, expenses and refunds", icon: "reports", page: "reports" },
    { title: "Sales History", detail: "Transactions and receipts", icon: "sales", page: "sales" },
    { title: "Inventory", detail: "Stock and movement controls", icon: "inventory", page: "inventory" },
    { title: "Employees", detail: "Staff and permissions", icon: "employees", page: "employees" },
    { title: "Cashier Shifts", detail: "Shift history and Z Reports", icon: "shifts", page: "shift-reports" },
  ];
  const coreCards = summary ? [
    ["Gross Sales", "gross_sales", summary.metrics.gross_sales],
    ["Net Sales", "net_sales", summary.metrics.net_sales],
    ["Gross Profit", "gross_profit", summary.metrics.gross_profit],
  ] as Array<[string, DashboardMetricKey, DashboardMetric]> : [];

  const filters = (showGranularity = false) => <section className="dashboard-filters panel" aria-labelledby="dashboard-filters-title">
    <div className="dashboard-filter-grid">
      <label className="dashboard-filter-field"><span>Date filter</span><select aria-label="Reporting period" value={rangeKey} onChange={(event) => onRangeChange(event.target.value as DashboardRangeKey)}>{dashboardRangeOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}</select></label>
      <label className="dashboard-filter-field"><span>Business / shop</span><select aria-label="Shop" value={selectedShopId} onChange={(event) => onShopChange(event.target.value)}><option value="">All shops</option>{(shops ?? summary?.shops ?? []).map((shop) => <option key={shop.id} value={shop.id}>{shop.name}</option>)}</select></label>
      {showGranularity && <label className="dashboard-filter-field"><span>Trend grouping</span><select aria-label="Trend grouping" value={granularity} onChange={(event) => onGranularityChange(event.target.value as Props["granularity"])}><option value="day">Day</option><option value="week">Week</option><option value="month">Month</option></select></label>}
      {rangeKey === "custom" && <><label className="dashboard-filter-field"><span>Date from</span><input aria-label="Date from" type="date" value={customDateFrom} onChange={(event) => onDateFromChange(event.target.value)} /></label><label className="dashboard-filter-field"><span>Date to</span><input aria-label="Date to" type="date" value={customDateTo} onChange={(event) => onDateToChange(event.target.value)} /></label></>}
    </div>
  </section>;

  if (feature === "home") return <>
    {filters()}
    <section className="summary-grid dashboard-core-summary" aria-label="Financial summary">
      {coreCards.map(([title, key, metric]) => <button type="button" className="summary-card dashboard-drilldown-trigger" key={title} onClick={() => onOpenDrilldown({ title: `${title} contributing sales`, metric: key })}><span>{title}</span><strong>{formatDashboardMoney(metric, summary?.currency_symbol || "$", summary?.decimal_places ?? 2)}</strong></button>)}
      <article className="summary-card summary-card-static"><span>Net Profit</span><strong>{summary ? money(summary.financial_summary.net_profit, summary) : "—"}</strong></article>
    </section>
    <section className="dashboard-feature-grid" aria-label="Dashboard features">
      {featureButtons.map((item) => <button type="button" key={item.title} onClick={() => item.feature ? onFeatureChange(item.feature) : item.page && onNavigatePage(item.page)}><span className="dashboard-feature-icon"><AppIcon name={item.icon} /></span><span><strong>{item.title}</strong><small>{item.detail}</small></span></button>)}
    </section>
  </>;

  if (!summary) return <><button type="button" className="dashboard-back-button" onClick={() => onFeatureChange("home")}>← Back to Dashboard</button>{filters(feature === "sales-analytics")}</>;

  return <>
    <div className="dashboard-feature-header"><button type="button" className="dashboard-back-button" onClick={() => onFeatureChange("home")}>← Back to Dashboard</button><h2>{feature === "sales-analytics" ? "Sales Analytics" : feature === "payment-methods" ? "Payment Methods" : "Top Products"}</h2></div>
    {filters(feature === "sales-analytics")}
    {feature === "sales-analytics" && <>
      <section className="panel chart-card"><div className="panel-header"><div><span className="panel-eyebrow">Revenue</span><h2>Sales trend</h2></div><ExportButton section="trends" onExport={onExport} /></div><RevenueTrendChart summary={summary} /></section>
      <section className="panel analytics-panel"><div className="panel-header"><div><h2>Revenue comparison</h2><p>Grouped by {granularity}</p></div><ExportButton section="trends" onExport={onExport} /></div><div className="analytics-table-wrap"><table className="analytics-table"><thead><tr><th>Period</th><th>Gross sales</th><th>Refunds</th><th>Net sales</th><th>Gross profit</th><th>Discounts</th></tr></thead><tbody>{summary.trends.map((point) => <tr key={point.period_start}><th>{point.period_start} – {point.period_end}</th><td>{formatDashboardMoney(point.metrics.gross_sales, summary.currency_symbol, summary.decimal_places)}</td><td>{formatDashboardMoney(point.metrics.refunds, summary.currency_symbol, summary.decimal_places)}</td><td>{formatDashboardMoney(point.metrics.net_sales, summary.currency_symbol, summary.decimal_places)}</td><td>{formatDashboardMoney(point.metrics.gross_profit, summary.currency_symbol, summary.decimal_places)}</td><td>{formatDashboardMoney(point.metrics.discounts, summary.currency_symbol, summary.decimal_places)}</td></tr>)}</tbody></table></div></section>
    </>}
    {feature === "payment-methods" && <>
      <section className="dashboard-payment-summary"><article><span>Cash sales</span><strong>{money(summary.financial_summary.cash_sales, summary)}</strong></article><article><span>Card sales</span><strong>{money(summary.financial_summary.card_sales, summary)}</strong></article><article><span>Mobile payments</span><strong>{money(summary.financial_summary.mobile_sales, summary)}</strong></article></section>
      <section className="panel chart-card"><div className="panel-header"><div><span className="panel-eyebrow">Tender mix</span><h2>Payment breakdown</h2></div><ExportButton section="payment_methods" onExport={onExport} /></div><PaymentDonutChart rows={summary.payment_methods} summary={summary} /></section>
      <BreakdownTable title="Payment methods" rows={summary.payment_methods} summary={summary} section="payment_methods" dimension="payment" onExport={onExport} onOpenDrilldown={onOpenDrilldown} />
    </>}
    {feature === "top-products" && <>
      <section className="panel chart-card"><div className="panel-header"><div><span className="panel-eyebrow">Product performance</span><h2>Top-selling products</h2></div><ExportButton section="top_products" onExport={onExport} /></div><RankedBarChart rows={summary.top_products} summary={summary} /></section>
      <div className="analytics-grid"><RankedTable title="Top products" rows={summary.top_products} summary={summary} section="top_products" dimension="product" onExport={onExport} onOpenDrilldown={onOpenDrilldown} /><RankedTable title="Category performance" rows={summary.top_categories} summary={summary} section="top_categories" dimension="category" onExport={onExport} onOpenDrilldown={onOpenDrilldown} /></div>
    </>}
  </>;
}
