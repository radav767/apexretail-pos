import { useEffect, useRef, useState } from "react";
import "./business.css";
import "./business-mobile.css";
type Api = { get: (url: string) => Promise<{ data: any }>; post: (url: string, data: unknown) => Promise<{ data: any }> };
type Pending = { payload: Record<string, unknown>; acknowledged: boolean; receipt?: string; rejectedValidation?: boolean };
export default function TipPaymentPanel({ api, companyId, saleId = "", management = false }: {
  api: Api; companyId: string; saleId?: string; management?: boolean;
}) {
  const [options, setOptions] = useState<{ shifts: { id: string; name: string }[]; currencies: { code: string }[]; employees: { id: string; name: string }[] }>({ shifts: [], currencies: [], employees: [] });
  const [kind, setKind] = useState(saleId ? "collect" : "reverse"); const [shift, setShift] = useState(""); const [employee, setEmployee] = useState("");
  const [original, setOriginal] = useState(""); const [currency, setCurrency] = useState(""); const [method, setMethod] = useState("cash");
  const [amount, setAmount] = useState(""); const [reason, setReason] = useState(""); const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const recording = useRef(false);
  const [online, setOnline] = useState(navigator.onLine);
  const identity = `${companyId}:${localStorage.getItem("employee_id") || "backoffice"}:${localStorage.getItem("device_id") || "backoffice"}`;
  const key = `apexretail_tip_record_v1:${identity}:${saleId || "management"}`;
  const [pending, setPending] = useState<Pending | null>(() => {
    try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return { payload: {}, acknowledged: false }; }
  });
  useEffect(() => { const status = () => setOnline(navigator.onLine); window.addEventListener("online", status); window.addEventListener("offline", status); return () => { window.removeEventListener("online", status); window.removeEventListener("offline", status); }; }, []);
  useEffect(() => { if (online) void api.get("/operations/tips/options").then(({ data }) => { setOptions(data); setShift(data.shifts[0]?.id || ""); setCurrency(data.currencies[0]?.code || ""); }).catch(error => setMessage(error.response?.data?.detail || "Tip access unavailable")); }, [api, online]);
  async function record() {
    if (recording.current || !online) return;
    recording.current = true;
    setBusy(true); setMessage("");
    try {
      const saved = pending || JSON.parse(localStorage.getItem(key) || "null") || { payload: { request_id: crypto.randomUUID(), shift_id: shift, kind,
        sale_id: kind === "collect" ? saleId : null, original_id: kind === "reverse" ? original : null,
        employee_id: kind === "payout" ? employee : null, payment_method: method, currency_code: currency,
        amount, reason, reference, confirmed: true }, acknowledged: false };
      if (!saved.payload.request_id) throw new Error("Stored request needs review; no recovery data has been cleared");
      localStorage.setItem(key, JSON.stringify(saved)); setPending(saved);
      const response = await api.post("/operations/tips/entries", saved.payload);
      if (typeof response.data?.id !== "string") throw new Error("No tip receipt returned; retain the original request");
      const acknowledged = { ...saved, acknowledged: true, receipt: response.data.id };
      localStorage.setItem(key, JSON.stringify(acknowledged)); setPending(acknowledged);
      setMessage("Tip transfer recorded. Product sale and stock are unchanged.");
    } catch (error) {
      const status = (error as { response?: { status?: number } }).response?.status;
      if (status === 400 || status === 422) {
        try { const original = JSON.parse(localStorage.getItem(key) || "null") as Pending | null; if (original) { const rejected = { ...original, rejectedValidation: true }; localStorage.setItem(key, JSON.stringify(rejected)); setPending(rejected); } } catch { /* Preserve whatever storage remains; never claim success. */ }
      }
      setMessage((error as { response?: { data?: { detail?: string } } }).response?.data?.detail || "Recording not confirmed. Keep this request and retry recording only — do not transfer money again.");
    } finally { recording.current = false; setBusy(false); }
  }
  return <details className="business-operations business-details"><summary>{management ? "Record tip refund / employee payout" : "Record separate tip payment"}</summary>
    <p className="business-warning">Online only. Record an already confirmed transfer. Tips are separate from the product receipt and service charges.</p>
    {pending ? <><p>{pending.acknowledged ? "Recorded" : "Pending confirmation — do not transfer money again"}</p>
      <p>{String(pending.payload.currency_code || "")} {String(pending.payload.amount || "")} · {String(pending.payload.payment_method || "")}</p><details><summary>Original transfer details</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(pending.payload, null, 2)}</pre></details>
      {pending.acknowledged ? <button onClick={() => { localStorage.setItem(`${key}:ack:${String(pending.payload.request_id)}`, JSON.stringify(pending)); localStorage.setItem(key, "null"); setPending(null); }}>New tip record</button>
        : <><button disabled={busy || !online} onClick={() => void record()}>Retry recording original transfer</button>{pending.rejectedValidation && <button onClick={() => {
          localStorage.setItem(`${key}:rejected:${String(pending.payload.request_id)}`, JSON.stringify(pending)); localStorage.setItem(key, "null"); setPending(null);
        }}>Correct rejected request (original archived)</button>}</>}</> :
      <form className="business-form" onSubmit={event => { event.preventDefault(); if (confirm("Has this tip payment, refund or payout actually occurred? This records it; it does not transfer money.")) void record(); }}>
        <label>Action<select value={kind} onChange={e => setKind(e.target.value)}>{saleId && <option value="collect">Receive tip</option>}{management && <><option value="reverse">Refund original tip</option><option value="payout">Employee payout</option></>}</select></label>
        <label>Processing shift<select required value={shift} onChange={e => setShift(e.target.value)}><option value="">Select shift</option>{options.shifts.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        {kind === "reverse" && <label>Original tip reference<input required value={original} onChange={e => setOriginal(e.target.value)}/></label>}
        {kind === "payout" && <label>Employee<select required value={employee} onChange={e => setEmployee(e.target.value)}><option value="">Select employee</option>{options.employees.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>}
        <label>Payment method<select value={method} onChange={e => setMethod(e.target.value)}><option value="cash">Cash (authenticated POS register)</option><option value="card">Card</option><option value="mobile">Mobile money</option></select></label>
        <label>Currency<select required value={currency} onChange={e => setCurrency(e.target.value)}>{options.currencies.map(row => <option key={row.code}>{row.code}</option>)}</select></label>
        <label>Amount<input required type="number" min="0.0001" step="0.0001" value={amount} onChange={e => setAmount(e.target.value)}/></label>
        <label>Reason<input required minLength={3} maxLength={500} value={reason} onChange={e => setReason(e.target.value)}/></label>
        <label>Transfer reference<input maxLength={120} value={reference} onChange={e => setReference(e.target.value)}/></label>
        <button disabled={busy || !online || !shift || (kind === "collect" && !saleId)}>Confirm & record transfer</button>
      </form>}{message && <p role="status">{message}</p>}
  </details>;
}
