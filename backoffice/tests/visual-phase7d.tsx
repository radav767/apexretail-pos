import { createRoot } from "react-dom/client";
import "../src/App.css";
import "../src/theme.css";
import "../src/ui-system.css";
import "../src/premium-theme.css";
import BusinessOperations from "../../pos-web/src/business/BusinessOperations";
import * as access from "../../pos-web/src/business/access";
import { api } from "../src/api/client";

const params = new URL(location.href).searchParams;
const business = params.get("profile") || "restaurant";
const permissions = params.get("role") === "kitchen" ? { kitchen_view: true, kitchen_update: true, sales: false } : {};
const profile = { profile: business, name: ({ restaurant: "Restaurant / Café", hospitality: "Hotel / Hospitality", pharmacy: "Pharmacy", wholesale: "Hardware / Wholesale" } as Record<string, string>)[business], administrator: params.get("role") !== "kitchen", features: business === "hospitality" ? ["restaurant", "hospitality"] : [business], permissions };
Object.assign(profile, { employee_id: params.has("offline") ? "synthetic-waiter" : undefined });
const products = [{ id: "meal", name: "Garden lunch bowl", selling_price: "12.00", unit: "each", product_type: "standard" }, { id: "coffee", name: "House coffee", selling_price: "3.50", unit: "each", product_type: "standard" }, { id: "tip", name: "Voluntary tip", selling_price: "1.00", unit: "each", product_type: "service" }];
let tables = [{ id: "table-1", branch_id: "branch", name: "Table 1", floor: "Main floor", seats: 2, x: 1, y: 1, active: true }, { id: "table-4", branch_id: "branch", name: "Table 4", floor: "Main floor", seats: 4, x: 7, y: 1, active: true }, { id: "table-12", branch_id: "branch", name: "Table 12", floor: "Main floor", seats: 6, x: 13, y: 4, active: true }];
let orders = [{ id: "order-a", number: "O-SYN-0042", kind: business === "wholesale" ? "quotation" : "restaurant", status: "open", version: 3, branch_id: "branch", device_id: "register", table_id: "table-12", waiter_id: "staff", guest_id: null, sale_id: null, table_name: "Table 12", waiter_name: "Jamie Patel", estimated_subtotal: "31.00", items: [{ id: "line-1", product_id: "meal", variant_id: null, name: "Garden lunch bowl", quantity: "2", sent_quantity: "2", price: "12.00", unit: "each", notes: "No nuts" }, { id: "line-2", product_id: "coffee", variant_id: null, name: "House coffee", quantity: "2", sent_quantity: "2", price: "3.50", unit: "each", notes: "Oat milk" }] }];
const calls: string[] = [];
api.defaults.adapter = async config => {
  const url = config.url || ""; const body = typeof config.data === "string" ? JSON.parse(config.data) : config.data;
  calls.push(`${config.method} ${url}`);
  let data: unknown;
  if (url === "/operations/profile") data = profile;
  else if (url === "/operations/options") data = { branches: [{ id: "branch", name: "Main Floor" }], devices: [{ id: "register", name: "Register 1", branch_id: "branch" }], products, variants: [], staff: [{ id: "staff", name: "Jamie Patel", branch_id: "branch" }], customers: [{ id: "customer", name: "Alex Morgan" }] };
  else if (url === "/operations/tables" && config.method === "post") { tables = [...tables, { id: "new-table", ...body }]; data = tables.at(-1); }
  else if (url === "/operations/tables") data = tables;
  else if (url === "/operations/orders" || url.startsWith("/operations/orders?")) data = orders;
  else if (url.endsWith("/send")) data = { order: orders[0], jobs: [] };
  else if (url === "/operations/kitchen") data = ["kitchen", "bar"].flatMap(purpose => ["queued", "preparing", "ready"].map((status, i) => ({ id: `${purpose}-${i}`, status, purpose, station_name: purpose === "kitchen" ? "Main kitchen" : "Garden bar", print_status: i === 0 ? "pending" : "submitted", payload: { order_number: `O-SYN-00${42+i}`, title: "KITCHEN ORDER UPDATE", table: `Table ${12+i}`, waiter: "Jamie Patel", created_at: "2026-10-19T12:15:00Z", items: purpose === "kitchen" ? [{ name: "Garden lunch bowl", quantity: "2", notes: "No nuts · dressing on side" }] : [{ name: "House iced coffee", quantity: "2", notes: "Oat milk" }] } })));
  else if (url === "/operations/rooms") data = [{ id: "room-a", name: "Room 204", branch_id: "branch", active: true, guests: [{ id: "guest", customer_id: "customer" }] }, { id: "room-b", name: "Room 205", branch_id: "branch", active: true, guests: [] }];
  else if (url.endsWith("/folio")) data = { guest_name: "Alex Morgan", charges: [{ receipt_number: "SYN-0042", currency: "USD", amount: "31.00", outstanding: "31.00" }] };
  else if (url === "/operations/batches") data = [{ id: "batch-a", product_name: "Synthetic stocked item A", code: "LOT-2026-A", quantity: "124", expires_on: "2026-11-02", expired: false, expires_soon: true }, { id: "batch-b", product_name: "Synthetic stocked item B", code: "LOT-2026-B", quantity: "48", expires_on: "2027-04-30", expired: false, expires_soon: false }, { id: "batch-c", product_name: "Synthetic stocked item C", code: "LOT-2026-C", quantity: "8", expires_on: "2026-10-01", expired: true, expires_soon: false }];
  else if (url === "/operations/batches/returns") data = [];
  else if (url.startsWith("/operations/reports")) data = { currency_totals: [{ currency: "USD", sales: "728.00", refunds: "12.00", discounts: "18.00", orders: 24 }] };
  else throw new Error(`Synthetic preview has no handler for ${config.method} ${url}`);
  return { data, status: 200, statusText: "OK", headers: {}, config };
};
Object.assign(window, { __phase7dAccess: access, __phase7dCalls: calls });
createRoot(document.getElementById("root")!).render(<main style={{ background: "#f5f7f8", minHeight: "100vh", fontFamily: "Inter, system-ui, sans-serif" }}><header style={{ background: "#07583b", color: "white", padding: "20px 24px", display: "flex", justifyContent: "space-between", gap: 12 }}><strong>ApexRetail {params.get("app") === "pos" ? "POS" : "Backoffice"}</strong><small>Central Store · Synthetic preview</small></header><div style={{ maxWidth: 1250, margin: "24px auto", background: "white", borderRadius: 18, padding: 8 }}><BusinessOperations companyId="synthetic-company" api={api} branchId="branch" deviceId="register" /></div></main>);
