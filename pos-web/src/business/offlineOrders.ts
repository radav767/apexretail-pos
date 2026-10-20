/** Separate unpaid-order outbox. Never touches the financial sales queue. */
export type OrderIdentity = { company: string; employee: string; device: string };
export type OrderCommand = { id: string; endpoint: "/operations/offline/drafts" | "/operations/offline/edits"; payload: unknown; status: "pending" | "review" | "acknowledged"; error?: string; result?: unknown };
type StorageLike = Pick<Storage, "getItem" | "setItem" | "key" | "length">;
export class OfflineOrderOutbox {
  private key: string;
  private storage: StorageLike;
  constructor(storage: StorageLike, identity: OrderIdentity) {
    this.storage = storage;
    if (!identity.company || !identity.employee || !identity.device) throw new Error("Original order identity is required");
    this.key = `apexretail_unpaid_order_outbox_v1:${identity.company}:${identity.employee}:${identity.device}`;
  }
  list(): OrderCommand[] {
    const values: OrderCommand[] = [];
    for (let i = 0; i < this.storage.length; i++) {
      const key = this.storage.key(i);
      if (!key?.startsWith(`${this.key}:`)) continue;
      const value = JSON.parse(this.storage.getItem(key) || "null") as OrderCommand | null;
      if (!value || typeof value.id !== "string" || !["pending", "review", "acknowledged"].includes(value.status)
          || !["/operations/offline/drafts", "/operations/offline/edits"].includes(value.endpoint)) {
      throw new Error("Offline order storage needs review; no records were cleared");
      }
      values.push(value);
    }
    return values;
  }
  enqueue(command: Omit<OrderCommand, "status">): void {
    const entries = this.list();
    if (entries.some(v => v.id === command.id)) throw new Error("Order command already exists");
    // Write before reporting success. A quota failure must not pretend to save.
    // One key per immutable command avoids cross-tab read/append/write loss.
    this.storage.setItem(`${this.key}:${command.id}`, JSON.stringify({ ...command, status: "pending" }));
  }
  async synchronize(send: (endpoint: string, payload: unknown) => Promise<unknown>): Promise<void> {
    for (const snapshot of this.list()) {
      if (snapshot.status === "acknowledged") continue;
      try {
        const result = await send(snapshot.endpoint, snapshot.payload);
        this.requireReceipt(result);
        this.update(snapshot.id, { status: "acknowledged", result, error: undefined });
      } catch (error) {
        const status = (error as { response?: { status?: number } }).response?.status;
        const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
        this.update(snapshot.id, { status: status && status < 500 ? "review" : "pending", error: detail || "Sync not confirmed. Original order retained; retry with the same account." });
        break; // Preserve command ordering. Never overwrite versions to force sync.
      }
    }
  }
  async recover(check: (endpoint: string, payload: unknown) => Promise<unknown>): Promise<void> {
    for (const entry of this.list()) {
      if (entry.status === "acknowledged") continue;
      try {
        const result = await check(`${entry.endpoint}/recover`, entry.payload);
        this.requireReceipt(result);
        this.update(entry.id, { status: "acknowledged", result, error: undefined });
      } catch (error) {
        const status = (error as { response?: { status?: number } }).response?.status;
        this.update(entry.id, { status: status === 404 || !status || status >= 500 ? "pending" : "review",
          error: status === 404 ? "Not confirmed on server. Synchronize the unchanged original draft." : "Recovery not confirmed. Original command retained." });
      }
    }
  }
  private update(id: string, values: Partial<OrderCommand>) {
    const entry = this.list().find(item => item.id === id);
    if (!entry || entry.status === "acknowledged") return;
    this.storage.setItem(`${this.key}:${id}`, JSON.stringify({ ...entry, ...values }));
  }
  private requireReceipt(result: unknown) {
    const receipt = result as { order?: { id?: unknown }; already_synchronized?: unknown } | null;
    if (typeof receipt?.order?.id !== "string" || typeof receipt.already_synchronized !== "boolean") {
      throw new Error("No authoritative order acknowledgement returned");
    }
  }
}
