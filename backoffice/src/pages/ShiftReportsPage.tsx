import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import Pagination from "../components/Pagination";
import { emptyPage, unpackPage, type PageMeta } from "../components/pagination";
import "./shift-reports.css";

type CurrencyCash = {
  currency_code: string;
  currency_name: string;
  symbol: string;
  decimal_places: number;
  opening_float: string | number;
  cash_sales: string | number;
  cash_refunds: string | number;
  cash_settlements: string | number;
  cash_expenses: string | number;
  cash_in: string | number;
  cash_out: string | number;
  cash_paid_out: string | number;
  expected_cash: string | number;
  counted_cash: string | number | null;
  variance: string | number | null;
};

type ShiftSummary = {
  gross_sales_base: string | number | null;
  net_sales_base: string | number | null;
  total_sales_base?: string | number | null;
  cost_of_sales_base: string | number | null;
  gross_profit_base: string | number | null;
  discounts_base: string | number | null;
  cash_sales_base: string | number | null;
  card_sales_base: string | number | null;
  mobile_sales_base: string | number | null;
  credit_sales_base: string | number | null;
  cash_settlements_base: string | number | null;
  card_settlements_base: string | number | null;
  mobile_settlements_base: string | number | null;
  cash_expenses_base: string | number | null;
  noncash_expenses_base: string | number | null;
  cash_received_base?: string | number | null;
  cash_paid_out_base?: string | number | null;
  refunds_base?: string | number | null;
  base_currency_code?: string | null;
};

type Shift = {
  id: string;
  shift_number: string;
  company_id: string;
  shop_id: string;
  branch_id: string;
  device_id: string;
  employee_id: string;
  cashier_name?: string | null;
  cashier_role?: string | null;
  shop_name?: string | null;
  branch_name?: string | null;
  register_name?: string | null;
  status: "open" | "closed";
  opened_at: string;
  closed_at: string | null;
  opening_note: string | null;
  closing_note: string | null;
  currencies: CurrencyCash[];
  summary: ShiftSummary;
};

type ReportSummary = {
  total_shifts: number;
  open_shifts: number;
  closed_shifts: number;
  total_sales_base: string | number;
  cash_received_base: string | number;
  base_currency_code: string | null;
  variance_by_currency: Array<{ currency_code: string; amount: string | number }>;
};

type FilterOptions = {
  cashiers: Array<{ id: string; name: string; role: string }>;
  branches: Array<{ id: string; name: string; shop_name: string }>;
  devices: Array<{ id: string; name: string }>;
};

type DatePreset = "today" | "yesterday" | "week" | "month" | "custom";

const localDate = (date: Date) => {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 10);
};

function rangeFor(preset: DatePreset, dateFrom: string, dateTo: string) {
  if (preset === "custom") return { dateFrom, dateTo };
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const end = new Date(start);
  if (preset === "yesterday") start.setDate(start.getDate() - 1);
  if (preset === "week") start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  if (preset === "month") start.setDate(1);
  if (preset === "today" || preset === "yesterday") end.setTime(start.getTime());
  else end.setTime(now.getTime());
  return { dateFrom: localDate(start), dateTo: localDate(end) };
}

function amount(value: string | number | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function money(value: string | number | null | undefined, code: string, symbol?: string, places = 2) {
  const parsed = amount(value);
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency", currency: code, minimumFractionDigits: places,
      maximumFractionDigits: places,
    }).format(parsed);
  } catch {
    return `${symbol || code} ${parsed.toFixed(places)} ${code}`;
  }
}

function multiCurrency(values: CurrencyCash[], field: keyof CurrencyCash) {
  if (!values.length) return <span>—</span>;
  return <span className="shift-currency-stack">{values.map((row) => (
    <span key={row.currency_code}>
      <b>{row[field] === null
        ? (field === "counted_cash" ? "Not counted" : field === "variance" ? "Open" : "—")
        : money(row[field] as string | number, row.currency_code, row.symbol, row.decimal_places)}</b>
      <small>{row.currency_code}</small>
    </span>
  ))}</span>;
}

function filterParams(
  preset: DatePreset, dateFrom: string, dateTo: string,
  filters: { employeeId: string; branchId: string; deviceId: string; status: string },
) {
  const range = rangeFor(preset, dateFrom, dateTo);
  const start = range.dateFrom ? new Date(`${range.dateFrom}T00:00:00`).toISOString() : undefined;
  const end = range.dateTo
    ? new Date(new Date(`${range.dateTo}T00:00:00`).getTime() + 86_400_000).toISOString()
    : undefined;
  return {
    start_at: start,
    end_at: end,
    employee_id: filters.employeeId || undefined,
    branch_id: filters.branchId || undefined,
    device_id: filters.deviceId || undefined,
    status: filters.status || undefined,
  };
}

const EMPTY_OPTIONS: FilterOptions = { cashiers: [], branches: [], devices: [] };
const EMPTY_SUMMARY: ReportSummary = {
  total_shifts: 0, open_shifts: 0, closed_shifts: 0,
  total_sales_base: 0, cash_received_base: 0,
  base_currency_code: null, variance_by_currency: [],
};

export default function ShiftReportsPage({ companyId }: { companyId: string }) {
  const today = localDate(new Date());
  const [preset, setPreset] = useState<DatePreset>("today");
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(today);
  const [employeeId, setEmployeeId] = useState("");
  const [branchId, setBranchId] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [status, setStatus] = useState("");
  const [filters, setFilters] = useState({ employeeId: "", branchId: "", deviceId: "", status: "" });
  const [options, setOptions] = useState<FilterOptions>(EMPTY_OPTIONS);
  const [items, setItems] = useState<Shift[]>([]);
  const [summary, setSummary] = useState<ReportSummary>(EMPTY_SUMMARY);
  const [page, setPage] = useState<PageMeta>(emptyPage(25));
  const [selected, setSelected] = useState<Shift | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const params = useMemo(() => filterParams(preset, dateFrom, dateTo, filters), [preset, dateFrom, dateTo, filters]);

  const load = useCallback(async (pageNumber = 1) => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const response = await api.get(`/shifts/company/${companyId}`, {
        params: { ...params, page: pageNumber, page_size: 25 },
      });
      const result = unpackPage<Shift>(response.data);
      setItems(result.items);
      setPage(result.meta);
      setSummary(response.data.summary || EMPTY_SUMMARY);
    } catch (requestError: any) {
      setItems([]);
      setSummary(EMPTY_SUMMARY);
      setError(requestError?.response?.status === 403
        ? "You do not have permission to view shift reports."
        : requestError?.response?.data?.detail || "Failed to load shift reports.");
    } finally {
      setLoading(false);
    }
  }, [companyId, params]);

  useEffect(() => {
    if (!companyId) return;
    api.get<FilterOptions>(`/shifts/company/${companyId}/filters`)
      .then((response) => setOptions(response.data))
      .catch((requestError: any) => {
        if (requestError?.response?.status !== 403) {
          setError(requestError?.response?.data?.detail || "Failed to load shift filters.");
        }
      });
  }, [companyId]);

  useEffect(() => { void load(1); }, [load]);

  function applyFilters() {
    if (preset === "custom" && (!dateFrom || !dateTo || dateFrom > dateTo)) {
      setError("Choose a valid start and end date.");
      return;
    }
    setFilters({ employeeId, branchId, deviceId, status });
  }

  function changePreset(value: DatePreset) {
    setPreset(value);
    if (value !== "custom") {
      const next = rangeFor(value, dateFrom, dateTo);
      setDateFrom(next.dateFrom);
      setDateTo(next.dateTo);
    }
  }

  async function openDetails(shift: Shift) {
    setSelected(null);
    setDetailLoading(true);
    setError("");
    try {
      const response = await api.get<Shift>(`/shifts/company/${companyId}/${shift.id}`);
      setSelected(response.data);
    } catch (requestError: any) {
      setError(requestError?.response?.data?.detail || "Failed to load shift details.");
    } finally {
      setDetailLoading(false);
    }
  }

  async function exportCsv() {
    setError("");
    try {
      const response = await api.get(`/shifts/company/${companyId}/export.csv`, {
        params, responseType: "blob",
      });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `shift-report-${new Date().toISOString().slice(0, 10)}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (requestError: any) {
      setError(requestError?.response?.data?.detail || "Failed to export shift report.");
    }
  }

  const totalVariance = summary.variance_by_currency || [];
  const summaryCurrency = summary.base_currency_code || "USD";

  return <div className="shift-reports-page">
    <section className="shift-report-toolbar">
      <div className="shift-report-heading">
        <div><h2>Cashier shift reports</h2><p>Review register sessions, cash reconciliation, and base-currency totals. Physical cash remains separated by currency.</p></div>
        <div className="shift-report-actions">
          <button type="button" onClick={() => void load(1)} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>
          <button type="button" onClick={() => void exportCsv()} disabled={loading}>Export CSV</button>
        </div>
      </div>
      <div className="shift-presets" aria-label="Shift date range">
        {([["today", "Today"], ["yesterday", "Yesterday"], ["week", "This week"], ["month", "This month"], ["custom", "Custom"]] as Array<[DatePreset, string]>).map(([value, label]) => (
          <button type="button" key={value} className={preset === value ? "selected" : ""} onClick={() => changePreset(value)}>{label}</button>
        ))}
      </div>
      {preset === "custom" && <div className="shift-date-fields">
        <label>From<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
        <label>To<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
      </div>}
      <div className="shift-filter-grid">
        <label>Cashier<select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}><option value="">All cashiers</option>{options.cashiers.map((cashier) => <option key={cashier.id} value={cashier.id}>{cashier.name}</option>)}</select></label>
        <label>Shop / branch<select value={branchId} onChange={(event) => setBranchId(event.target.value)}><option value="">All branches</option>{options.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.shop_name} — {branch.name}</option>)}</select></label>
        <label>Register / device<select value={deviceId} onChange={(event) => setDeviceId(event.target.value)}><option value="">All registers</option>{options.devices.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}</select></label>
        <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Open and closed</option><option value="open">Open</option><option value="closed">Closed</option></select></label>
        <button type="button" className="shift-apply-button" onClick={applyFilters} disabled={loading}>Apply filters</button>
      </div>
      {error && <p className="shift-report-error" role="alert">{error}</p>}
    </section>

    <section className="shift-summary-grid" aria-label="Shift summary">
      <article><span>Total shifts</span><strong>{summary.total_shifts}</strong></article>
      <article><span>Open shifts</span><strong>{summary.open_shifts}</strong></article>
      <article><span>Closed shifts</span><strong>{summary.closed_shifts}</strong></article>
      <article><span>Total sales ({summaryCurrency})</span><strong>{money(summary.total_sales_base, summaryCurrency)}</strong><small>Base-currency accounting total</small></article>
      <article><span>Cash received ({summaryCurrency})</span><strong>{money(summary.cash_received_base, summaryCurrency)}</strong><small>Positive cash sales + cash settlements</small></article>
      <article className="shift-variance-card"><span>Total variance by physical currency</span>{totalVariance.length ? totalVariance.map((row) => <strong key={row.currency_code}>{money(row.amount, row.currency_code)}</strong>) : <strong>—</strong>}<small>Never converted or combined across currencies</small></article>
    </section>

    <section className="shift-table-panel">
      <div className="shift-table-heading"><div><h2>Shifts</h2><p>{page.total} matching records · newest opened first</p></div></div>
      <div className="shift-table-scroll"><table className="shift-table"><thead><tr><th>Shift</th><th>Cashier</th><th>Shop / branch</th><th>Register</th><th>Opened</th><th>Closed</th><th>Status</th><th>Opening cash</th><th>Expected</th><th>Counted</th><th>Variance</th><th>Details</th></tr></thead>
        <tbody>{items.map((shift) => <tr key={shift.id}>
          <td data-label="Shift"><strong>{shift.shift_number}</strong><small>{shift.id.slice(0, 8).toUpperCase()}</small></td>
          <td data-label="Cashier">{shift.cashier_name || "Unknown cashier"}</td>
          <td data-label="Shop / branch">{[shift.shop_name, shift.branch_name].filter(Boolean).join(" — ") || "Unknown branch"}</td>
          <td data-label="Register">{shift.register_name || "Unknown register"}</td>
          <td data-label="Opened">{new Date(shift.opened_at).toLocaleString()}</td>
          <td data-label="Closed">{shift.closed_at ? new Date(shift.closed_at).toLocaleString() : "—"}</td>
          <td data-label="Status"><span className={`shift-status shift-status-${shift.status}`}>{shift.status === "open" ? "Open" : "Closed"}</span></td>
          <td data-label="Opening cash">{multiCurrency(shift.currencies, "opening_float")}</td>
          <td data-label="Expected">{multiCurrency(shift.currencies, "expected_cash")}</td>
          <td data-label="Counted">{multiCurrency(shift.currencies, "counted_cash")}</td>
          <td data-label="Variance">{multiCurrency(shift.currencies, "variance")}</td>
          <td data-label="Details"><button type="button" className="shift-detail-button" onClick={() => void openDetails(shift)}>View</button></td>
        </tr>)}
        {!items.length && !loading && <tr><td colSpan={12} className="shift-empty">No shifts match these filters.</td></tr>}
        {loading && <tr><td colSpan={12} className="shift-empty">Loading shift report…</td></tr>}
        </tbody></table></div>
      <Pagination meta={page} onPage={(next) => void load(next)} />
    </section>

    {detailLoading && <div className="shift-modal-backdrop" role="presentation"><section className="shift-modal" role="dialog" aria-modal="true" aria-label="Shift details"><p>Loading shift details…</p></section></div>}
    {selected && <div className="shift-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}>
      <section className="shift-modal" role="dialog" aria-modal="true" aria-labelledby="shift-detail-title">
        <header><div><h2 id="shift-detail-title">{selected.shift_number}</h2><p>{selected.cashier_name || "Unknown cashier"} · {selected.shop_name || "Unknown shop"} · {selected.branch_name || "Unknown branch"} · {selected.register_name || "Unknown register"}</p></div><button type="button" aria-label="Close shift details" onClick={() => setSelected(null)}>Close</button></header>
        <div className="shift-detail-facts"><span>Status <b>{selected.status === "open" ? "Open" : "Closed"}</b></span><span>Opened <b>{new Date(selected.opened_at).toLocaleString()}</b></span><span>Closed <b>{selected.closed_at ? new Date(selected.closed_at).toLocaleString() : "Still open"}</b></span><span>Cashier role <b>{selected.cashier_role || "—"}</b></span></div>
        {selected.opening_note && <p className="shift-note"><b>Opening note:</b> {selected.opening_note}</p>}
        {selected.closing_note && <p className="shift-note"><b>Closing note:</b> {selected.closing_note}</p>}
        <h3>Sales and payment methods ({selected.summary.base_currency_code || summaryCurrency})</h3>
        <div className="shift-detail-metrics">
          <span>Gross sales <b>{money(selected.summary.gross_sales_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
          <span>Net sales <b>{money(selected.summary.net_sales_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
          <span>Cash sales <b>{money(selected.summary.cash_sales_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
          <span>Card sales <b>{money(selected.summary.card_sales_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
          <span>Mobile sales <b>{money(selected.summary.mobile_sales_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
          <span>Credit sales <b>{money(selected.summary.credit_sales_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
          <span>Cash settlements <b>{money(selected.summary.cash_settlements_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
          <span>Cash received <b>{money(selected.summary.cash_received_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
          <span>Cash paid out <b>{money(selected.summary.cash_paid_out_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
          <span>Refunds <b>{money(selected.summary.refunds_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
          <span>Cash expenses <b>{money(selected.summary.cash_expenses_base, selected.summary.base_currency_code || summaryCurrency)}</b></span>
        </div>
        <h3>Cash reconciliation by physical currency</h3>
        <div className="shift-currency-detail-scroll"><table className="shift-currency-detail"><thead><tr><th>Currency</th><th>Opening</th><th>Cash sales</th><th>Cash settlements</th><th>Cash in</th><th>Cash out</th><th>Refunds</th><th>Cash expenses</th><th>Expected</th><th>Counted</th><th>Variance</th></tr></thead><tbody>
          {selected.currencies.map((row) => <tr key={row.currency_code}><td>{row.currency_name} ({row.currency_code})</td><td>{money(row.opening_float, row.currency_code, row.symbol, row.decimal_places)}</td><td>{money(row.cash_sales, row.currency_code, row.symbol, row.decimal_places)}</td><td>{money(row.cash_settlements, row.currency_code, row.symbol, row.decimal_places)}</td><td>{money(row.cash_in, row.currency_code, row.symbol, row.decimal_places)}</td><td>{money(row.cash_out, row.currency_code, row.symbol, row.decimal_places)}</td><td>{money(row.cash_refunds, row.currency_code, row.symbol, row.decimal_places)}</td><td>{money(row.cash_expenses, row.currency_code, row.symbol, row.decimal_places)}</td><td>{money(row.expected_cash, row.currency_code, row.symbol, row.decimal_places)}</td><td>{row.counted_cash === null ? "Not counted" : money(row.counted_cash, row.currency_code, row.symbol, row.decimal_places)}</td><td>{row.variance === null ? "Open" : money(row.variance, row.currency_code, row.symbol, row.decimal_places)}</td></tr>)}
          {!selected.currencies.length && <tr><td colSpan={11}>No currency snapshots available for this shift.</td></tr>}
        </tbody></table></div>
        <p className="shift-base-note">Accounting totals are in the company base currency. Physical drawer amounts and variance above are never combined or revalued.</p>
      </section>
    </div>}
  </div>;
}
