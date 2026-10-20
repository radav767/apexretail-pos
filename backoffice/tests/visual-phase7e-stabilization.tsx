// Local test entry only. Never imported by the production application.
import { createRoot } from "react-dom/client";
import BatchStockPanel from "../../pos-web/src/business/BatchStockPanel";
import BusinessOperations from "../../pos-web/src/business/BusinessOperations";
import { OfflineOrderOutbox } from "../../pos-web/src/business/offlineOrders";
import "../../pos-web/src/business/business.css";
import "../../pos-web/src/business/business-mobile.css";
const params = new URL(location.href).searchParams;
const identity = { company: "synthetic-stabilization-company", employee: params.get("employee") || "synthetic-waiter", device: "synthetic-register" };
const calls: { endpoint: string; payload: any }[] = [];
const receipts = new Map(); let first = true;
const api = {
  async get<T>(endpoint: string): Promise<{ data: T }> { throw new Error(`Synthetic API unavailable: ${endpoint}`); },
  async put<T>(): Promise<{ data: T }> { throw new Error("Unexpected write"); },
  async post<T>(endpoint: string, payload: any): Promise<{ data: T }> {
    calls.push({ endpoint, payload });
    if (params.has("conflict")) throw { response: { status: 409, data: { detail: "Synthetic order version conflict" } } };
    if (!receipts.has(payload.request_id)) receipts.set(payload.request_id, endpoint.includes("batches")
      ? { movement_id: "synthetic-stock-movement", batch_id: "synthetic-variant-lot" }
      : { already_synchronized: true, order: { id: "synthetic-original-order" } });
    if (first && params.has("timeout")) { first = false; throw new Error("Synthetic response lost after server commit"); }
    return { data: (params.has("malformed") ? "<html>not an acknowledgement</html>" : receipts.get(payload.request_id)) as T };
  },
};
if (params.has("seed") && !localStorage.getItem("synthetic-seeded")) {
  new OfflineOrderOutbox(localStorage, identity).enqueue({ id: "original-synthetic-command", endpoint: "/operations/offline/drafts", payload: {
    request_id: "original-synthetic-command", employee_id: identity.employee, captured_at: "2026-10-19T12:00:00Z",
    order: { branch_id: "synthetic-branch", device_id: identity.device, request_id: "original-order-request" }, items: [{ product_id: "synthetic-medicine", quantity: "2" }],
  } });
  localStorage.setItem("synthetic-seeded", "true");
}
Object.assign(window, { __stabilizationCalls: calls, __stabilizationReceipts: () => receipts.size });
createRoot(document.getElementById("root")!).render(<main style={{ padding: 12, background: "#f5f7f8", minHeight: "100vh", fontFamily: "system-ui", color: "#20252b" }}><header style={{ background: "#07583b", color: "white", borderRadius: 12, padding: 16 }}><strong>ApexRetail · Stabilization review</strong><p>Synthetic data · Development only</p></header>
  {params.get("view") === "recovery" ? <BusinessOperations companyId={identity.company} branchId="synthetic-branch" deviceId={identity.device} recoveryEmployeeId={identity.employee} api={api}/>
    : <section className="business-operations"><h2>Variant batch inventory</h2><BatchStockPanel identity="synthetic-variant-stock" branch="synthetic-branch" products={[{ id: "synthetic-medicine", name: "Synthetic medicine" }]} variants={[{ id: "strength-a", product_id: "synthetic-medicine", name: "250mg" }, { id: "strength-b", product_id: "synthetic-medicine", name: "500mg" }]} receive adjust online send={async payload => (await api.post("/operations/batches/stock", payload)).data} changed={async () => {}}/></section>}
</main>);
