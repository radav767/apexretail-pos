import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import {contextGeneration} from '../api/businessSession';
import AllocationDetails from '../../../pos-web/src/printing/AllocationDetails';
import type {SplitAccounting} from '../../../pos-web/src/printing/splitReceipt';
import "./reports.css";

type Metric = { available: boolean; value: string | null; reason?: string | null };
type Option = { id: string; name: string };
type Report = {
  view: string; reporting_timezone: string; currency_symbol: string; decimal_places: number;
  total: number; limit: number; offset: number;
  summary: Record<string, any>; rows: Array<Record<string, any>>;
  options: Record<string, Option[]>;
};

const views = [
  ["individual", "Individual sales and receipts"], ["cashier", "Sales by cashier"],
  ["product", "Sales by product"], ["category", "Sales by category"],
  ["payment_type", "Sales by payment type"], ["shop_branch", "Sales by shop/branch"],
  ["credit_sales", "Credit sales"], ["refunds_cancellations", "Refunds and cancellations"],
];

function localDate(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
function reportingDate(timeZone:string){const parts=new Intl.DateTimeFormat('en',{timeZone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const value=(kind:string)=>parts.find(p=>p.type===kind)!.value;return `${value('year')}-${value('month')}-${value('day')}`;}

function initialFilters(monthStart: Date, today: Date) {
  const defaults = { view: "individual", date_from: localDate(monthStart), date_to: localDate(today), shop_id: "", branch_id: "", cashier_id: "", product_id: "", category_id: "", payment_method: "", sort_by: "date", sort_dir: "desc", limit: "25", offset: "0" };
  if (typeof window === "undefined") return defaults;
  const search = new URLSearchParams(window.location.search);
  return Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, search.get(`sales_${key}`) || value])) as typeof defaults;
}

function showMetric(metric: Metric | undefined, report: Report | null, percent = false) {
  if (!metric?.available) return <span className="reports-unavailable" title={metric?.reason || "Unavailable"}>Unavailable</span>;
  if (percent) return `${Number(metric.value).toFixed(2)}%`;
  return `${report?.currency_symbol || "$"}${Number(metric.value).toFixed(report?.decimal_places ?? 2)}`;
}

export default function SalesHistoryPage({ companyId }: { companyId: string }) {
  const today = useMemo(() => new Date(), []);
  const monthStart = useMemo(() => new Date(today.getFullYear(), today.getMonth(), 1), [today]);
  const [filters, setFilters] = useState(() => initialFilters(monthStart, today));
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [receipt,setReceipt]=useState<{receipt_number:string;payment_method:string;total_amount:string;split_accounting?:SplitAccounting|null;items:Array<{id:string;product_name:string;quantity:string;line_total:string}>}|null>(null);
  const sequence=useRef(0);
  const receiptSequence=useRef(0),[contextTick,setContextTick]=useState(0);
  const defaultDates=useRef(!new URLSearchParams(window.location.search).has('sales_date_from')&&!new URLSearchParams(window.location.search).has('sales_date_to'));
  function guard(){const epoch=contextGeneration(),token=sessionStorage.getItem('backoffice_token');return ()=>epoch===contextGeneration()&&token===sessionStorage.getItem('backoffice_token')&&companyId===sessionStorage.getItem('backoffice_company_id');}
  useEffect(()=>{setReceipt(null);setReport(null);const clear=()=>{sequence.current++;receiptSequence.current++;setReceipt(null);setReport(null);setContextTick(value=>value+1)};window.addEventListener('business-context-changed',clear);return()=>{sequence.current++;receiptSequence.current++;window.removeEventListener('business-context-changed',clear)}},[companyId]);
  async function viewReceipt(id:string){const current=guard(),request=++receiptSequence.current;try{const {data}=await api.get(`/sales/receipt/${companyId}/${id}`,{params:{mark_reprint:false}});if(current()&&request===receiptSequence.current)setReceipt(data)}catch{if(current()&&request===receiptSequence.current)setError('Cannot read this receipt with the current account.')}}

  const params = useCallback(() => Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== "")), [filters]);
  const load = useCallback(async () => {
    if (!companyId || filters.date_from > filters.date_to) { setError("Choose a valid date range."); return; }
    setLoading(true); setError("");
    const current=guard(),request=++sequence.current;
    try { const response = await api.get(`/reports/sales-history/${companyId}`, { params: params() }); if(current()&&request===sequence.current){if(defaultDates.current){defaultDates.current=false;const date=reportingDate(response.data.reporting_timezone);if(date!==filters.date_to){setFilters(old=>({...old,date_to:date,date_from:date.slice(0,7)+'-01',offset:'0'}));return}}setReport(response.data);} }
    catch (requestError: any) { if(current()&&request===sequence.current){setReport(null); setError(requestError?.response?.status === 403 ? "You do not have reports permission." : requestError?.response?.data?.detail || "Failed to load Sales History.");} }
    finally { if(current()&&request===sequence.current)setLoading(false); }
  }, [companyId, filters.date_from, filters.date_to, params,contextTick]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const search = new URLSearchParams(window.location.search);
    Object.entries(filters).forEach(([key, value]) => value ? search.set(`sales_${key}`, value) : search.delete(`sales_${key}`));
    window.history.replaceState(null, "", `${window.location.pathname}?${search.toString()}${window.location.hash}`);
  }, [filters]);
  function update(name: string, value: string, resetPage = true) { if(name==='date_from'||name==='date_to')defaultDates.current=false;setFilters(current => ({ ...current, [name]: value, ...(resetPage ? { offset: "0" } : {}) })); }
  async function exportCsv() {
    try {
      const response = await api.get(`/reports/sales-history/${companyId}/export.csv`, { params: params(), responseType: "blob" });
      const url = URL.createObjectURL(response.data); const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `sales-history-${filters.date_from}-${filters.date_to}.csv`; anchor.click(); URL.revokeObjectURL(url);
    } catch (requestError: any) { setError(requestError?.response?.data?.detail || "Failed to export Sales History."); }
  }
  const options = report?.options || {};
  const offset = Number(filters.offset); const limit = Number(filters.limit);

  return <div className="reports-page sales-history-page">
    <section className="reports-toolbar">
      <div><h2>Sales History</h2><p>Transaction and grouped views use {report?.reporting_timezone || "Africa/Harare"} reporting dates.</p></div>
      <div className="reports-filter-grid">
        <label>Report view<select aria-label="Report view" value={filters.view} onChange={e => update("view", e.target.value)}>{views.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Date from<input type="date" value={filters.date_from} onChange={e => update("date_from", e.target.value)} /></label>
        <label>Date to<input type="date" value={filters.date_to} onChange={e => update("date_to", e.target.value)} /></label>
        <Filter label="Shop" name="shop_id" value={filters.shop_id} options={options.shops} update={update} />
        <Filter label="Branch" name="branch_id" value={filters.branch_id} options={options.branches} update={update} />
        <Filter label="Cashier" name="cashier_id" value={filters.cashier_id} options={options.cashiers} update={update} />
        <Filter label="Product" name="product_id" value={filters.product_id} options={options.products} update={update} />
        <Filter label="Category" name="category_id" value={filters.category_id} options={options.categories} update={update} />
        <label>Payment type<input value={filters.payment_method} onChange={e => update("payment_method", e.target.value)} placeholder="All payment types" /></label>
        <label>Sort by<select value={filters.sort_by} onChange={e => update("sort_by", e.target.value)}><option value="date">Date</option><option value="amount">Amount</option><option value="label">Name / receipt</option><option value="transactions">Transactions</option><option value="quantity">Quantity</option></select></label>
        <label>Direction<select value={filters.sort_dir} onChange={e => update("sort_dir", e.target.value)}><option value="desc">Descending</option><option value="asc">Ascending</option></select></label>
      </div>
      <div className="reports-presets"><button onClick={() => void load()} disabled={loading}>{loading ? "Loading…" : "Run report"}</button><button onClick={() => void exportCsv()} disabled={loading}>Export CSV</button></div>
    </section>
    {error && <p className="reports-message" role="alert">{error}</p>}
    {receipt&&<section role="dialog" aria-label={`Receipt ${receipt.receipt_number}`}><h2>Receipt {receipt.receipt_number}</h2><p>{receipt.payment_method} · Total {receipt.total_amount}</p><ul>{receipt.items.map(item=><li key={item.id}>{item.product_name} · {item.quantity} · {item.line_total}</li>)}</ul><AllocationDetails accounting={receipt.split_accounting} total={receipt.total_amount} method={receipt.payment_method}/><button type="button" onClick={()=>{receiptSequence.current++;setReceipt(null)}}>Close receipt</button></section>}
    {loading && <section className="reports-panel reports-empty">Loading Sales History…</section>}
    {!loading && report && <>
      <section className="reports-summary-grid">
        <article><span>Gross sales</span><strong>{report.currency_symbol}{Number(report.summary.gross_sales).toFixed(report.decimal_places)}</strong></article>
        <article><span>Refunds</span><strong>{report.currency_symbol}{Number(report.summary.refunds).toFixed(report.decimal_places)}</strong></article>
        <article><span>Net sales</span><strong>{report.currency_symbol}{Number(report.summary.net_sales).toFixed(report.decimal_places)}</strong></article>
        <article><span>Cost of sales</span><strong>{showMetric(report.summary.cost_of_sales, report)}</strong></article>
        <article><span>Gross profit</span><strong>{showMetric(report.summary.gross_profit, report)}</strong></article>
      </section>
      <section className="reports-panel"><div className="reports-panel-header"><div><h2>{views.find(([key]) => key === report.view)?.[1]}</h2><p>{report.total} matching row{report.total === 1 ? "" : "s"}</p></div></div>
        <div className="reports-table-wrapper"><table><thead><tr><th>Name / receipt</th><th>Date</th><th>Transactions</th><th>Quantity</th><th>Amount</th><th>Cost</th><th>Gross profit</th><th>Discount</th><th>Status / payment</th></tr></thead>
          <tbody>{report.rows.length ? report.rows.map((row,index) => <tr key={String(row.dimension_id || index)}><td><strong>{String(row.label || "Unavailable")}</strong>{report.view==="individual"&&row.dimension_id&&<button type="button" onClick={()=>void viewReceipt(String(row.dimension_id))}>View receipt</button>}</td><td>{row.created_at ? new Date(row.created_at).toLocaleString() : "—"}</td><td>{row.transactions}</td><td>{row.quantity ?? "—"}</td><td>{report.currency_symbol}{Number(row.amount).toFixed(report.decimal_places)}</td><td>{showMetric(row.cost, report)}</td><td>{showMetric(row.gross_profit, report)}</td><td>{showMetric(row.discount, report)}</td><td>{[row.status,row.payment_method].filter(Boolean).join(" / ") || "—"}</td></tr>) : <tr><td colSpan={9} className="reports-empty">No sales match these filters.</td></tr>}</tbody></table></div>
        <div className="reports-pagination"><span>{report.total ? `${offset + 1}–${Math.min(offset + limit, report.total)} of ${report.total}` : "0 results"}</span><button disabled={offset === 0} onClick={() => update("offset", String(Math.max(0, offset-limit)), false)}>Previous</button><button disabled={offset + limit >= report.total} onClick={() => update("offset", String(offset+limit), false)}>Next</button></div>
      </section>
    </>}
  </div>;
}

function Filter({ label, name, value, options = [], update }: { label: string; name: string; value: string; options?: Option[]; update: (name:string,value:string)=>void }) {
  return <label>{label}<select value={value} onChange={e => update(name,e.target.value)}><option value="">All {label.toLowerCase()}s</option>{options.map(option => <option key={option.id} value={option.id}>{option.name}</option>)}</select></label>;
}
