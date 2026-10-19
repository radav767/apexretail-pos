import { api } from "../api/client";
import { buildReceiptHtml, buildEscPosPayload, encodeBase64 } from "./receiptFormatter";
import { sendReceiptToPrinter } from "./printerConfig";
import type { PrinterConfig, ReceiptSnapshot } from "./types";

export type Station = {
  id: string; name: string; purpose: "receipt" | "kitchen" | "bar";
  company_id: string; shop_id: string; branch_id: string; device_id: string;
  transport: PrinterConfig["connectionType"]; address: string;
  paper_width: "58mm" | "80mm"; active: boolean; auto_print: boolean;
  routes: { target_type: "product" | "category"; target_id: string }[];
};
export type PrintJob = {
  id: string; station_id: string; sale_id: string | null; kind: "receipt" | "kot" | "test";
  status: "pending" | "sending" | "submitted" | "uncertain" | "cancelled";
  payload: Record<string, unknown> & { printer: { transport: PrinterConfig["connectionType"]; address: string; paper_width: "58mm" | "80mm"; name: string } };
  payload_hash: string; attempts: number; last_error: string | null; created_at: string;
};
const escapeHtml = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
// Prevent item notes/names from injecting ESC/POS device commands.
export const safePrintText = (value: unknown) => Array.from(String(value ?? ""), c => {
  const code = c.codePointAt(0)!;
  return code < 32 || (code >= 127 && code <= 159) ? " " : c;
}).join("");
export function ticketLines(payload: Record<string, unknown>) {
  const items = (payload.items || []) as Array<Record<string, unknown>>;
  const previous = payload.previous_location as { table?: string; waiter?: string } | undefined;
  return [payload.reprint ? "DUPLICATE" : "", payload.title,
    `Order ${payload.order_number || "TEST"}`, `Table ${payload.table || "—"}`,
    previous ? `Previous: ${previous.table || "—"} / ${previous.waiter || "—"}` : "",
    `Waiter ${payload.waiter || "—"}`, payload.created_at,
    ...items.flatMap(i => [`${i.quantity} ${i.selling_unit || ""}  ${i.name}`, i.notes || ""]),
    payload.notes || "", "NOT A PAYMENT RECEIPT"].filter(Boolean).map(safePrintText);
}
export function renderTicket(payload: Record<string, unknown>, width: "58mm" | "80mm") {
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>@page{size:${width} auto;margin:3mm}body{width:${width === "58mm" ? "50" : "72"}mm;font:14px monospace;margin:0;overflow-wrap:anywhere}p{margin:8px 0}h1{font-size:18px}</style></head><body>${ticketLines(payload).map((line, i) => i === 0 ? `<h1>${escapeHtml(line)}</h1>` : `<p>${escapeHtml(line)}</p>`).join("")}</body></html>`;
}
const busy = new Set<string>();
export async function deliverJob(job: PrintJob, dependencies?: { transport?: typeof sendReceiptToPrinter; client?: Pick<typeof api, "post"> }) {
  if (busy.has(job.id) || job.status !== "pending") return;
  busy.add(job.id);
  const token = crypto.randomUUID();
  let claimed = false;
  const client = dependencies?.client || api;
  const transport = dependencies?.transport || sendReceiptToPrinter;
  try {
    // A claim response timeout is NOT permission to print or claim again.
    await client.post(`/printing/jobs/${job.id}/claim`, { token });
    claimed = true;
    const p = job.payload.printer;
    const config: PrinterConfig = { enabled: true, connectionType: p.transport, selectedPrinterId: p.address,
      selectedPrinterName: p.name, paperWidth: p.paper_width, copies: 1, autoPrint: false, cutPaper: false };
    let html: string, rawDataBase64: string;
    if (job.kind === "receipt") {
      const snapshot = job.payload as unknown as ReceiptSnapshot;
      // ESC/POS receipt data is sanitized recursively, but amounts remain unchanged.
      const clean = JSON.parse(JSON.stringify(snapshot, (_key, value) => typeof value === "string" ? safePrintText(value) : value)) as ReceiptSnapshot;
      html = buildReceiptHtml(snapshot, config);
      rawDataBase64 = encodeBase64(buildEscPosPayload(clean, config));
    } else {
      html = renderTicket(job.payload, p.paper_width);
      const columns = p.paper_width === "58mm" ? 32 : 48;
      const wrapped = ticketLines(job.payload).flatMap(line => {
        const chars = Array.from(line); const lines: string[] = [];
        while (chars.length) lines.push(chars.splice(0, columns).join(""));
        return lines;
      }).join("\n");
      rawDataBase64 = encodeBase64(new TextEncoder().encode(`\x1b@${wrapped}\n\n\n`));
    }
    await transport({ config, html, rawDataBase64, jobName: `Print ${job.id}` });
    // "submitted" deliberately does not claim that paper physically printed.
    await client.post(`/printing/jobs/${job.id}/result`, { token, outcome: "submitted" });
  } catch (error) {
    if (claimed) {
      try { await client.post(`/printing/jobs/${job.id}/result`, { token, outcome: "uncertain", error: "Delivery unconfirmed. Inspect printer before an authorized retry." }); } catch { /* Sending remains visible; never auto-repeat. */ }
    }
    throw error;
  } finally { busy.delete(job.id); }
}

// Separate non-financial outbox. Never stores credentials or touches offline_sales.
// A failed enqueue must not convert a committed sale into a checkout failure.
type Intent = { company: string; cashier: string; device: string; sale: string; synchronizedOffline?: boolean };
const OUTBOX = "apexretail_print_intents_v1";
function readIntents(): Intent[] {
  const raw = localStorage.getItem(OUTBOX);
  if (!raw) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed)) throw new Error("Print outbox needs operator review");
  return parsed as Intent[];
}
export function getOfflinePrintReviews(company: string) {
  return readIntents().filter(i => i.synchronizedOffline && i.company === company && i.cashier === (localStorage.getItem("employee_id") || "") && i.device === (localStorage.getItem("device_id") || ""));
}
export async function resolveOfflinePrintReview(company: string, sale: string, decision: string, reason: string) {
  await api.post(`/printing/offline-review/${sale}`, { decision, reason });
  // Remove only the acknowledged non-financial print intent, never a sale.
  localStorage.setItem(OUTBOX, JSON.stringify(readIntents().filter(i => !(i.company === company && i.sale === sale && i.synchronizedOffline))));
}
export function rememberPrintIntent(company: string, sale: string, synchronizedOffline = false) {
  const intents = readIntents();
  if (!intents.some(i => i.company === company && i.sale === sale)) {
    intents.push({ company, sale, cashier: localStorage.getItem("employee_id") || "", device: localStorage.getItem("device_id") || "", synchronizedOffline });
    localStorage.setItem(OUTBOX, JSON.stringify(intents));
  }
}
export async function scheduleSalePrint(company: string, sale: string) {
  rememberPrintIntent(company, sale);
  const { data: stations } = await api.get<Station[]>(`/printing/stations/${company}`);
  const centralizedReceipt = stations.some(s => s.active && s.auto_print && s.purpose === "receipt" && s.device_id === localStorage.getItem("device_id"));
  void flushPrintIntents().catch(error => console.warn("Print delivery needs review", error));
  return centralizedReceipt;
}
let flushing = false;
export async function flushPrintIntents() {
  if (flushing || !navigator.onLine) return;
  flushing = true;
  try {
    for (const intent of readIntents()) {
      if (intent.cashier !== (localStorage.getItem("employee_id") || "") || intent.device !== (localStorage.getItem("device_id") || "") || intent.company !== localStorage.getItem("company_id")) continue;
      const { data: stations } = await api.get<Station[]>(`/printing/stations/${intent.company}`);
      // An offline receipt may already have printed locally, even in older
      // clients. No evidence means no automatic second receipt after sync.
      // Kitchen tickets also need review when delayed by an offline period.
      if (intent.synchronizedOffline) continue;
      for (const station of stations.filter(s => s.active && s.auto_print && s.device_id === intent.device)) {
        try {
          const { data: job } = await api.post<PrintJob>(`/printing/station/${station.id}/jobs`, { sale_id: intent.sale, kind: station.purpose === "receipt" ? "receipt" : "kot", request_key: "original" });
          await deliverJob(job);
        } catch (error: unknown) {
          const status = (error as { response?: { status?: number; data?: { detail?: string } } }).response;
          if (status?.status === 409 && status.data?.detail === "No items routed to this station") continue;
          if (status?.status === 409 && status.data?.detail === "Use the original open-order kitchen tickets; payment must not send preparation again") continue;
          throw error;
        }
      }
      // Re-read so an intent appended during I/O is never lost.
      localStorage.setItem(OUTBOX, JSON.stringify(readIntents().filter(i => !(i.company === intent.company && i.sale === intent.sale))));
    }
  } finally { flushing = false; }
}
