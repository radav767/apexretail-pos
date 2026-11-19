import { useEffect, useRef, useState } from "react";
import { CheckoutCustomerCommands } from "../checkoutCustomer";
import type { BasicCustomer } from "../checkoutCustomer";
import { createBootstrapScope } from "../api/authLifecycle";
export type CheckoutCustomer = { id: string; company_id: string; customer_code: string; name: string; active: boolean; credit_enabled: boolean; unlimited_credit: boolean; credit_limit: string | null; credit_terms_days: number; price_level_name?: string | null; outstanding_balance: string; available_credit: string | null };
export default function InlineCustomerCreate({ companyId, actorKey, client, onCreated }: { companyId: string; actorKey: string; client: { post: (path: string, payload: unknown) => Promise<{ data: CheckoutCustomer }> }; onCreated: (customer: CheckoutCustomer) => void }) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [name, setName] = useState(""), [phone, setPhone] = useState(""), [email, setEmail] = useState(""), [address, setAddress] = useState("");
  const [pending, setPending] = useState<BasicCustomer | null>(null); const lock = useRef(false), alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  function show() { try { const old = new CheckoutCustomerCommands(companyId, actorKey, sessionStorage).read(); setPending(old); if (old) { setName(old.name); setPhone(old.phone || ""); setEmail(old.email || ""); setAddress(old.address || ""); } setOpen(true); setMessage(""); } catch (error) { setMessage((error as Error).message); } }
  async function save() {
    if (lock.current) return; lock.current = true; setBusy(true); setMessage(""); const scope = createBootstrapScope();
    try {
      const store = new CheckoutCustomerCommands(companyId, actorKey, sessionStorage), payload = store.prepare({ name, phone, email, address }); setPending(payload);
      const { data } = await client.post("/customers/checkout", payload);
      if (!alive.current || !scope.isCurrent()) return;
      store.confirm(payload, data); setPending(null); setOpen(false); setName(""); setPhone(""); setEmail(""); setAddress("");
      if (data.active) onCreated(data); else setMessage("Customer created but is no longer active. Review the account before use.");
    } catch (error) { if (alive.current && scope.isCurrent()) setMessage((error as { response?: { data?: { detail?: unknown } }; message?: string }).response?.data?.detail as string || (error as Error).message || "Customer not confirmed. Retry the original request when connected."); }
    finally { if (alive.current) setBusy(false); lock.current = false; }
  }
  return <section className="inline-customer"><button type="button" onClick={show}>New customer</button>{message && <p role="status">{typeof message === "string" ? message : "Customer not confirmed. Original request retained."}</p>}{open && <div role="group" aria-label="Create checkout customer">
    <p>Create a basic customer without leaving checkout. Credit starts disabled.</p>
    <label>Name<input autoFocus required maxLength={160} value={name} disabled={busy || !!pending} onChange={e => setName(e.target.value)}/></label>
    <label>Phone<input maxLength={60} value={phone} disabled={busy || !!pending} onChange={e => setPhone(e.target.value)}/></label>
    <label>Email<input type="email" maxLength={160} value={email} disabled={busy || !!pending} onChange={e => setEmail(e.target.value)}/></label>
    <label>Address<textarea maxLength={1000} value={address} disabled={busy || !!pending} onChange={e => setAddress(e.target.value)}/></label>
    {pending && <p>Unconfirmed request retained. Retry uses the original contact details.</p>}
    <button type="button" disabled={busy || !name.trim()} onClick={() => void save()}>{busy ? "Saving…" : pending ? "Retry customer creation" : "Save customer"}</button><button type="button" disabled={busy} onClick={() => setOpen(false)}>Back to checkout</button>
  </div>}</section>;
}
