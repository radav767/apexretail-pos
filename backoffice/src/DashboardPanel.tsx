import {
  dashboardRangeOptions, formatDashboardMoney,
  type DashboardBreakdownRow, type DashboardMetric,
  type DashboardDrilldownRequest, type DashboardMetricKey,
  type DashboardPhase3Summary, type DashboardRangeKey, type DashboardRankedRow,
} from "./dashboard";

export type ExportSection = "trends" | "top_products" | "top_categories" | "payment_methods" | "shop_breakdown" | "cashier_breakdown" | "discount_breakdown" | "refund_breakdown";

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
  onNavigateFinancial: (page: "expenses" | "credit-settlements") => void;
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
  const { summary, shops, rangeKey, granularity, selectedShopId, customDateFrom, customDateTo, onRangeChange, onGranularityChange, onShopChange, onDateFromChange, onDateToChange, onExport, onOpenDrilldown, onNavigateFinancial } = props;
  const cards = summary ? [
    ["Gross Sales", "gross_sales", summary.metrics.gross_sales],
    ["Net Sales", "net_sales", summary.metrics.net_sales],
    ["Cost of Sales", "cost_of_sales", summary.metrics.cost_of_sales],
    ["Gross Profit", "gross_profit", summary.metrics.gross_profit],
    ["Discounts", "discounts", summary.metrics.discounts],
    ["Refunds", "refunds", summary.metrics.refunds],
  ] as Array<[string, string, DashboardMetric]> : [];
  const financialCards = summary ? [
    { title: "Operating Expenses", value: summary.financial_summary.operating_expenses, detail: "Deducted from gross profit, not sales", page: "expenses" as const },
    { title: "Net Profit", value: summary.financial_summary.net_profit, detail: "Gross profit minus operating expenses" },
    { title: "Cash Sales", value: summary.financial_summary.cash_sales, detail: "Sales revenue paid in cash" },
    { title: "Card Sales", value: summary.financial_summary.card_sales, detail: "Sales revenue paid by card" },
    { title: "Mobile / Transfer Sales", value: summary.financial_summary.mobile_sales, detail: "Sales revenue paid by mobile / transfer" },
    { title: "Credit Sales", value: summary.financial_summary.credit_sales, detail: "Recognized as revenue at sale time" },
    { title: "Credit Settlements", value: summary.financial_summary.credit_settlements, detail: `Cash ${money(summary.financial_summary.cash_settlements, summary)} · Card ${money(summary.financial_summary.card_settlements, summary)} · Mobile ${money(summary.financial_summary.mobile_settlements, summary)}`, page: "credit-settlements" as const },
    { title: "Outstanding Credit / Receivables", value: summary.financial_summary.outstanding_receivables, detail: "Current unsettled customer credit", page: "credit-settlements" as const },
    { title: "Expected Cash Movement", value: summary.financial_summary.expected_cash_movement, detail: "Cash sales + cash settlements − cash expenses" },
  ] : [];

  return <>
    <section className="dashboard-filters panel" aria-labelledby="dashboard-filters-title">
      <div className="panel-header"><div><h2 id="dashboard-filters-title">Reporting Filters</h2><p>Completed sales only. Reporting timezone: {summary?.reporting_timezone || "Africa/Harare"}</p></div></div>
      <div className="dashboard-filter-grid">
        <label className="dashboard-filter-field"><span>Reporting period</span><select aria-label="Reporting period" value={rangeKey} onChange={(event) => onRangeChange(event.target.value as DashboardRangeKey)}>{dashboardRangeOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}</select></label>
        <label className="dashboard-filter-field"><span>Shop</span><select aria-label="Shop" value={selectedShopId} onChange={(event) => onShopChange(event.target.value)}><option value="">All shops</option>{(shops ?? summary?.shops ?? []).map((shop) => <option key={shop.id} value={shop.id}>{shop.name}</option>)}</select></label>
        <label className="dashboard-filter-field"><span>Trend grouping</span><select aria-label="Trend grouping" value={granularity} onChange={(event) => onGranularityChange(event.target.value as Props["granularity"])}><option value="day">Day</option><option value="week">Week</option><option value="month">Month</option></select></label>
        {rangeKey === "custom" && <><label className="dashboard-filter-field"><span>Date from</span><input aria-label="Date from" type="date" value={customDateFrom} onChange={(event) => onDateFromChange(event.target.value)} /></label><label className="dashboard-filter-field"><span>Date to</span><input aria-label="Date to" type="date" value={customDateTo} onChange={(event) => onDateToChange(event.target.value)} /></label></>}
      </div>
      {summary && <p className="dashboard-range-caption">Showing {summary.date_from} to {summary.date_to}{summary.shop_id ? " for one shop" : " across all company shops"}. Compared with {summary.comparison.date_from} to {summary.comparison.date_to}.</p>}
    </section>

    <section className="summary-grid" aria-label="Financial summary">{cards.map(([title, key, metric]) => {
      const change = summary?.comparison.metrics[key];
      const changeText = change && summary && change.available && change.amount !== null ? `${Number(change.amount) >= 0 ? "+" : ""}${money(change.amount, summary)} vs previous${change.percentage === null ? " (percentage unavailable)" : ` (${Number(change.percentage) >= 0 ? "+" : ""}${change.percentage}%)`}` : change?.reason || "Completed sales and recorded refunds";
      return <button type="button" className={`summary-card dashboard-drilldown-trigger ${metric.available ? "" : "muted"}`} key={title} onClick={() => onOpenDrilldown({ title: `${title} contributing sales`, metric: key as DashboardMetricKey })}><span>{title}</span><strong>{formatDashboardMoney(metric, summary?.currency_symbol || "$", summary?.decimal_places ?? 2)}</strong><small>{changeText}</small>{metric.reason ? <p>{metric.reason}</p> : null}</button>;
    })}{financialCards.map((card) => card.page ? (
      <button type="button" className="summary-card dashboard-financial-link" key={card.title} onClick={() => onNavigateFinancial(card.page!)}><span>{card.title}</span><strong>{summary ? money(card.value, summary) : ""}</strong><small>{card.detail}</small></button>
    ) : (
      <article className="summary-card summary-card-static" key={card.title}><span>{card.title}</span><strong>{summary ? money(card.value, summary) : ""}</strong><small>{card.detail}</small></article>
    ))}</section>

    {summary && <>
      <section className="panel analytics-panel"><div className="panel-header"><div><h2>Sales and gross-profit trend</h2><p>Grouped by {granularity}</p></div><ExportButton section="trends" onExport={onExport} /></div><div className="analytics-table-wrap"><table className="analytics-table"><caption className="sr-only">Sales and gross-profit trend</caption><thead><tr><th>Period</th><th>Gross sales</th><th>Refunds</th><th>Net sales</th><th>Gross profit</th><th>Discounts</th></tr></thead><tbody>{summary.trends.length ? summary.trends.map((point) => <tr key={point.period_start}><th scope="row"><button type="button" className="dashboard-detail-link" onClick={() => onOpenDrilldown({ title: `Sales from ${point.period_start} to ${point.period_end}`, metric: "net_sales", dateFrom: point.period_start, dateTo: point.period_end })}>{point.period_start} – {point.period_end}</button></th><td>{formatDashboardMoney(point.metrics.gross_sales, summary.currency_symbol, summary.decimal_places)}</td><td>{formatDashboardMoney(point.metrics.refunds, summary.currency_symbol, summary.decimal_places)}</td><td>{formatDashboardMoney(point.metrics.net_sales, summary.currency_symbol, summary.decimal_places)}</td><td>{formatDashboardMoney(point.metrics.gross_profit, summary.currency_symbol, summary.decimal_places)}</td><td>{formatDashboardMoney(point.metrics.discounts, summary.currency_symbol, summary.decimal_places)}</td></tr>) : <tr><td colSpan={6}>No contributing sales</td></tr>}</tbody></table></div></section>
      <div className="analytics-grid"><RankedTable title="Top products" rows={summary.top_products} summary={summary} section="top_products" dimension="product" onExport={onExport} onOpenDrilldown={onOpenDrilldown} /><RankedTable title="Top categories" rows={summary.top_categories} summary={summary} section="top_categories" dimension="category" onExport={onExport} onOpenDrilldown={onOpenDrilldown} /></div>
      <BreakdownTable title="Payment methods" rows={summary.payment_methods} summary={summary} section="payment_methods" dimension="payment" onExport={onExport} onOpenDrilldown={onOpenDrilldown} />
      <BreakdownTable title="Shops" rows={summary.shop_breakdown} summary={summary} section="shop_breakdown" dimension="shop" onExport={onExport} onOpenDrilldown={onOpenDrilldown} />
      <BreakdownTable title="Cashiers" rows={summary.cashier_breakdown} summary={summary} section="cashier_breakdown" dimension="cashier" onExport={onExport} onOpenDrilldown={onOpenDrilldown} />
      <div className="analytics-grid"><BreakdownTable title="Discounts" rows={summary.discount_breakdown} summary={summary} section="discount_breakdown" metric="discounts" dimension="discount" onExport={onExport} onOpenDrilldown={onOpenDrilldown} /><BreakdownTable title="Refunds" rows={summary.refund_breakdown} summary={summary} section="refund_breakdown" metric="refunds" dimension="refund" onExport={onExport} onOpenDrilldown={onOpenDrilldown} /></div>
    </>}
  </>;
}
