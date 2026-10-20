import { useEffect, useState } from "react";
import { api } from "../api/client";
import TipPaymentPanel from "../../../pos-web/src/business/TipPaymentPanel";
import "../../../pos-web/src/business/business.css";
import "../../../pos-web/src/business/business-mobile.css";
type Config = { enabled: boolean; policy: string; weights: Record<string, number>; business_retention_confirmed: boolean; service_product_id: string | null; legacy_queue_review_required?: boolean; legacy_queues_reviewed?: boolean };
const tipErrorMessage = (error: unknown) => {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === "string" ? detail : "Tip operation failed";
};
export default function TipsSettingsPanel({ companyId }: { companyId: string }) {
  const [config, setConfig] = useState<Config>({ enabled: false, policy: "staff", weights: {}, business_retention_confirmed: false, service_product_id: null });
  const [options, setOptions] = useState<{ branches?: { id: string; name: string }[]; employees: { id: string; name: string; active: boolean; branch_name?: string }[]; products: { id: string; name: string }[] }>({ employees: [], products: [] });
  const [branch, setBranch] = useState("");
  const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);
  const [start, setStart] = useState(new Date().toISOString().slice(0,10)); const [end, setEnd] = useState(new Date().toISOString().slice(0,10));
  const [report, setReport] = useState<{ net_tip_receipts?: { currency: string; method: string; policy: string; amount: string }[]; totals: { currency: string; method: string; kind: string; policy: string; amount: string }[]; balances: { employee: string; currency: string; outstanding: string; overpaid_after_reversal: boolean }[]; entries: { id: string; kind: string; method: string; currency: string; amount: string; reference: string }[] } | null>(null);
  const errorMessage = tipErrorMessage;
  useEffect(() => { void Promise.all([api.get("/operations/tips/config"), api.get("/operations/tips/options")]).then(([settings, data]) => { setConfig(settings.data); setOptions(data.data); }).catch(error => setMessage(errorMessage(error))); }, [companyId, errorMessage]);
  return <section className="business-operations"><h2>Tips & Service Charges</h2><form className="business-form" onSubmit={event => {
    event.preventDefault(); if (busy) return; setBusy(true); void api.put("/operations/tips/config", config).then(({ data }) => { setConfig(data); setMessage("Tip policy saved. Existing entitlements are unchanged."); }).catch(error => setMessage(errorMessage(error))).finally(() => setBusy(false));
  }}>
    <label>Enable separate tips<input type="checkbox" checked={config.enabled} onChange={e => setConfig({ ...config, enabled: e.target.checked })}/></label>
    {config.legacy_queue_review_required && <label><input required type="checkbox" checked={Boolean(config.legacy_queues_reviewed)} onChange={e => setConfig({ ...config, legacy_queues_reviewed: e.target.checked })}/>I reviewed pending legacy tip-product transactions on every terminal. No offline queue will be cleared.</label>}
    <label>Tip policy<select value={config.policy} onChange={e => setConfig({ ...config, policy: e.target.value })}><option value="staff">Staff tips — serving employee</option><option value="shared">Shared tips — weighted distribution</option><option value="business">Business tips — separate business income</option></select></label>
    {config.policy === "business" && <label><input type="checkbox" checked={config.business_retention_confirmed} onChange={e => setConfig({ ...config, business_retention_confirmed: e.target.checked })}/>Owner confirms business retention is permitted for this business</label>}
    {config.policy === "shared" && <fieldset><legend>Eligible staff & distribution weights</legend><p>Only active eligible employees in the processing branch share each tip. Shares are saved when received.</p>{options.employees.filter(employee => employee.active).map(employee => <label key={employee.id}>{employee.name}<input aria-label={`Tip weight ${employee.name}`} type="number" min="0" max="10000" step="1" value={config.weights[employee.id] || 0} onChange={e => {
      const weights = { ...config.weights }; if (Number(e.target.value) > 0) weights[employee.id] = Number(e.target.value); else delete weights[employee.id]; setConfig({ ...config, weights });
    }}/></label>)}</fieldset>}
    <label>Separate service-charge product<select value={config.service_product_id || ""} onChange={e => setConfig({ ...config, service_product_id: e.target.value || null })}><option value="">No configured charge</option>{options.products.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>
    <p>Service charges retain their reviewed product/tax settings. No automatic percentage or payroll deduction is applied.</p><button disabled={busy}>Save policy</button>
  </form><h3>Tip reporting</h3><form className="business-form" onSubmit={event => { event.preventDefault(); void api.get(`/operations/tips/reports?start=${start}&end=${end}${branch ? `&branch_id=${branch}` : ""}`).then(({ data }) => setReport(data)).catch(error => setMessage(errorMessage(error))); }}><label>Branch<select value={branch} onChange={e => setBranch(e.target.value)}><option value="">All authorized branches</option>{options.branches?.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>From (UTC)<input type="date" required value={start} onChange={e => setStart(e.target.value)}/></label><label>To (UTC)<input type="date" required value={end} onChange={e => setEnd(e.target.value)}/></label><button>View tip report</button></form>
    {report && <><h3>Net tip receipts — after refunds, separate from payouts</h3><div className="business-records">{report.net_tip_receipts?.map((row, index) => <article key={index}><strong>{row.policy === "business" ? "Business tip income" : "Staff tip receipts"} · {row.method}</strong><p>{row.currency} {row.amount}</p></article>)}</div><div className="business-records">{report.totals.map((row, index) => <article key={index}><strong>{row.kind} · {row.method} · {row.policy}</strong><p>{row.currency} {row.amount}</p></article>)}</div><h3>Employee outstanding balances (all time)</h3><div className="business-records">{report.balances.map((row, index) => <article key={index}><strong>{row.employee}</strong><p>{row.currency} {row.outstanding}</p>{row.overpaid_after_reversal && <p role="alert">Paid tip was reversed — manager review required. No payroll deduction created.</p>}</article>)}</div>
      <details><summary>Tip references for refunds</summary>{report.entries.map(entry => <article key={entry.id}><strong>{entry.kind} · {entry.currency} {entry.amount} · {entry.method}</strong><label>Tip reference<input readOnly value={entry.id}/></label></article>)}</details>
      <button onClick={() => {
        const rows = [["Currency","Method","Kind","Policy","Amount"], ...report.totals.map(row => [row.currency,row.method,row.kind,row.policy,row.amount])];
        const csv = rows.map(row => row.map(value => { const text = /^[\s]*[=+\-@]/.test(String(value)) ? `'${value}` : String(value); return `"${text.replaceAll('"','""')}"`; }).join(",")).join("\n");
        const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); const link = document.createElement("a"); link.href=url; link.download="tip-report.csv"; link.click(); URL.revokeObjectURL(url);
      }}>Export tip totals CSV</button></>}
    <TipPaymentPanel key={companyId} api={api} companyId={companyId} management />{message && <p role="status">{message}</p>}
  </section>;
}
