import { useCallback, useEffect, useRef, useState } from "react";
import type { PrintJob } from "../printing/queue";
import "./business.css";
import "./business-mobile.css";
import TableLayoutEditor from "./TableLayoutEditor";
import { batchCsv, quotationHtml } from "./documents";

type Api = { get: <T = any>(url: string) => Promise<{ data: T }>; post: <T = any>(url: string, data?: unknown) => Promise<{ data: T }>; put: <T = any>(url: string, data: unknown) => Promise<{ data: T }> };
type Option = { id: string; name: string; branch_id?: string; product_id?: string; selling_price?: string; product_type?: string; role?: string };
type Profile = { profile: string; name: string; features: string[]; administrator: boolean; permissions: Record<string, boolean>; tip_product_id?: string; service_product_id?: string };
type Item = { id: string; product_id: string; variant_id: string | null; name: string; quantity: string; sent_quantity: string; price: string; unit: string; notes: string };
type Order = { id: string; number: string; kind: string; status: string; version: number; branch_id: string; device_id: string; table_id: string | null; waiter_id: string | null; guest_id: string | null; sale_id: string | null; table_name: string; waiter_name: string; estimated_subtotal: string; items: Item[] };
type Table = { id: string; branch_id: string; name: string; floor: string; seats: number; x: number; y: number; active: boolean };
type Room = { id: string; name: string; branch_id: string; active: boolean; guests: { id: string; customer_id: string }[] };
type Ticket = { id: string; status: string; purpose: string; station_name: string; print_status: string; current_table?: string; current_waiter?: string; payload: { order_number: string; title: string; table: string; waiter: string; created_at: string; items: { name: string; quantity: string; notes: string }[] } };
type Batch = { id: string; product_name: string; code: string; quantity: string; expires_on: string; expired: boolean; expires_soon: boolean };
type View = "home" | "profile" | "tables" | "orders" | "kitchen" | "bar" | "rooms" | "batches" | "quotations" | "reports";
const views: View[] = ["home", "profile", "tables", "orders", "kitchen", "bar", "rooms", "batches", "quotations", "reports"];
const titles: Record<View, string> = { home: "Business operations", profile: "Business profile", tables: "Tables & floors", orders: "Open orders", kitchen: "Kitchen display", bar: "Bar display", rooms: "Rooms & guest accounts", batches: "Batches & expiry", quotations: "Quotations", reports: "Restaurant reports" };
const profileLabels = { retail: "Retail / Supermarket", restaurant: "Restaurant / Café", bar: "Bar / Nightclub", hospitality: "Hotel / Hospitality", pharmacy: "Pharmacy", wholesale: "Hardware / Wholesale", general: "General Business" };
function FeatureIcon() { return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><path d="M3 15h7v6H3zM14 15h7v6h-7z"/></svg>; }
const errorMessage = (error: unknown) => (error as { response?: { data?: { detail?: string } } }).response?.data?.detail || (error instanceof Error ? error.message : "Request failed");

export default function BusinessOperations({ companyId, api, branchId = "", deviceId = "", deliver, onSaleCompleted, onPrintReceipt, approve }: {
  companyId: string; api: Api; branchId?: string; deviceId?: string; deliver?: (job: PrintJob) => Promise<void>;
  onSaleCompleted?: (id: string) => Promise<void>; onPrintReceipt?: (id: string) => Promise<void>;
  approve?: (request: { action: "large_discount"; reason: string; context: Record<string, unknown> }, done: (token: string) => void) => void;
}) {
  const [view, setView] = useState<View>("home");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [options, setOptions] = useState<Record<string, Option[]>>({});
  const [orders, setOrders] = useState<Order[]>([]);
  const [tables, setTables] = useState<Table[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const [recoveryReady, setRecoveryReady] = useState(true);
  const [online, setOnline] = useState(navigator.onLine);
  const [branch, setBranch] = useState(branchId); const [device, setDevice] = useState(deviceId);
  const [product, setProduct] = useState(""); const [variant, setVariant] = useState(""); const [quantity, setQuantity] = useState("1"); const [notes, setNotes] = useState("");
  const [table, setTable] = useState(""); const [waiter, setWaiter] = useState(""); const [customer, setCustomer] = useState(""); const [guest, setGuest] = useState("");
  const [name, setName] = useState(""); const [floor, setFloor] = useState("Main floor"); const [seats, setSeats] = useState("4"); const [x, setX] = useState("0"); const [y, setY] = useState("0");
  const [method, setMethod] = useState("cash"); const [received, setReceived] = useState(""); const [discount, setDiscount] = useState("0"); const [roomCharge, setRoomCharge] = useState(false);
  const [mergeTarget, setMergeTarget] = useState(""); const [batchCode, setBatchCode] = useState(""); const [expiry, setExpiry] = useState("");
  const [profileChoice, setProfileChoice] = useState("retail"); const [tip, setTip] = useState(""); const [service, setService] = useState("");
  const [folio, setFolio] = useState<{ guest_name: string; charges: { receipt_number: string; amount: string; currency: string; outstanding: string }[] } | null>(null);
  const [start, setStart] = useState(new Date().toISOString().slice(0, 10)); const [end, setEnd] = useState(new Date().toISOString().slice(0, 10));
  const [report, setReport] = useState<{ currency_totals: { currency: string; sales: string; discounts: string; orders: number }[] } | null>(null);
  const requestStorageKey = `apexretail_open_order_request_v1:${companyId}:${deviceId}:${localStorage.getItem("employee_id") || "backoffice"}`;
  const requestId = useRef(localStorage.getItem(requestStorageKey) || crypto.randomUUID());
  useEffect(() => {
    requestId.current = localStorage.getItem(requestStorageKey) || crypto.randomUUID();
    try { localStorage.setItem(requestStorageKey, requestId.current); setRecoveryReady(true); }
    catch { setRecoveryReady(false); setError("Local order recovery storage is unavailable. Existing records and queues have not been cleared."); }
  }, [requestStorageKey]);
  const allowed = useCallback((permission: string) => Boolean(profile?.administrator || profile?.permissions[permission]), [profile]);
  function navigate(next: View) { setView(next); setSelectedOrder(null); setError(""); const url = new URL(location.href); url.searchParams.set("business_view", next); history.pushState({}, "", url); }
  useEffect(() => {
    const restore = () => { const requested = new URL(location.href).searchParams.get("business_view") as View; setView(views.includes(requested) ? requested : "home"); setSelectedOrder(null); };
    const connectivity = () => setOnline(navigator.onLine);
    restore(); window.addEventListener("popstate", restore); window.addEventListener("online", connectivity); window.addEventListener("offline", connectivity);
    return () => { window.removeEventListener("popstate", restore); window.removeEventListener("online", connectivity); window.removeEventListener("offline", connectivity); };
  }, []);
  useEffect(() => {
    if (!online) return;
    void api.get<Profile>("/operations/profile").then(r => { setProfile(r.data); setProfileChoice(r.data.profile); setTip(r.data.tip_product_id || ""); setService(r.data.service_product_id || ""); setError(""); }).catch(e => setError(errorMessage(e)));
  }, [api, companyId, online]);
  useEffect(() => {
    if (!online || !profile || (!profile.administrator && !["orders_manage", "orders_settle", "hospitality_manage", "batches_view", "batches_manage", "business_settings_manage", "quotations_manage"].some(p => profile.permissions[p]))) return;
    void api.get<Record<string, Option[]>>("/operations/options").then(r => { setOptions(r.data); if (!branch && r.data.branches?.length) setBranch(r.data.branches[0].id); }).catch(e => setError(errorMessage(e)));
  }, [api, branch, profile, online]);
  const load = useCallback(async () => {
    if (!online || !profile) return;
    if (view === "tables") setTables((await api.get<Table[]>("/operations/tables")).data);
    if (view === "orders" || view === "quotations") {
      setOrders((await api.get<Order[]>(`/operations/orders${view === "quotations" ? "?kind=quotation" : ""}`)).data);
      if (profile.features.includes("restaurant") && (allowed("orders_manage") || allowed("restaurant_manage"))) setTables((await api.get<Table[]>("/operations/tables")).data);
      if (profile.features.includes("hospitality") && allowed("hospitality_manage")) setRooms((await api.get<Room[]>("/operations/rooms")).data);
    }
    if (view === "kitchen" || view === "bar") setTickets((await api.get<Ticket[]>("/operations/kitchen")).data);
    if (view === "rooms") setRooms((await api.get<Room[]>("/operations/rooms")).data);
    if (view === "batches") setBatches((await api.get<Batch[]>("/operations/batches")).data);
    setError("");
  }, [api, view, profile, allowed, online]);
  useEffect(() => { void load().catch(e => setError(errorMessage(e))); }, [load]);
  useEffect(() => { if (view !== "kitchen" && view !== "bar") return; const timer = setInterval(() => { if (navigator.onLine) void load().catch(e => setError(errorMessage(e))); }, 10000); return () => clearInterval(timer); }, [load, view]);
  async function run(action: () => Promise<unknown>) {
    if (busy || !online) return;
    setBusy(true); setError(""); setNotice("");
    try { await action(); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  const disabled = busy || !online;
  const list = (key: string) => options[key] || [];
  const selector = (label: string, value: string, change: (value: string) => void, choices: Option[], required = false) => <label>{label}<select value={value} onChange={e => change(e.target.value)} required={required}><option value="">{required ? "Choose…" : "None"}</option>{choices.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>;
  const features: { view: View; permission: string; feature?: string }[] = [
    { view: "profile", permission: "business_settings_manage" }, { view: "tables", permission: "orders_manage", feature: "restaurant" }, { view: "orders", permission: "orders_manage", feature: "restaurant" },
    { view: "kitchen", permission: "kitchen_view", feature: "restaurant" }, { view: "bar", permission: "bar_view", feature: "restaurant" }, { view: "rooms", permission: "hospitality_manage", feature: "hospitality" },
    { view: "batches", permission: "batches_view", feature: "pharmacy" }, { view: "quotations", permission: "quotations_manage", feature: "wholesale" }, { view: "reports", permission: "revenue_view", feature: "restaurant" },
  ];
  function selectOrder(order: Order) {
    setSelectedOrder(order); setSelected({}); setTable(order.table_id || ""); setWaiter(order.waiter_id || "");
    setReceived(""); setDiscount("0"); setMethod("cash"); setRoomCharge(false); setNotes(""); setProduct(""); setVariant("");
  }
  function kitchenAction(ticket: Ticket) {
    if (ticket.status === "needs_review") return { status: "acknowledged", label: "Confirm reviewed amendment" };
    if (ticket.payload.items.every(item => Number(item.quantity) <= 0)) return { status: "acknowledged", label: "Acknowledge update" };
    return ticket.status === "queued" ? { status: "preparing", label: "Start preparation" } : ticket.status === "preparing" ? { status: "ready", label: "Mark ready" } : { status: "served", label: "Mark served" };
  }
  async function createOrder() {
    if (!recoveryReady) throw new Error("Review local recovery storage before creating another order");
    const { data } = await api.post<Order>("/operations/orders", { request_id: requestId.current, branch_id: branch, device_id: device || deviceId,
      kind: view === "quotations" ? "quotation" : guest ? "room_service" : "restaurant", table_id: table || null, waiter_id: waiter || null, guest_id: guest || null, customer_id: customer || null });
    selectOrder(data); requestId.current = crypto.randomUUID();
    try { localStorage.setItem(requestStorageKey, requestId.current); }
    catch { setRecoveryReady(false); setNotice("Order saved. Local recovery storage needs review before creating another order."); }
  }
  async function settle(token?: string) {
    if (!selectedOrder) return;
    const { data } = await api.post<{ sale_id: string; order: Order; already_settled: boolean }>(`/operations/orders/${selectedOrder.id}/settle`, { version: selectedOrder.version, charge_to_room: roomCharge,
      payment: { company_id: companyId, items: [], payment_method: method, amount_received: received ? received : null,
        discount_amount: discount, sale_discount_amount: discount, discount_authorization_token: token || null } });
    setSelectedOrder(data.order); setNotice(data.already_settled ? "Bill was already settled. No new payment was created." : "Payment recorded. Bill closed.");
    if (onSaleCompleted && !data.already_settled) { try { await onSaleCompleted(data.sale_id); } catch { setNotice("Sale saved. Receipt printing needs review."); } }
  }
  async function transferSelected() {
    if (!selectedOrder) return;
    const { data } = await api.post<Order & { print_jobs?: PrintJob[] }>(`/operations/orders/${selectedOrder.id}/transfer`, { version: selectedOrder.version, table_id: table || null, waiter_id: waiter || null });
    setSelectedOrder(data);
    if (deliver) for (const job of data.print_jobs || []) {
      try { await deliver(job); } catch { setNotice("Table updated in KDS. Printer delivery needs review."); }
    }
  }
  return <section className="business-operations"><header><div><span className="business-eyebrow">{profile?.name || "ApexRetail"}</span><h2><FeatureIcon/>{titles[view]}</h2></div><div className="business-actions">{view !== "home" && <button onClick={() => navigate("home")}>← Back</button>}<button disabled={disabled} onClick={() => void run(load)}>Refresh</button></div></header>
    {!online && <p className="business-warning" role="status">Operations are online-only. Existing offline sales remain on this device.</p>}{error && <p className="business-error" role="alert">{error}</p>}{notice && <p className="business-success" role="status">{notice}</p>}
    {view === "home" && <><div className="business-feature-grid">{features.filter(f => allowed(f.permission) || (f.view === "orders" && allowed("orders_settle")) || (f.view === "tables" && allowed("restaurant_manage"))).filter(f => !f.feature || profile?.features.includes(f.feature)).map(f => <button key={f.view} onClick={() => navigate(f.view)}><FeatureIcon/><strong>{titles[f.view]}</strong><span>Open →</span></button>)}</div><p className="business-hint">Retail checkout, stock, receipts and existing reports remain available in the main menu.</p></>}
    {view === "batches" && <p className="business-warning">Batch reports cover assigned lots. Stock without batch data is not expiry-verified.</p>}
    {view === "profile" && allowed("business_settings_manage") && <form className="business-form" onSubmit={e => { e.preventDefault(); void run(async () => { const { data } = await api.put<Profile>("/operations/profile", { profile: profileChoice, tip_product_id: tip || null, service_product_id: service || null }); setProfile(data); setNotice("Business profile saved"); }); }}><label>Business type<select value={profileChoice} onChange={e => setProfileChoice(e.target.value)}>{Object.entries(profileLabels).map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></label>{selector("Tip product", tip, setTip, list("products").filter(p => p.product_type === "service" || p.product_type === "non_stock"))}{selector("Service charge product", service, setService, list("products").filter(p => p.product_type === "service" || p.product_type === "non_stock"))}<p className="business-hint">Charges use existing product prices and tax settings. No new financial formula is introduced.</p><button disabled={disabled} className="business-primary">Save profile</button></form>}
    {view === "tables" && <>{selector("Floor", floor, setFloor, [...new Set(tables.map(t => t.floor))].map(name => ({ id: name, name })))}<div className="business-floor">{tables.filter(t => t.active && t.floor === floor).map(t => <button key={t.id} style={{ left: `min(${t.x * 4}%, calc(100% - 95px))`, top: `${t.y * 52 + 16}px` }} onClick={() => { setTable(t.id); setBranch(t.branch_id); navigate("orders"); }}><FeatureIcon/><strong>{t.name}</strong><small>{t.seats} seats</small></button>)}</div>{allowed("restaurant_manage") && <form className="business-form" onSubmit={e => { e.preventDefault(); void run(async () => { await api.post("/operations/tables", { branch_id: branch, name, floor, seats: Number(seats), x: Number(x), y: Number(y) }); setName(""); }); }}>{selector("Branch", branch, setBranch, list("branches"), true)}<label>Table name<input required value={name} onChange={e => setName(e.target.value)} maxLength={60}/></label><label>Floor name<input required value={floor} onChange={e => setFloor(e.target.value)} maxLength={60}/></label><label>Seats<input type="number" min="1" max="100" value={seats} onChange={e => setSeats(e.target.value)}/></label><label>Layout column<input type="number" min="0" max="20" value={x} onChange={e => setX(e.target.value)}/></label><label>Layout row<input type="number" min="0" max="20" value={y} onChange={e => setY(e.target.value)}/></label><button disabled={disabled} className="business-primary">Add table</button></form>}</>}
    {view === "tables" && allowed("restaurant_manage") && <TableLayoutEditor tables={tables} disabled={disabled} save={draft => run(() => api.put(`/operations/tables/${draft.id}`, draft))} />}
    {(view === "orders" || view === "quotations") && <>{!selectedOrder ? <>
      {(allowed("orders_manage") || (view === "quotations" && allowed("quotations_manage"))) && <form className="business-form" onSubmit={e => { e.preventDefault(); void run(createOrder); }}>{selector("Branch", branch, setBranch, list("branches"), true)}{selector("Register", device || deviceId, setDevice, list("devices").filter(d => d.branch_id === branch), true)}{view !== "quotations" && selector("Table", table, setTable, tables.filter(t => t.branch_id === branch && t.active))}{(allowed("restaurant_manage") || profile?.administrator) && selector("Waiter", waiter, setWaiter, list("staff").filter(s => s.branch_id === branch))}{selector("Customer", customer, setCustomer, list("customers"))}{allowed("hospitality_manage") && selector("Guest room", guest, setGuest, rooms.flatMap(r => r.guests.map(g => ({ id: g.id, name: `${r.name} · ${list("customers").find(c => c.id === g.customer_id)?.name || "Guest"}` }))))}<button disabled={disabled} className="business-primary">{view === "quotations" ? "New quotation" : "Open order"}</button></form>}
      <div className="business-records">{orders.filter(o => view === "quotations" ? o.kind === "quotation" : o.kind !== "quotation").map(order => <button key={order.id} onClick={() => selectOrder(order)}><span className="business-badge">{order.status}</span><strong>{order.number}</strong><span>{order.table_name} · {order.waiter_name}</span><small>Estimated subtotal {order.estimated_subtotal}</small></button>)}{!orders.length && <p>No orders yet</p>}</div></> : <>
        <div className="business-bill-heading"><div><h3>{selectedOrder.number}</h3><p>{selectedOrder.table_name} · {selectedOrder.waiter_name}</p></div><span className="business-badge">{selectedOrder.status}</span><button onClick={() => setSelectedOrder(null)}>← Orders</button></div>
        <div className="business-lines">{selectedOrder.items.map(item => <article key={item.id}><label className="business-check"><input type="checkbox" checked={Boolean(selected[item.id])} onChange={e => setSelected({ ...selected, [item.id]: e.target.checked })}/><strong>{item.name}</strong></label><span>{item.quantity} {item.unit} · {item.price}</span><small>{item.notes} · Sent: {item.sent_quantity}</small>{selectedOrder.status === "open" && (allowed("orders_manage") || allowed("quotations_manage")) && <button disabled={disabled} onClick={() => void run(async () => { const { data } = await api.put<Order>(`/operations/orders/${selectedOrder.id}/items/${item.id}`, { version: selectedOrder.version, quantity: "0", notes: item.notes }); setSelectedOrder(data); })}>Remove</button>}</article>)}</div>
        <p className="business-estimate">Estimated subtotal <strong>{selectedOrder.estimated_subtotal}</strong><small>Final pricing, discounts and tax are validated at payment.</small></p>
        {selectedOrder.kind === "quotation" && allowed("quotations_manage") && <button onClick={() => {
          const preview = window.open("", "_blank", "width=800,height=700");
          if (!preview) { setError("Allow pop-ups to view or save this quotation as PDF."); return; }
          preview.opener = null; preview.document.write(quotationHtml(selectedOrder)); preview.document.close(); preview.focus(); preview.print();
        }}>Print / save quotation PDF</button>}
        {selectedOrder.status === "open" && <>
          {(allowed("orders_manage") || allowed("quotations_manage")) && <form className="business-form" onSubmit={e => { e.preventDefault(); void run(async () => { const { data } = await api.post<Order>(`/operations/orders/${selectedOrder.id}/items`, { version: selectedOrder.version, product_id: product, variant_id: variant || null, quantity, notes }); setSelectedOrder(data); setNotes(""); }); }}>{selector("Product", product, value => { setProduct(value); setVariant(""); }, list("products"), true)}{selector("Variant", variant, setVariant, list("variants").filter(v => v.product_id === product))}<label>Quantity<input required type="number" step="0.001" min="0.001" value={quantity} onChange={e => setQuantity(e.target.value)}/></label><label>Preparation notes<input value={notes} maxLength={500} onChange={e => setNotes(e.target.value)}/></label><button disabled={disabled} className="business-primary">Add item</button></form>}
          {selectedOrder.kind !== "quotation" && allowed("orders_send") && <button className="business-primary" disabled={disabled} onClick={() => void run(async () => { const { data } = await api.post<{ order: Order; jobs: PrintJob[] }>(`/operations/orders/${selectedOrder.id}/send`, { version: selectedOrder.version }); setSelectedOrder(data.order); setNotice(`${data.jobs.length} kitchen/bar tickets queued`); if (deliver) { for (const job of data.jobs) { try { await deliver(job); } catch { setNotice("Order sent to KDS. Printer delivery needs review in the print queue."); } } } })}>Send to kitchen / bar</button>}
          {(profile?.tip_product_id || profile?.service_product_id) && <div className="business-actions">{[["Add tip", profile.tip_product_id], ["Add service charge", profile.service_product_id]].filter(([, id]) => id).map(([label, id]) => <button key={id} disabled={disabled} onClick={() => { setProduct(id!); setVariant(""); setQuantity("1"); }}>{label}</button>)}</div>}
          {allowed("restaurant_manage") && <details className="business-details"><summary>Manage bill</summary><div className="business-form">
            {selector("Transfer to table", table, setTable, tables.filter(t => t.branch_id === selectedOrder.branch_id))}{selector("Assign waiter", waiter, setWaiter, list("staff").filter(s => s.branch_id === selectedOrder.branch_id))}
            <button disabled={disabled} onClick={() => void run(transferSelected)}>Transfer / assign</button>
            <button disabled={disabled || !Object.values(selected).some(Boolean)} onClick={() => void run(async () => { const { data } = await api.post<{ source: Order }>(`/operations/orders/${selectedOrder.id}/split`, { version: selectedOrder.version, item_ids: Object.keys(selected).filter(id => selected[id]), request_id: crypto.randomUUID() }); setSelectedOrder(data.source); setSelected({}); })}>Split selected lines</button>
            {selector("Merge another bill", mergeTarget, setMergeTarget, orders.filter(o => o.id !== selectedOrder.id && o.status === "open").map(o => ({ id: o.id, name: o.number })))}
            <button disabled={disabled || !mergeTarget} onClick={() => void run(async () => { const source = orders.find(o => o.id === mergeTarget)!; const { data } = await api.post<Order>(`/operations/orders/${selectedOrder.id}/merge`, { version: selectedOrder.version, source_id: source.id, source_version: source.version }); setSelectedOrder(data); })}>Merge bill</button>
            <button disabled={disabled} className="business-danger" onClick={() => { if (confirm("Cancel this unpaid order? Sent items must already have cancellation tickets.")) void run(async () => { const { data } = await api.post<Order>(`/operations/orders/${selectedOrder.id}/cancel`, { version: selectedOrder.version }); setSelectedOrder(data); }); }}>Cancel unpaid order</button>
          </div></details>}
          {allowed("orders_settle") && <form className="business-form" onSubmit={e => { e.preventDefault(); if (!confirm("Record payment and close this bill? Stock will be deducted once.")) return;
            if (Number(discount) > 0 && !allowed("sales_discount") && approve) approve({ action: "large_discount", reason: "Approve bill discount", context: { client_sale_id: selectedOrder.id, discount_amount: discount } }, token => void run(() => settle(token)));
            else void run(() => settle());
          }}><h3>Payment</h3><label>Payment method<select value={method} onChange={e => setMethod(e.target.value)}>{["cash", "card", "mobile", "credit"].map(p => <option key={p}>{p}</option>)}</select></label><label>Amount received<input type="number" step="0.01" min="0" value={received} onChange={e => setReceived(e.target.value)}/></label><label>Discount<input type="number" step="0.01" min="0" value={discount} onChange={e => setDiscount(e.target.value)}/></label>{selectedOrder.guest_id && allowed("hospitality_manage") && <label className="business-check"><input type="checkbox" checked={roomCharge} onChange={e => { setRoomCharge(e.target.checked); if (e.target.checked) setMethod("credit"); }}/> Charge to guest's credit account</label>}<button disabled={disabled} className="business-primary">Confirm payment</button></form>}
        </>}
        {selectedOrder.sale_id && onPrintReceipt && allowed("sales_receipt_reprint") && <button disabled={disabled} onClick={() => void run(() => onPrintReceipt(selectedOrder.sale_id!))}>Print customer receipt</button>}
      </> }</>}
    {(view === "kitchen" || view === "bar") && <div className="business-kds">{tickets.filter(t => t.purpose === (view === "bar" ? "bar" : "kitchen") && !["served", "acknowledged"].includes(t.status)).map(ticket => <article key={ticket.id}>
      <span className={`business-badge ${ticket.status === "needs_review" ? "soon" : ""}`}>{ticket.status}</span><h3>{ticket.payload.order_number}</h3><p>{ticket.current_table || ticket.payload.table} · {ticket.current_waiter || ticket.payload.waiter}</p><small>{new Date(ticket.payload.created_at).toLocaleString()} · {ticket.station_name}</small><strong className="business-ticket-title">{ticket.payload.title}</strong>
      {ticket.status === "needs_review" && <p className="business-warning">Order changed. Review the latest amendment; do not prepare from these old quantities.</p>}
      {ticket.payload.items.map((item, index) => <p key={index}><b>{item.quantity} × {item.name}</b><br/><small>{item.notes}</small></p>)}<small>Printer: {ticket.print_status}</small>
      {allowed(view === "bar" ? "bar_update" : "kitchen_update") && <button className="business-primary" disabled={disabled} onClick={() => void run(() => api.put(`/operations/kitchen/${ticket.id}`, { status: kitchenAction(ticket).status }))}>{kitchenAction(ticket).label}</button>}
    </article>)}{!tickets.length && <p>No kitchen tickets</p>}</div>}
    {view === "rooms" && allowed("hospitality_manage") && <><form className="business-form" onSubmit={e => { e.preventDefault(); void run(() => api.post("/operations/rooms", { branch_id: branch, name })); }}>{selector("Branch", branch, setBranch, list("branches"), true)}<label>Room number / name<input required value={name} maxLength={60} onChange={e => setName(e.target.value)}/></label><button disabled={disabled} className="business-primary">Add room</button></form><div className="business-records">{rooms.map(room => <article key={room.id}><FeatureIcon/><h3>{room.name}</h3>{room.guests.map(g => <div key={g.id}><p>{list("customers").find(c => c.id === g.customer_id)?.name || "Guest account"}</p><button disabled={disabled} onClick={() => void run(async () => setFolio((await api.get(`/operations/guests/${g.id}/folio`)).data))}>View guest bill</button></div>)}{!room.guests.length && <><p>Available account</p>{selector("Guest / customer", customer, setCustomer, list("customers"))}<button disabled={disabled || !customer} onClick={() => void run(() => api.post("/operations/guests", { room_id: room.id, customer_id: customer }))}>Open guest account</button></>}</article>)}</div>{folio && <section className="business-details"><h3>{folio.guest_name}</h3>{folio.charges.map(charge => <p key={charge.receipt_number}>{charge.receipt_number} · {charge.currency} {charge.amount} · Outstanding {charge.outstanding}</p>)}{!folio.charges.length && <p>No posted charges</p>}<small>Settle receivables in existing Credit Settlement.</small></section>}</>}
    {view === "batches" && <>{allowed("batches_manage") && <form className="business-form" onSubmit={e => { e.preventDefault(); void run(() => api.post("/operations/batches", { branch_id: branch, product_id: product, code: batchCode, expires_on: expiry, quantity })); }}>{selector("Branch", branch, setBranch, list("branches"), true)}{selector("Product", product, setProduct, list("products"), true)}<label>Batch code<input required maxLength={80} value={batchCode} onChange={e => setBatchCode(e.target.value)}/></label><label>Expiry date<input required type="date" value={expiry} onChange={e => setExpiry(e.target.value)}/></label><label>Assign existing stock<input required type="number" step="0.001" min="0.001" value={quantity} onChange={e => setQuantity(e.target.value)}/></label><button disabled={disabled} className="business-primary">Assign batch stock</button></form>}<div className="business-records">{batches.map(batch => <article key={batch.id}><span className={`business-badge ${batch.expired ? "expired" : batch.expires_soon ? "soon" : ""}`}>{batch.expired ? "Expired" : batch.expires_soon ? "Expiring soon" : "Available"}</span><h3>{batch.product_name}</h3><p>{batch.code} · {batch.quantity} units</p><small>Expiry {batch.expires_on}</small></article>)}{!batches.length && <p>No batch stock assigned</p>}</div></>}
    {view === "rooms" && allowed("hospitality_manage") && <details className="business-details"><summary>Room & guest account actions</summary><div className="business-records">{rooms.map(room => <article key={room.id}><strong>{room.name}</strong>{room.guests.map(g => <button key={g.id} disabled={disabled} onClick={() => { if (confirm("Close this guest account? Open bills and outstanding credit must be settled first.")) void run(() => api.post(`/operations/guests/${g.id}/close`)); }}>Close guest account</button>)}<button disabled={disabled} onClick={() => void run(() => api.put(`/operations/rooms/${room.id}`, { branch_id: room.branch_id, name: room.name, active: !room.active }))}>{room.active ? "Suspend room" : "Enable room"}</button></article>)}</div></details>}
    {view === "batches" && allowed("batches_view") && <button onClick={() => {
      const url = URL.createObjectURL(new Blob([batchCsv(batches)], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = "batch-stock-report.csv"; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }}>Export batch stock CSV</button>}
    {view === "reports" && <><form className="business-form" onSubmit={e => { e.preventDefault(); void run(async () => setReport((await api.get(`/operations/reports?start=${start}&end=${end}`)).data)); }}><label>From<input required type="date" value={start} onChange={e => setStart(e.target.value)}/></label><label>To<input required type="date" value={end} onChange={e => setEnd(e.target.value)}/></label><button disabled={disabled} className="business-primary">View report</button></form><div className="business-records">{report?.currency_totals.map(r => <article key={r.currency}><h3>{r.currency}</h3><strong>Sales less refunds {r.sales}</strong><p>Discounts {r.discounts}</p><small>{r.orders} paid orders · Tax included</small></article>)}</div></>}
  </section>;
}
