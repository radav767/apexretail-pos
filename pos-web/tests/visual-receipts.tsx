import { createRoot } from "react-dom/client";
import { buildReceiptHtml } from "../src/printing/receiptFormatter";
import type { PrinterConfig, ReceiptSnapshot } from "../src/printing/types";

const printer: PrinterConfig = {
  enabled: true,
  connectionType: "system",
  selectedPrinterId: "",
  selectedPrinterName: "Synthetic preview",
  paperWidth: "80mm",
  copies: 1,
  autoPrint: false,
  cutPaper: false,
};

const base: ReceiptSnapshot = {
  id: "fixture-sale",
  receipt_number: "FIXTURE-001",
  company_id: "fixture-company",
  business_name: "ApexRetail Preview Store",
  shop_name: "Synthetic Test Shop",
  branch_name: "Preview Branch",
  pos_name: "Fixture Register",
  pos_number: "00",
  cashier_name: "Test Cashier",
  receipt_header: "SAFE FIXTURE — NOT A REAL TRANSACTION",
  receipt_footer: "Manual regression preview only",
  created_at: "2026-09-14T10:00:00Z",
  total_amount: "10.00",
  amount_received: "10.00",
  change_due: "0.00",
  payment_method: "cash",
  status: "completed",
  discount_amount: "0.00",
  sale_discount_amount: "0.00",
  items: [{
    product_id: "fixture-product",
    name: "Fixture Coffee",
    quantity: "2",
    selling_unit: "each",
    unit_price: "5.00",
    line_total: "10.00",
    line_discount_amount: "0.00",
  }],
};

const fixtures: Array<{ title: string; note: string; receipt: ReceiptSnapshot }> = [
  {
    title: "Line discount only",
    note: "10.00 gross − 2.00 line discount = 8.00 total",
    receipt: {
      ...base,
      receipt_number: "FIXTURE-LINE",
      total_amount: "8.00",
      amount_received: "8.00",
      discount_amount: "2.00",
      items: [{ ...base.items[0], line_total: "8.00", line_discount_amount: "2.00" }],
    },
  },
  {
    title: "Sale-wide discount only",
    note: "10.00 gross − 1.00 sale-wide discount = 9.00 total",
    receipt: {
      ...base,
      receipt_number: "FIXTURE-SALE",
      total_amount: "9.00",
      amount_received: "9.00",
      discount_amount: "1.00",
      sale_discount_amount: "1.00",
      items: [{ ...base.items[0], line_total: "9.00" }],
    },
  },
  {
    title: "Line + sale-wide discounts",
    note: "10.00 gross − 2.00 line − 1.00 sale-wide = 7.00 total",
    receipt: {
      ...base,
      receipt_number: "FIXTURE-BOTH",
      total_amount: "7.00",
      amount_received: "7.00",
      discount_amount: "3.00",
      sale_discount_amount: "1.00",
      items: [{ ...base.items[0], line_total: "7.00", line_discount_amount: "2.00" }],
    },
  },
  {
    title: "Archived / reprinted receipt",
    note: "The duplicate banner and original/reprint metadata must be visible; discounts still appear once.",
    receipt: {
      ...base,
      id: "fixture-archived-sale",
      receipt_number: "FIXTURE-ARCHIVE",
      total_amount: "7.00",
      amount_received: "7.00",
      discount_amount: "3.00",
      sale_discount_amount: "1.00",
      is_duplicate: true,
      original_receipt_number: "FIXTURE-ARCHIVE",
      original_sale_time: "2026-09-13T08:30:00Z",
      reprint_at: "2026-09-14T10:05:00Z",
      reprint_count: 2,
      items: [{ ...base.items[0], line_total: "7.00", line_discount_amount: "2.00" }],
    },
  },
];

export function ReceiptGallery() {
  return (
    <main className="gallery">
      <header>
        <p className="eyebrow">Safe synthetic fixtures</p>
        <h1>POS receipt discount regression preview</h1>
        <p>No production API or transaction data is used by this page.</p>
      </header>
      <section className="grid">
        {fixtures.map(({ title, note, receipt }) => (
          <article className="fixture" key={title}>
            <h2>{title}</h2>
            <p>{note}</p>
            <iframe
              title={title}
              srcDoc={buildReceiptHtml(receipt, printer)}
              sandbox=""
            />
          </article>
        ))}
      </section>
    </main>
  );
}

const style = document.createElement("style");
style.textContent = `
  :root { font-family: Inter, system-ui, sans-serif; color: #172033; background: #eef2f7; }
  * { box-sizing: border-box; }
  body { margin: 0; }
  .gallery { max-width: 1500px; margin: 0 auto; padding: 28px; }
  header { margin-bottom: 24px; }
  header h1 { margin: 4px 0 8px; }
  header p { margin: 0; color: #526075; }
  .eyebrow { color: #08745b; font-size: 13px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
  .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }
  .fixture { min-width: 0; padding: 20px; border: 1px solid #d6dee9; border-radius: 16px; background: white; box-shadow: 0 8px 28px rgba(15, 23, 42, .07); }
  .fixture h2 { margin: 0 0 6px; font-size: 18px; }
  .fixture > p { min-height: 42px; margin: 0 0 14px; color: #526075; }
  iframe { display: block; width: 100%; height: 700px; border: 1px solid #cbd5e1; border-radius: 10px; background: white; }
  @media (max-width: 800px) { .gallery { padding: 14px; } .grid { grid-template-columns: 1fr; } }
`;
document.head.append(style);

createRoot(document.getElementById("root")!).render(<ReceiptGallery />);
