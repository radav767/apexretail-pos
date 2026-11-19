// Online recovery intent only. Credentials never enter this store. Web Locks
// serialize tabs; generations stop old forms creating a new UUID after recovery.
export type RefundPayload = {
  company_id: string; original_sale_id: string; branch_id?: string;
  employee_id?: string; device_id?: string; reason: string; refund_method?: string;
  items: Array<{sale_item_id: string; quantity: string}>;
};
export type PendingRefund = { request_id: string; actor: string; payload: RefundPayload };
type Frame = { generation: number; pending?: PendingRefund; last_confirmed?: {request_id: string; sale_id: string} };
type Store = Pick<Storage, "getItem" | "setItem">;
type Lock = <T>(name: string, task: () => T | Promise<T>) => Promise<T>;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const browserLock: Lock = async (name, task) => {
  if (!globalThis.navigator?.locks) throw new Error("This browser cannot safely coordinate refund retries. Use a supported browser and retain the original request for review.");
  return navigator.locks.request(name, task);
};
export function refundActorStorageId(storage: Pick<Storage, "getItem"> = localStorage): string {
  const employee = storage.getItem("employee_id");
  if (employee) return `employee:${employee}`;
  // Unverified decoding is solely a local namespace, never authorization.
  try {
    const raw = (storage.getItem("token") || "").split(".")[1];
    const sub = JSON.parse(atob(raw.replace(/-/g,"+").replace(/_/g,"/"))).sub;
    if (typeof sub === "string" && sub) return `user:${sub}`;
  } catch { /* cannot establish the local actor namespace */ }
  throw new Error("Reconnect and sign in before creating a refund.");
}
export class RefundCommands {
  private storage: Store;
  private key: string;
  private actor: string;
  private company: string;
  private originalSale: string;
  private lock: Lock;
  constructor(company: string, actor: string, originalSale: string, storage: Store = localStorage, lock: Lock = browserLock) {
    if (!company || !actor || !originalSale) throw new Error("Original refund account and sale identity are required.");
    this.storage = storage; this.actor = actor; this.company = company; this.originalSale = originalSale; this.lock = lock;
    // Shared across cashiers/registers for this original sale: a context change
    // cannot silently create another identity for an unconfirmed refund.
    this.key = "apexpos_refund_command_v1:" + [company,originalSale].map(encodeURIComponent).join(":");
  }
  load(): Frame {
    const raw = this.storage.getItem(this.key);
    if (!raw) return {generation:0};
    try {
      const frame = JSON.parse(raw) as Frame;
      if (!Number.isSafeInteger(frame.generation) || frame.generation < 0 ||
          Object.keys(frame).some(key=>!["generation","pending","last_confirmed"].includes(key))) throw new Error();
      const pending = frame.pending;
      if (pending && (typeof pending.request_id !== "string" || !UUID_PATTERN.test(pending.request_id) || typeof pending.actor !== "string" ||
          pending.payload?.company_id !== this.company || pending.payload.original_sale_id !== this.originalSale ||
          typeof pending.payload.reason !== "string" || !Array.isArray(pending.payload.items) ||
          Object.keys(pending).some(key=>!["request_id","actor","payload"].includes(key)) ||
          Object.keys(pending.payload).some(key=>!["company_id","original_sale_id","branch_id","employee_id","device_id","reason","refund_method","items"].includes(key)) ||
          pending.payload.items.some(item=>typeof item.sale_item_id!=="string" || typeof item.quantity!=="string" ||
            Object.keys(item).some(key=>!["sale_item_id","quantity"].includes(key))))) throw new Error();
      if (frame.last_confirmed && (typeof frame.last_confirmed.request_id !== "string" || !UUID_PATTERN.test(frame.last_confirmed.request_id) || typeof frame.last_confirmed.sale_id !== "string" ||
          Object.keys(frame.last_confirmed).some(key=>!["request_id","sale_id"].includes(key)))) throw new Error();
      return frame;
    } catch { throw new Error("Saved refund needs review. The original request has not been cleared."); }
  }
  async prepare(payload: RefundPayload, expectedGeneration: number): Promise<PendingRefund> {
    const safe: RefundPayload = {company_id:payload.company_id,original_sale_id:payload.original_sale_id,
      branch_id:payload.branch_id,employee_id:payload.employee_id,device_id:payload.device_id,
      reason:payload.reason,refund_method:payload.refund_method,
      items:payload.items.map(item=>({sale_item_id:item.sale_item_id,quantity:item.quantity}))};
    const canonical = JSON.parse(JSON.stringify(safe)) as RefundPayload;
    if (canonical.company_id !== this.company || canonical.original_sale_id !== this.originalSale) throw new Error("Refund scope changed. Reload the original sale.");
    return this.lock(this.key, () => {
      const frame = this.load();
      if (frame.pending) {
        if (frame.pending.actor !== this.actor) throw new Error("Another account has an unconfirmed refund for this sale. Check its server confirmation or return to the original account.");
        if (JSON.stringify(frame.pending.payload) !== JSON.stringify(canonical)) throw new Error("A refund is unconfirmed. Retry the unchanged original request or check its server confirmation before changing it.");
        return frame.pending;
      }
      if (frame.generation !== expectedGeneration) throw new Error("The original refund was already confirmed. Reload the sale before starting a separate refund.");
      const pending = {request_id:crypto.randomUUID(),actor:this.actor,payload:canonical};
      this.storage.setItem(this.key,JSON.stringify({...frame,generation:frame.generation+1,pending}));
      return pending;
    });
  }
  async confirm(result: {id?: unknown; company_id?: unknown; client_sale_id?: unknown; original_sale_id?: unknown; status?: unknown}) {
    return this.lock(this.key, () => {
      const frame = this.load();
      if (typeof result.id !== "string" || result.company_id !== this.company || result.original_sale_id !== this.originalSale || result.status !== "refunded") {
        throw new Error("The refund response does not confirm the original request. Keep it for review.");
      }
      const previous = frame.last_confirmed;
      if (previous && previous.request_id === result.client_sale_id && previous.sale_id === result.id) return;
      if (!frame.pending || result.client_sale_id !== frame.pending.request_id) throw new Error("The refund response does not confirm the original request. Keep it for review.");
      this.storage.setItem(this.key,JSON.stringify({generation:frame.generation+1,
        last_confirmed:{request_id:frame.pending.request_id,sale_id:result.id}}));
    });
  }
}
