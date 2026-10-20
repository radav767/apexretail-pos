import { useState } from "react";
import { OfflineOrderOutbox, type OrderCommand } from "./offlineOrders";

type Option = { id: string; name: string; product_id?: string };
export default function OfflineDraftPanel({ company, employee, device, branch, products, variants, online, send }: {
  company: string; employee: string; device: string; branch: string; products: Option[]; variants: Option[]; online: boolean;
  send: (endpoint: string, payload: unknown) => Promise<unknown>;
}) {
  const [product, setProduct] = useState(""); const [variant, setVariant] = useState(""); const [quantity, setQuantity] = useState("1");
  const [lines, setLines] = useState<{ product_id: string; variant_id: string | null; quantity: string; version: number }[]>([]);
  const [entries, setEntries] = useState<OrderCommand[]>([]); const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);
  const outbox = () => new OfflineOrderOutbox(localStorage, { company, employee, device });
  const reload = () => { try { setEntries(outbox().list()); } catch (e) { setMessage(String(e)); } };
  return <details className="business-manager" onToggle={reload}><summary>Offline order drafts</summary>
    <p className="business-warning">Unpaid drafts only. Reconnect to send kitchen tickets or take payment. No stock is reserved.</p>
    <form className="business-form" onSubmit={event => { event.preventDefault(); setLines([...lines, { version: 1, product_id: product, variant_id: variant || null, quantity }]); }}>
      <label>Product<select required value={product} onChange={e => { setProduct(e.target.value); setVariant(""); }}><option value="">Select product</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      {variants.some(v => v.product_id === product) && <label>Variant<select required value={variant} onChange={e => setVariant(e.target.value)}><option value="">Select variant</option>{variants.filter(v => v.product_id === product).map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>}
      <label>Quantity<input required type="number" min="0.001" step="0.001" value={quantity} onChange={e => setQuantity(e.target.value)}/></label><button disabled={!product || busy}>Add draft item</button>
    </form>
    {lines.map((line, i) => <p key={i}>{products.find(p => p.id === line.product_id)?.name} × {line.quantity}</p>)}
    <button disabled={!lines.length || !branch || busy} onClick={() => {
      try { const request = crypto.randomUUID(); outbox().enqueue({ id: request, endpoint: "/operations/offline/drafts", payload: {
        request_id: request, employee_id: employee, captured_at: new Date().toISOString(),
        order: { request_id: crypto.randomUUID(), branch_id: branch, device_id: device, kind: "restaurant", waiter_id: employee }, items: lines,
      } }); setLines([]); setMessage("Draft saved on this device. Not sent to the kitchen."); reload(); } catch (e) { setMessage(String(e)); }
    }}>Save unpaid draft</button>
    <button disabled={!online || busy} onClick={() => { setBusy(true); void outbox().synchronize(send).then(reload).catch(e => setMessage(String(e))).finally(() => setBusy(false)); }}>Review & synchronize drafts</button>
    {message && <p role="status">{message}</p>}{entries.map(entry => <article key={entry.id}><strong>{entry.status}</strong>{entry.error && <p role="alert">{entry.error}</p>}<details><summary>Original draft</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(entry.payload, null, 2)}</pre></details></article>)}
  </details>;
}
