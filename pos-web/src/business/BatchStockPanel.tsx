import { useRef, useState } from "react";
type Option = { id: string; name: string; product_id?: string };
type Command = { payload: Record<string, unknown>; acknowledged: boolean };
export default function BatchStockPanel({ identity, branch, products, variants = [], receive, adjust, online, send, changed }: {
  identity: string; branch: string; products: Option[]; variants?: Option[]; receive: boolean; adjust: boolean; online: boolean;
  send: (payload: unknown) => Promise<unknown>; changed: () => Promise<unknown>;
}) {
  const key = `apexretail_batch_command_v1:${identity}`;
  const [operation, setOperation] = useState(receive ? "receive" : "dispose"); const [product, setProduct] = useState("");
  const [variant, setVariant] = useState("");
  const [code, setCode] = useState(""); const [expiry, setExpiry] = useState(""); const [quantity, setQuantity] = useState("1");
  const [unit, setUnit] = useState(""); const [reason, setReason] = useState(""); const [message, setMessage] = useState("");
  const [command, setCommand] = useState<Command | null>(() => {
    try { return JSON.parse(localStorage.getItem(key) || "null"); }
    catch { return { payload: {}, acknowledged: false }; } // Fail closed; never erase corrupt recovery data.
  });
  const [busy, setBusy] = useState(false);
  const recording = useRef(false);
  async function execute() {
    if (recording.current || !online) return;
    recording.current = true; setBusy(true); setMessage("");
    try {
      const persisted = JSON.parse(localStorage.getItem(key) || "null") as Command | null;
      const saved = persisted || command || { payload: { request_id: crypto.randomUUID(), branch_id: branch, product_id: product,
        ...(variant ? { variant_id: variant } : {}),
        operation, code, expires_on: expiry, quantity, reason, received_unit: operation === "receive" ? unit || null : null }, acknowledged: false };
      if (!saved.payload.request_id) throw new Error("Stored batch request needs review. No data was cleared.");
      localStorage.setItem(key, JSON.stringify(saved)); setCommand(saved);
      const response = await send(saved.payload) as { movement_id?: string; batch_id?: string } | null;
      if (!response?.movement_id || !response?.batch_id) throw new Error("No stock acknowledgement");
      const acknowledged = { ...saved, acknowledged: true };
      localStorage.setItem(key, JSON.stringify(acknowledged)); setCommand(acknowledged);
      setMessage("Stock operation confirmed."); await changed();
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      setMessage(detail || "Operation not confirmed. The original request is retained; retry without changing it.");
    } finally { recording.current = false; setBusy(false); }
  }
  return <details className="business-details"><summary>Receive / return / dispose batch stock</summary>
    {command ? <><p>{command.acknowledged ? "Confirmed" : "Pending confirmation — retry the original request"}</p><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(command.payload, null, 2)}</pre>
      {command.acknowledged ? <button onClick={() => { localStorage.setItem(`${key}:ack:${String(command.payload.request_id)}`, JSON.stringify(command)); localStorage.setItem(key, "null"); setCommand(null); }}>New stock operation</button> : <button disabled={!online || busy} onClick={() => void execute()}>Retry original stock request</button>}</> :
      <form className="business-form" onSubmit={e => { e.preventDefault(); if (confirm("Record this batch stock movement? This changes inventory, not customer payments.")) void execute(); }}>
        <label>Operation<select value={operation} onChange={e => setOperation(e.target.value)}>{receive && <option value="receive">Receive stock</option>}{adjust && <><option value="supplier_return">Return to supplier</option><option value="dispose">Dispose stock</option></>}</select></label>
        <label>Product<select required value={product} onChange={e => { setProduct(e.target.value); setVariant(""); }}><option value="">Select product</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        {variants.some(v => v.product_id === product) && <label>Variant<select required value={variant} onChange={e => setVariant(e.target.value)}><option value="">Select variant</option>{variants.filter(v => v.product_id === product).map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>}
        <label>Batch code<input required maxLength={80} value={code} onChange={e => setCode(e.target.value)}/></label>
        <label>Expiry date<input required type="date" value={expiry} onChange={e => setExpiry(e.target.value)}/></label>
        <label>Quantity<input required type="number" min="0.001" step="0.001" value={quantity} onChange={e => setQuantity(e.target.value)}/></label>
        {operation === "receive" && <label>Purchase unit (optional)<input maxLength={20} value={unit} onChange={e => setUnit(e.target.value)}/></label>}
        <label>Reason<input required minLength={3} maxLength={160} value={reason} onChange={e => setReason(e.target.value)}/></label>
        <button disabled={busy || !online || !branch || (!receive && !adjust)}>Confirm stock operation</button>
      </form>}{message && <p role="status">{message}</p>}
  </details>;
}
