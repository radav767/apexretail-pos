import { useCallback, useEffect, useRef, useState } from "react";
import type { Station, PrintJob } from "./queue";
import "./printers.css";

type Api = { get: <T = any>(url: string) => Promise<{ data: T }>; post: <T = any>(url: string, data?: unknown) => Promise<{ data: T }>; put: (url: string, data: unknown) => Promise<unknown> };
type Option = { id: string; name: string; branch_id?: string; shop_id?: string };
type Options = Record<"shops" | "branches" | "devices" | "products" | "categories", Option[]>;
const emptyOptions: Options = { shops: [], branches: [], devices: [], products: [], categories: [] };
const blank = { name: "", shop_id: "", branch_id: "", device_id: "", purpose: "receipt", transport: "system", address: "", paper_width: "80mm", auto_print: false, active: true, routes: [] } as Omit<Station, "id" | "company_id">;
const message = (error: unknown) => (error as { response?: { data?: { detail?: string } } }).response?.data?.detail || (error instanceof Error ? error.message : "Request failed");
function PrinterIcon() { return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M6 8V3h12v5M6 17H3V8h18v9h-3M6 14h12v7H6zM17 11h1"/></svg>; }

export default function PrinterManagement({ companyId, api, canManage = false, deviceId, deliver, approve }: {
  companyId: string; api: Api; canManage?: boolean; deviceId?: string;
  deliver?: (job: PrintJob) => Promise<void>;
  approve?: (request: { action: "print_retry" | "receipt_reprint"; reason: string; context: Record<string, unknown> }, callback: (token: string) => void) => void;
}) {
  const [stations, setStations] = useState<Station[]>([]);
  const [options, setOptions] = useState<Options>(emptyOptions);
  const [view, setView] = useState<"home" | "stations" | "routes" | "queue">("home");
  const [selected, setSelected] = useState("");
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ ...blank });
  const [jobs, setJobs] = useState<PrintJob[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [saleId, setSaleId] = useState("");
  const [table, setTable] = useState("");
  const [notes, setNotes] = useState("");
  const [reason, setReason] = useState("");
  const requestKeys = useRef(new Map<string, string>());
  const station = stations.find(s => s.id === selected);
  function navigate(next: typeof view) {
    setView(next); const url = new URL(location.href); url.searchParams.set("printer_view", next); history.pushState({}, "", url);
  }
  useEffect(() => {
    const restore = () => { const v = new URL(location.href).searchParams.get("printer_view"); setView(v === "stations" || v === "routes" || v === "queue" ? v : "home"); };
    restore(); window.addEventListener("popstate", restore); return () => window.removeEventListener("popstate", restore);
  }, []);
  const refresh = useCallback(async () => {
    const { data } = await api.get<Station[]>(`/printing/stations/${companyId}`);
    const visible = deviceId ? data.filter(s => s.device_id === deviceId) : data;
    setStations(visible);
    if (!selected && visible.length) setSelected(visible[0].id);
    if (canManage) setOptions((await api.get<Options>(`/printing/options/${companyId}`)).data);
  }, [api, companyId, deviceId, canManage, selected]);
  useEffect(() => { void refresh().catch(e => setError(message(e))); }, [refresh]);
  useEffect(() => {
    if (selected) void api.get<PrintJob[]>(`/printing/station/${selected}/jobs`).then(r => setJobs(r.data)).catch(e => setError(message(e)));
  }, [api, selected, view]);
  async function run(action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await action(); await refresh(); if (selected) setJobs((await api.get<PrintJob[]>(`/printing/station/${selected}/jobs`)).data); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  async function save() {
    if (editing && selected) await api.put(`/printing/station/${selected}`, form);
    else { const { data } = await api.post<{ id: string }>("/printing/stations", form); setSelected(data.id); }
    setNotice("Printer station saved"); setEditing(false);
  }
  async function queue(kind: "receipt" | "kot" | "test", reprint = false, token?: string) {
    const identity = `${selected}:${saleId}:${kind}:${reprint}`;
    const request_key = requestKeys.current.get(identity) || crypto.randomUUID();
    requestKeys.current.set(identity, request_key);
    const { data } = await api.post<PrintJob>(`/printing/station/${selected}/jobs`, { kind, sale_id: kind === "test" ? null : saleId, request_key, reprint, table, notes, manager_authorization: token });
    if (deliver) await deliver(data);
    requestKeys.current.delete(identity);
    setNotice(deliver ? "Submitted to printer. Check paper output." : "Queued for the assigned POS register.");
  }
  return <section className="printer-management">
    <header><div><span className="printer-eyebrow">Settings</span><h2><PrinterIcon/> Printers & kitchen</h2></div>{view !== "home" && <button onClick={() => navigate("home")}>← Back</button>}</header>
    {error && <p role="alert" className="printer-error">{error}</p>}{notice && <p role="status" className="printer-notice">{notice}</p>}
    {view === "home" ? <div className="printer-feature-grid">{([ ["stations", "Printer stations", "Receipt · Kitchen · Bar"], ["routes", "Product routing", "Products & categories"], ["queue", "Print queue", "Delivery & recovery"] ] as const).filter(([id]) => canManage || id !== "routes").map(([id, title, subtitle]) => <button key={id} onClick={() => navigate(id)}><PrinterIcon/><strong>{title}</strong><small>{subtitle}</small></button>)}</div> : <>
      <div className="printer-toolbar"><label>Printer station<select value={selected} onChange={e => { setSelected(e.target.value); setEditing(false); }}>{!stations.length && <option value="">No stations configured</option>}{stations.map(s => <option key={s.id} value={s.id}>{s.name} · {s.purpose}{!s.active ? " (inactive)" : ""}</option>)}</select></label><button disabled={busy} onClick={() => void run(refresh)}>Refresh</button></div>
      {view === "stations" && <>
        {station && <div className="printer-status-card"><PrinterIcon/><div><strong>{station.name}</strong><p>{station.transport.toUpperCase()} · {station.paper_width} · {station.active ? "Enabled" : "Inactive"}</p><small>Hardware status: unknown until tested</small></div></div>}
        {canManage && <div className="printer-actions"><button onClick={() => { setEditing(false); setForm({ ...blank, device_id: deviceId || "" }); }}>Add printer</button><button disabled={!station} onClick={() => { if (station) { setEditing(true); setForm({ ...station }); } }}>Edit selected</button><button disabled={!station || busy} onClick={() => void run(() => queue("test"))}>Test print</button></div>}
        {canManage && <form onSubmit={e => { e.preventDefault(); void run(save); }} className="printer-form">
          <label>Station name<input required maxLength={80} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}/></label>
          <label>Register<select required disabled={editing} value={form.device_id} onChange={e => { const d = options.devices.find(d => d.id === e.target.value); if (d) setForm({ ...form, device_id: d.id, branch_id: d.branch_id!, shop_id: d.shop_id! }); }}><option value="">Choose register</option>{options.devices.filter(d => !deviceId || d.id === deviceId).map(d => <option key={d.id} value={d.id}>{d.name} · {options.branches.find(b => b.id === d.branch_id)?.name}</option>)}</select></label>
          <label>Station type<select value={form.purpose} onChange={e => setForm({ ...form, purpose: e.target.value as Station["purpose"] })}>{["receipt", "kitchen", "bar"].map(v => <option key={v}>{v}</option>)}</select></label>
          <label>Connection<select value={form.transport} onChange={e => setForm({ ...form, transport: e.target.value as Station["transport"] })}>{["system", "bluetooth", "usb", "network"].map(v => <option key={v}>{v}</option>)}</select></label>
          <label>Device address<input value={form.address} placeholder={form.transport === "network" ? "192.168.1.50:9100" : "MAC / USB device identifier"} onChange={e => setForm({ ...form, address: e.target.value })}/></label>
          <label>Paper width<select value={form.paper_width} onChange={e => setForm({ ...form, paper_width: e.target.value as Station["paper_width"] })}><option>58mm</option><option>80mm</option></select></label>
          <label className="printer-check"><input type="checkbox" checked={form.auto_print} onChange={e => setForm({ ...form, auto_print: e.target.checked })}/> Auto print completed online sales</label>
          <label className="printer-check"><input type="checkbox" checked={form.active} onChange={e => setForm({ ...form, active: e.target.checked })}/> Enabled</label>
          <button className="printer-primary" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Add station"}</button>
        </form>}
        <p className="printer-hint">Chrome uses OS print services. Direct Bluetooth, USB and LAN require a compatible Android bridge. System print dialogs require confirmation.</p>
      </>}
      {view === "routes" && canManage && station && <><h3>Route to {station.name}</h3><div className="printer-route-columns">{(["products", "categories"] as const).map(group => <div key={group}><h4>{group === "products" ? "Products" : "Categories"}</h4>{options[group].map(target => <label className="printer-check" key={target.id}><input type="checkbox" checked={station.routes.some(r => r.target_id === target.id && r.target_type === (group === "products" ? "product" : "category"))} onChange={e => {
        const target_type = group === "products" ? "product" : "category";
        const routes = e.target.checked ? [...station.routes, { target_type, target_id: target.id } as Station["routes"][number]] : station.routes.filter(r => !(r.target_id === target.id && r.target_type === target_type));
        void run(() => api.put(`/printing/station/${station.id}`, { ...station, routes }));
      }} disabled={busy}/>{target.name}</label>)}</div>)}</div></>}
      {view === "queue" && <>
        {station && <div className="printer-form"><label>Existing sale ID<input value={saleId} onChange={e => setSaleId(e.target.value)} placeholder="Paste sale reference"/></label><label>Table<input value={table} maxLength={60} onChange={e => setTable(e.target.value)}/></label><label>Preparation notes<textarea value={notes} maxLength={500} onChange={e => setNotes(e.target.value)}/></label><div className="printer-actions"><button disabled={busy || !saleId} onClick={() => void run(() => queue(station.purpose === "receipt" ? "receipt" : "kot"))}>Queue original</button><button disabled={busy || !saleId} onClick={() => void run(() => queue(station.purpose === "receipt" ? "receipt" : "kot", true))}>Reprint</button>{approve && <button disabled={busy || !saleId} onClick={() => approve({ action: "receipt_reprint", reason: "Authorize receipt/ticket reprint", context: { sale_id: saleId, station_id: selected } }, token => void run(() => queue(station.purpose === "receipt" ? "receipt" : "kot", true, token)))}>Manager reprint</button>}</div></div>}
        <label>Recovery reason<input value={reason} maxLength={240} onChange={e => setReason(e.target.value)}/></label>
        <p className="printer-hint">Submitted means accepted by the bridge, not confirmed on paper. Inspect the printer before authorizing uncertain retries.</p>
        <div className="printer-jobs">{!jobs.length && <p>No queued jobs</p>}{jobs.map(job => <article key={job.id}><div><strong>{String(job.payload.order_number || job.kind).slice(0, 60)}</strong><span className={`printer-badge ${job.status}`}>{job.status}</span><p>{new Date(job.created_at).toLocaleString()} · Attempt {job.attempts}</p>{job.last_error && <p role="status">{job.last_error}</p>}</div><div className="printer-actions">{job.status === "pending" && deliver && <button disabled={busy} onClick={() => void run(() => deliver(job))}>Print</button>}{["sending", "uncertain"].includes(job.status) && <button disabled={busy || reason.trim().length < 5} onClick={() => {
          const retry = (token?: string) => void run(() => api.post(`/printing/jobs/${job.id}/retry`, { reason, manager_authorization: token }));
          if (canManage) retry(); else approve?.({ action: "print_retry", reason, context: { job_id: job.id } }, retry);
        }}>Authorize retry</button>}</div></article>)}</div>
      </>}
    </>}
  </section>;
}
