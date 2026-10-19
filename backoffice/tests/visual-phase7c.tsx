import { createRoot } from "react-dom/client";
import "../src/App.css";
import "../src/theme.css";
import "../src/ui-system.css";
import "../src/premium-theme.css";
import PrinterManagement from "../../pos-web/src/printing/PrinterManagement";
import * as printing from "../../pos-web/src/printing/queue";
import { api } from "../src/api/client";
import { api as posApi } from "../../pos-web/src/api/client";

const query = new URL(location.href).searchParams;
const product = { id: "product-meal", name: "Garden lunch bowl" };
const stations: printing.Station[] = [
  { id: "station-receipt", company_id: "synthetic-company", shop_id: "shop", branch_id: "branch", device_id: "device", name: "Front counter", purpose: "receipt", transport: "system", address: "", paper_width: "80mm", auto_print: true, active: true, routes: [] },
  { id: "station-kitchen", company_id: "synthetic-company", shop_id: "shop", branch_id: "branch", device_id: "device", name: "Main kitchen", purpose: "kitchen", transport: "network", address: "192.168.1.50:9100", paper_width: "80mm", auto_print: true, active: true, routes: [{ target_type: "product", target_id: product.id }] },
  { id: "station-bar", company_id: "synthetic-company", shop_id: "shop", branch_id: "branch", device_id: "device", name: "Garden bar", purpose: "bar", transport: "bluetooth", address: "00:11:22:33:44:55", paper_width: "58mm", auto_print: false, active: true, routes: [] },
];
const payload = { title: "KITCHEN ORDER", order_number: "SYN-0042", table: "12", waiter: "Jamie Patel", notes: "Allergy: no nuts", created_at: "2026-10-19T12:15:00Z", items: [{ name: product.name, quantity: "2", selling_unit: "each", notes: "Dressing on side" }], printer: { transport: "system", address: "", paper_width: "80mm", name: "Kitchen" } };
const jobs = ["pending", "submitted", "uncertain"].map((status, i) => ({ id: `synthetic-job-${i}`, station_id: stations[0].id, sale_id: "synthetic-sale", kind: "kot", payload, status, attempts: status === "pending" ? 0 : 1, created_at: "2026-10-19T12:15:00Z", last_error: status === "uncertain" ? "Delivery unconfirmed. Inspect printer before retry." : null }));
const calls: string[] = [];
api.defaults.adapter = async config => {
  const url = config.url || ""; calls.push(`${config.method} ${url}`);
  let data: unknown = {};
  if (url.includes("/printing/stations/")) data = stations;
  else if (url.includes("/printing/options/")) data = { shops: [{ id: "shop", name: "Central Store" }], branches: [{ id: "branch", shop_id: "shop", name: "Main Floor" }], devices: [{ id: "device", name: "Register 1", branch_id: "branch", shop_id: "shop" }], products: [product, { id: "product-coffee", name: "House coffee" }], categories: [{ id: "category-food", name: "Fresh food" }, { id: "category-drinks", name: "Drinks" }] };
  else if (url.endsWith("/jobs")) data = jobs;
  return { data, status: 200, statusText: "OK", headers: {}, config };
};
posApi.defaults.adapter = api.defaults.adapter;
Object.assign(window, { __phase7cPrinting: printing, __phase7cCalls: calls, __phase7cPayload: payload });
const mode = query.get("app") === "pos" ? "POS" : "Backoffice";
createRoot(document.getElementById("root")!).render(<main style={{ background: "#f5f7f8", minHeight: "100vh", fontFamily: "Inter, system-ui, sans-serif" }}><header style={{ background: "#07583b", color: "white", padding: "20px 24px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}><strong>ApexRetail {mode}</strong><small>Central Store · Synthetic preview</small></header><div style={{ maxWidth: 1200, margin: "24px auto", background: "white", borderRadius: 18, padding: 8 }}><PrinterManagement companyId="synthetic-company" api={api} canManage={query.get("restricted") !== "true"} deviceId={mode === "POS" ? "device" : undefined} deliver={mode === "POS" ? async () => { /* Preview only: no physical transport. */ } : undefined}/></div></main>);
