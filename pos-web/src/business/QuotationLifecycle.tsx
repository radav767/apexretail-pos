import QuotationPricing,{type PricingPlan} from "./QuotationPricing";
import {createPrintScope} from "../printing/context";
import QuotationRevision from "./QuotationRevision";
import { useEffect, useRef, useState } from "react";
type Command = { request_id: string; version: number; action: "sent" | "accepted" | "rejected"; valid_until?: string };
type Quote = { id: string; kind: string; version: number; quotation_status?: string; quotation_valid_until?: string | null; quotation_terms?: ({ total: string; tax: string; currency: string } & Partial<PricingPlan>) | null; quotation_pricing?:PricingPlan|null;items:{id:string;product_id:string;name:string;quantity:string;unit:string}[]; quotation_command_ack?: string; parent_id?: string | null };
export default function QuotationLifecycle<T extends Quote>({ order, companyId, actorKey, client, onChanged, disabled, pricingEnabled, products, currencies }: {
  order: T; companyId: string; actorKey: string; pricingEnabled?:boolean;products:{id:string;unit?:string;purchase_unit?:string|null}[];currencies:{id:string;name:string}[]; client: { get:<R>(path:string)=>Promise<{data:R}>; post: <R>(path: string, data: unknown) => Promise<{ data: R }> }; onChanged: (value: T) => void; disabled: boolean;
}) {
  const key = `apexretail_quotation_action_v1:${companyId}:${actorKey}:${order.id}`;
  const [deadline, setDeadline] = useState(""), [pending, setPending] = useState<Command | null>(null), [message, setMessage] = useState(""), [busy, setBusy] = useState(false), [blocked, setBlocked] = useState(false);
  const alive = useRef(true), lock = useRef(false);
  useEffect(() => {
    alive.current = true;
    try { const value = JSON.parse(sessionStorage.getItem(key) || "null"); if (value && (!Number.isInteger(value.version) || value.version < 1 || typeof value.request_id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.request_id) || Object.keys(value).some(key => !["request_id","version","action","valid_until"].includes(key)) || !["sent", "accepted", "rejected"].includes(value.action))) throw new Error("Invalid action"); setPending(value); }
    catch { setBlocked(true); setMessage("Pending quotation action needs review. Nothing was removed."); }
    return () => { alive.current = false; };
  }, [key]);
  async function apply(action?: Command["action"]) {
    if (lock.current || disabled || blocked) return; lock.current = true; setBusy(true); setMessage(""); const scope = createPrintScope();
    try {
      const command = pending || { request_id: crypto.randomUUID(), version: order.version, action: action!, ...(action === "sent" ? { valid_until: new Date(deadline).toISOString() } : {}) };
      sessionStorage.setItem(key, JSON.stringify(command)); setPending(command);
      const { data } = await client.post<T>(`/operations/orders/${order.id}/quotation-transition`, command);
      if (!alive.current || !scope.isCurrent()) return;
      if (data.id !== order.id || data.kind !== "quotation" || data.quotation_command_ack !== command.request_id || data.version <= command.version) throw new Error("No authoritative quotation acknowledgement. Original request retained.");
      sessionStorage.removeItem(key); setPending(null); onChanged(data);
    } catch { if (alive.current && scope.isCurrent()) setMessage("Quotation action not confirmed. Retry the original request when connected; changed or rejected requests require review."); }
    finally { if (alive.current) setBusy(false); lock.current = false; }
  }
  const [revisionPending,setRevisionPending]=useState(false),[pricingPending,setPricingPending]=useState(false);
  const unavailable = disabled || busy || blocked || revisionPending || pricingPending;
  return <section className="business-details"><h3>Quotation: {order.quotation_status || "legacy review"}</h3>
    {order.quotation_pricing&&<p>Saved pricing: {order.quotation_pricing.total} {order.quotation_pricing.currency}; discount {order.quotation_pricing.discount}; tax {order.quotation_pricing.tax}; {order.quotation_pricing.display_total} {order.quotation_pricing.display_currency}. {order.quotation_status==='draft'&&order.quotation_pricing.bound_version!==order.version?'Draft changes require pricing to be saved again.':''}</p>}
    <QuotationPricing enabled={!!pricingEnabled} order={order} companyId={companyId} actorKey={actorKey} client={client} products={products} currencies={currencies} disabled={disabled||busy||blocked||!!pending||revisionPending} onChanged={onChanged} onPending={setPricingPending}/>
    {order.quotation_pricing&&<div aria-label="Saved quotation positions">{order.quotation_pricing.items.map(row=><p key={row.id}>{order.items.find(i=>i.id===row.id)?.name}: {row.entered_quantity} {row.entered_unit} / {row.base_quantity} {row.base_unit}; net {row.net}, discount {row.discount}, tax {row.tax}</p>)}</div>}
    {order.quotation_valid_until && <p>Valid until {new Date(order.quotation_valid_until).toLocaleString()}</p>}
    {order.quotation_terms && <p>Frozen total {order.quotation_terms.total} {order.quotation_terms.currency} · Tax {order.quotation_terms.tax}</p>}
    <p>Marking sent records your workflow choice. It does not send a message or reserve stock.</p>
    {message && <p role="status">{message}</p>}
    {pending ? <button type="button" disabled={unavailable} onClick={() => void apply()}>Retry original quotation action</button> : order.quotation_status === "draft" ? <><label>Valid until<input type="datetime-local" value={deadline} disabled={unavailable} onChange={e => setDeadline(e.target.value)}/></label><button type="button" disabled={unavailable || !deadline || !!order.quotation_pricing&&order.quotation_pricing.bound_version!==order.version} onClick={() => void apply("sent")}>Mark sent and freeze terms</button></> : order.quotation_status === "sent" ? <><button type="button" disabled={unavailable} onClick={() => void apply("accepted")}>Mark accepted</button><button type="button" disabled={unavailable} onClick={() => void apply("rejected")}>Mark rejected</button></> : null}
    {order.quotation_terms&&!["superseded","converted","legacy_converted"].includes(order.quotation_status||"")&&<QuotationRevision order={order} companyId={companyId} actorKey={actorKey} client={client} onChanged={onChanged} onPending={setRevisionPending} disabled={disabled||busy||blocked||!!pending||pricingPending}/>}
  </section>;
}
