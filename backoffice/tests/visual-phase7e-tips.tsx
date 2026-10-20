// Preview-only adapters. This file is not a production entry point.
import { createRoot } from "react-dom/client";
import TipsSettingsPanel from "../src/pages/TipsSettingsPanel";
import TipPaymentPanel from "../../pos-web/src/business/TipPaymentPanel";
import ReturnInspectionPanel from "../../pos-web/src/business/ReturnInspectionPanel";
import "../src/theme.css";
import "../src/premium-theme.css";
import { api } from "../src/api/client";
const params = new URL(location.href).searchParams;
const employee = "00000000-0000-4000-a000-000000000001";
const second = "00000000-0000-4000-a000-000000000002";
const shift = "00000000-0000-4000-a000-000000000003";
const hold = "00000000-0000-4000-a000-000000000004";
localStorage.setItem("employee_id", employee); localStorage.setItem("device_id", "synthetic-register");
let settings = { enabled: true, policy: "staff", weights: {}, business_retention_confirmed: false, service_product_id: null };
let holds = [{ id: hold, product: "Synthetic pharmacy stock", quantity: "2.000", refund_reference: "REF-SYN-0042" }];
const calls: { method: string; url: string; data: any }[] = [];
const receipts = new Map();
let failed = false;
api.defaults.adapter = async config => {
  const url = config.url || ""; const body = typeof config.data === "string" ? JSON.parse(config.data) : config.data;
  calls.push({ method: config.method || "get", url, data: body });
  let data: unknown;
  if (url === "/operations/tips/config" && config.method === "put") { settings = body; data = settings; }
  else if (url === "/operations/tips/config") data = settings;
  else if (url === "/operations/tips/options") data = { shifts: [{ id: shift, name: "SHIFT-SYN-0042" }], currencies: [{ code: "USD", precision: 2 }],
    employees: [{ id: employee, name: "Jamie Patel", active: true }, { id: second, name: "Alex Morgan", active: true }], products: [{ id: "service", name: "Reviewed service charge" }] };
  else if (url.startsWith("/operations/tips/reports")) data = { net_tip_receipts: [{ currency: "USD", method: "cash", policy: "staff", amount: "24.00" }, { currency: "USD", method: "card", policy: "shared", amount: "36.00" }, { currency: "USD", method: "mobile", policy: "business", amount: "8.00" }], totals: [{ currency: "USD", method: "cash", kind: "collect", policy: "staff", amount: "24.00" }, { currency: "USD", method: "card", kind: "collect", policy: "shared", amount: "36.00" }, { currency: "USD", method: "mobile", kind: "collect", policy: "business", amount: "8.00" }, { currency: "USD", method: "mobile", kind: "payout", policy: "staff", amount: "12.00" }],
    balances: [{ employee: "Jamie Patel", currency: "USD", outstanding: "32.00", overpaid_after_reversal: false }, { employee: "Alex Morgan", currency: "USD", outstanding: "16.00", overpaid_after_reversal: false }], entries: [{ id: "00000000-0000-4000-a000-000000000009", kind: "collect", method: "cash", currency: "USD", amount: "24.00" }] };
  else if (url === "/operations/tips/entries" || url === "/operations/batches/returns/inspect") {
    if (!receipts.has(body.request_id)) receipts.set(body.request_id, { id: crypto.randomUUID() });
    if (url.endsWith("/inspect")) holds = [];
    if (params.has("timeout") && !failed) { failed = true; throw { isAxiosError: true, code: "ERR_NETWORK", message: "Synthetic timeout after acknowledgement", config }; }
    data = receipts.get(body.request_id);
  } else if (url === "/operations/batches/returns") data = holds;
  else throw new Error(`Unexpected synthetic route ${url}`);
  return { data, status: 200, statusText: "OK", headers: {}, config };
};
Object.assign(window, { __tipCalls: calls, __tipReceiptCount: () => receipts.size });
const view = params.get("view") || "settings";
createRoot(document.getElementById("root")!).render(<main style={{ margin: 0, padding: 12, background: "#f5f7f8", minHeight: "100vh", color: "#20252b", fontFamily: "system-ui" }}><header style={{ background: "#07583b", color: "white", padding: 16, borderRadius: 12 }}><strong>ApexRetail · {view === "settings" ? "Backoffice" : "POS"}</strong><p>Synthetic preview — no live transactions</p></header>
  {view === "settings" ? <TipsSettingsPanel companyId="synthetic-company"/> : view === "returns" ? <section className="business-operations"><h2>Customer return inspection</h2><ReturnInspectionPanel api={api} identity="synthetic-company:synthetic-waiter:register" allowDispose online changed={async () => {}}/></section>
    : <TipPaymentPanel api={api} companyId="synthetic-company" saleId="00000000-0000-4000-a000-000000000006"/>}
</main>);
