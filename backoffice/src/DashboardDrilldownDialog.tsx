import { formatDashboardMoney, type DashboardDrilldown, type DashboardDrilldownRequest } from "./dashboard";

type Props = {
  request: DashboardDrilldownRequest;
  data: DashboardDrilldown | null;
  loading: boolean;
  error: string;
  currencySymbol: string;
  decimalPlaces: number;
  reportingTimezone: string;
  onClose: () => void;
  onPage: (offset: number) => void;
  onExport: () => void;
};

export function DashboardDrilldownDialog({ request, data, loading, error, currencySymbol, decimalPlaces, reportingTimezone, onClose, onPage, onExport }: Props) {
  const pageStart = data && data.total ? data.offset + 1 : 0;
  const pageEnd = data ? Math.min(data.offset + data.rows.length, data.total) : 0;
  const selectedMetric = data?.metrics[request.metric];
  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: reportingTimezone,
  });
  return <div className="dashboard-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="dashboard-dialog" role="dialog" aria-modal="true" aria-labelledby="dashboard-detail-title">
      <div className="panel-header dashboard-dialog-header"><div><h2 id="dashboard-detail-title">{request.title}</h2><p>Reporting timezone: {reportingTimezone}. Current Dashboard filters remain applied.</p></div><button type="button" className="dashboard-dialog-close" onClick={onClose} aria-label="Close contributing sales">×</button></div>
      {loading && <p className="dashboard-detail-state" role="status">Loading contributing sales…</p>}
      {!loading && error && <p className="dashboard-detail-state error" role="alert">{error}</p>}
      {!loading && !error && data && <>
        <div className="dashboard-detail-summary"><span>{data.total} contributing transaction{data.total === 1 ? "" : "s"}</span><strong>{selectedMetric ? formatDashboardMoney(selectedMetric, currencySymbol, decimalPlaces) : "Unavailable"}</strong></div>
        {data.rows.length ? <div className="analytics-table-wrap"><table className="analytics-table dashboard-detail-table"><caption className="sr-only">{request.title}</caption><thead><tr><th>Receipt</th><th>Date</th><th>Shop</th><th>Cashier</th><th>Payment</th><th>Status</th><th>Gross</th><th>Refunds</th><th>Net</th><th>Profit</th><th>Discount</th></tr></thead><tbody>{data.rows.map((row) => <tr key={row.id}><th scope="row">{row.receipt_number}</th><td>{dateFormatter.format(new Date(row.created_at))}</td><td>{row.shop_name}</td><td>{row.cashier_name}</td><td>{row.payment_method}</td><td>{row.status}</td><td>{currencySymbol}{Number(row.gross_sales).toFixed(decimalPlaces)}</td><td>{currencySymbol}{Number(row.refunds).toFixed(decimalPlaces)}</td><td>{currencySymbol}{Number(row.net_sales).toFixed(decimalPlaces)}</td><td>{currencySymbol}{Number(row.gross_profit).toFixed(decimalPlaces)}</td><td>{formatDashboardMoney(row.discounts, currencySymbol, decimalPlaces)}</td></tr>)}</tbody></table></div> : <p className="dashboard-detail-state">No contributing sales match these filters.</p>}
        <div className="dashboard-dialog-actions"><button type="button" className="dashboard-export" onClick={onExport} disabled={!data.total}>Export contributing sales CSV</button><div className="dashboard-pagination" aria-label="Contributing sales pages"><button type="button" onClick={() => onPage(Math.max(0, data.offset - data.limit))} disabled={loading || data.offset === 0}>Previous</button><span>{pageStart}–{pageEnd} of {data.total}</span><button type="button" onClick={() => onPage(data.offset + data.limit)} disabled={loading || data.offset + data.limit >= data.total}>Next</button></div></div>
      </>}
    </section>
  </div>;
}
