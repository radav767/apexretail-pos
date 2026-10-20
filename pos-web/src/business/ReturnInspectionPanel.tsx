import { useCallback, useEffect, useRef, useState } from "react";
type Api = { get: (url: string) => Promise<{ data: any }>; post: (url: string, data: unknown) => Promise<{ data: any }> };
type Hold = { id: string; product: string; quantity: string; refund_reference: string };
type Pending = { payload: Record<string, unknown>; acknowledged: boolean; rejectedValidation?: boolean };
export default function ReturnInspectionPanel({ api, identity, allowDispose, online, changed }: {
  api: Api; identity: string; allowDispose: boolean; online: boolean; changed: () => Promise<unknown>;
}) {
  const key = `apexretail_return_inspection_v1:${identity}`;
  const [holds, setHolds] = useState<Hold[]>([]); const [hold, setHold] = useState(""); const [code, setCode] = useState("");
  const [expiry, setExpiry] = useState(""); const [disposition, setDisposition] = useState("restock"); const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const recording = useRef(false);
  const [pending, setPending] = useState<Pending | null>(() => { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return { payload: {}, acknowledged: false }; } });
  const load = useCallback(async () => setHolds((await api.get("/operations/batches/returns")).data), [api]);
  useEffect(() => { if (online) void load().catch(() => setMessage("Return inspection access unavailable")); }, [online, identity, load]);
  async function inspect() {
    if (!online || recording.current) return; recording.current = true; setBusy(true);
    try {
      const command = pending || { payload: { request_id: crypto.randomUUID(), hold_id: hold, code, expires_on: expiry,
        disposition, reason, confirmed: true }, acknowledged: false };
      if (!command.payload.request_id) throw new Error("Stored inspection needs review");
      localStorage.setItem(key, JSON.stringify(command)); setPending(command);
      const { data } = await api.post("/operations/batches/returns/inspect", command.payload);
      if (!data?.id) throw new Error("No inspection acknowledgement");
      const ack = { ...command, acknowledged: true }; localStorage.setItem(key, JSON.stringify(ack)); setPending(ack);
      setMessage("Inspection recorded. The original financial refund is unchanged."); await load(); await changed();
    } catch (error) {
      const response = (error as { response?: { status?: number; data?: { detail?: string | { code?: string; message?: string } } } }).response;
      const detail = response?.data?.detail;
      if (response?.status === 400 || response?.status === 422 || (typeof detail === "object" && detail?.code === "expired_return_requires_disposal")) {
        try { const original = JSON.parse(localStorage.getItem(key) || "null") as Pending | null; if (original) { const rejected = { ...original, rejectedValidation: true }; localStorage.setItem(key, JSON.stringify(rejected)); setPending(rejected); } } catch { /* No records cleared. */ }
      }
      setMessage(typeof detail === "string" ? detail : detail?.message || "Inspection not confirmed. Original request retained; do not repeat stock movements manually.");
    }
    finally { recording.current = false; setBusy(false); }
  }
  return <details className="business-details"><summary>Inspect held customer returns</summary><p>New pharmacy/batch returns cannot be sold until inspected. Financial refunds remain separate.</p>
    {pending ? <><p>{pending.acknowledged ? "Inspection confirmed" : "Pending inspection confirmation"}</p><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(pending.payload, null, 2)}</pre>{pending.acknowledged ? <button onClick={() => { localStorage.setItem(`${key}:ack:${String(pending.payload.request_id)}`, JSON.stringify(pending)); localStorage.setItem(key, "null"); setPending(null); }}>Next return</button> : <><button disabled={busy || !online} onClick={() => void inspect()}>Retry original inspection</button>{pending.rejectedValidation && <button onClick={() => { localStorage.setItem(`${key}:rejected:${String(pending.payload.request_id)}`, JSON.stringify(pending)); localStorage.setItem(key, "null"); setPending(null); }}>Revise rejected inspection (original archived)</button>}</>}</> :
      <form className="business-form" onSubmit={event => { event.preventDefault(); if (confirm("Confirm physical inspection and the selected disposition? Disposal changes stock once; it does not refund money again.")) void inspect(); }}>
        <label>Customer return<select required value={hold} onChange={e => setHold(e.target.value)}><option value="">Select held return</option>{holds.map(row => <option key={row.id} value={row.id}>{row.product} × {row.quantity} · {row.refund_reference}</option>)}</select></label>
        <label>Verified lot code<input required maxLength={80} value={code} onChange={e => setCode(e.target.value)}/></label><label>Verified expiry<input required type="date" value={expiry} onChange={e => setExpiry(e.target.value)}/></label>
        <label>Disposition<select value={disposition} onChange={e => setDisposition(e.target.value)}><option value="restock">Release inspected stock</option>{allowDispose && <option value="dispose">Dispose returned stock</option>}</select></label>
        <label>Inspection reason<input required minLength={3} maxLength={500} value={reason} onChange={e => setReason(e.target.value)}/></label><button disabled={!online || busy || !hold}>Confirm inspection</button>
      </form>}{message && <p role="status">{message}</p>}
  </details>;
}
