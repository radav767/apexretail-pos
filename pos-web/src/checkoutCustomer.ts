export type BasicCustomer = { company_id: string; request_id: string; name: string; phone: string | null; email: string | null; address: string | null };
export class CheckoutCustomerCommands {
  private key: string;
  private company: string;
  private storage: Storage;
  constructor(company: string, actor: string, storage: Storage) {
    if (!company || !actor) throw new Error("Sign in again before creating a customer.");
    this.company = company; this.storage = storage; this.key = `apexretail_checkout_customer_v1:${encodeURIComponent(company)}:${encodeURIComponent(actor)}`;
  }
  read(): BasicCustomer | null {
    const raw = this.storage.getItem(this.key); if (!raw) return null;
    let value: BasicCustomer; try { value = JSON.parse(raw); } catch { throw new Error("The pending customer request needs review. Nothing was removed."); }
    if (!value || value.company_id !== this.company || typeof value.name !== "string" || !value.name.trim() || typeof value.request_id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.request_id) || Object.keys(value).sort().join() !== "address,company_id,email,name,phone,request_id" || [value.phone, value.email, value.address].some(v => v !== null && typeof v !== "string")) throw new Error("The pending customer request needs review. Nothing was removed.");
    return value;
  }
  prepare(contact: { name: string; phone: string; email: string; address: string }): BasicCustomer {
    const previous = this.read(); if (previous) return previous;
    if (!contact.name.trim()) throw new Error("Customer name is required.");
    const payload = { company_id: this.company, request_id: crypto.randomUUID(), name: contact.name.trim(), phone: contact.phone.trim() || null, email: contact.email.trim() || null, address: contact.address.trim() || null };
    this.storage.setItem(this.key, JSON.stringify(payload)); return payload;
  }
  confirm(payload: BasicCustomer, customer: { id?: unknown; company_id?: unknown; customer_code?: unknown; active?: unknown; name?: unknown }): void {
    if (!customer || customer.company_id !== this.company || typeof customer.id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(customer.id) || typeof customer.name !== "string" || !customer.name.trim() || customer.customer_code !== `POS-${payload.request_id.replaceAll("-", "").toUpperCase()}` || typeof customer.active !== "boolean") throw new Error("Customer creation was not confirmed. Original request retained.");
    const pending = this.read(); if (!pending || pending.request_id !== payload.request_id) throw new Error("Pending customer request changed. Review before retrying.");
    this.storage.removeItem(this.key);
  }
}
