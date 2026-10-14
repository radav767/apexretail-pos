import type {
  PrinterConfig,
  ReceiptLineItem,
  ReceiptSnapshot,
} from "./types.ts";
import {
  formatCents,
  multiplyPriceByQuantity,
  parseMoneyToCents,
} from "../decimal.ts";

function money(value: string | number | undefined) {
  return Number(value || 0).toFixed(2);
}

function snapshotAmount(value: string | number | null | undefined) {
  return value == null ? "0.00" : String(value);
}

function snapshotPaymentLines(snapshot: ReceiptSnapshot, width: number) {
  const baseCode = snapshot.base_currency_code || "";
  const paymentCode = snapshot.payment_currency_code || baseCode;
  const foreign = Boolean(paymentCode && baseCode && paymentCode !== baseCode);
  const paid = snapshot.payment_amount_original ?? snapshot.amount_received;
  const tendered = snapshot.tendered_amount_original;
  const change = foreign
    ? snapshot.change_amount_original ?? "0"
    : snapshot.change_amount_original ?? snapshot.change_due;
  return [
    alignLine(`TOTAL${baseCode ? ` (${baseCode})` : ""}`, money(snapshot.total_amount), width),
    alignLine("Payment", snapshot.payment_method.toUpperCase(), width),
    ...(paymentCode ? [alignLine("Payment currency", paymentCode, width)] : []),
    ...(foreign && snapshot.exchange_rate_snapshot
      ? [alignLine(`Rate 1 ${baseCode}`, `${snapshot.exchange_rate_snapshot} ${paymentCode}`, width)]
      : []),
    alignLine("Paid", `${snapshotAmount(paid)}${paymentCode ? ` ${paymentCode}` : ""}`, width),
    ...(tendered != null
      ? [alignLine("Tendered", `${snapshotAmount(tendered)}${paymentCode ? ` ${paymentCode}` : ""}`, width)]
      : []),
    alignLine("Change", `${snapshotAmount(change)}${paymentCode ? ` ${paymentCode}` : ""}`, width),
  ];
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };

    return entities[character];
  });
}

function alignLine(left: string, right: string, width: number) {
  const normalizedLeft = left.trimEnd();
  const normalizedRight = right.trimStart();
  const available = Math.max(1, width - normalizedRight.length);

  if (normalizedLeft.length >= available) {
    return `${normalizedLeft.slice(0, available)}${normalizedRight}`;
  }

  return `${normalizedLeft}${" ".repeat(available - normalizedLeft.length)}${normalizedRight}`;
}

function buildItemLines(item: ReceiptLineItem, width: number) {
  const grossTotal = money(
    multiplyPriceByQuantity(item.unit_price, item.quantity),
  );
  const quantity = Number(item.quantity || 0)
    .toFixed(3)
    .replace(/\.?0+$/, "");
  const unitSuffix = item.selling_unit
    ? ` ${item.selling_unit}`
    : "";
  const priceSuffix = item.selling_unit
    ? `/${item.selling_unit}`
    : "";
  const qtyAndPrice = `${quantity}${unitSuffix} x ${money(item.unit_price)}${priceSuffix}`;

  return [
    item.name.slice(0, width),
    alignLine(qtyAndPrice, grossTotal, width),
    ...(Number(item.line_discount_amount || 0) > 0
      ? [alignLine("  Line discount", `-${money(item.line_discount_amount || 0)}`, width)]
      : []),
  ];
}

function grossItemsTotal(snapshot: ReceiptSnapshot): string {
  return formatCents(
    snapshot.items.reduce(
      (sum, item) =>
        sum + parseMoneyToCents(
          multiplyPriceByQuantity(item.unit_price, item.quantity),
        ),
      0n,
    ),
  );
}

function hasExplicitDiscountComponents(snapshot: ReceiptSnapshot): boolean {
  return snapshot.sale_discount_amount != null
    || snapshot.items.some((item) => item.line_discount_amount != null);
}

function buildShiftSummaryLines(snapshot: ReceiptSnapshot, width: number) {
  const lines = [
    snapshot.business_name || "ApexRetail POS",
    ...(snapshot.shop_name ? [`Shop: ${snapshot.shop_name}`] : []),
    ...(snapshot.branch_name ? [`Branch: ${snapshot.branch_name}`] : []),
    ...(snapshot.pos_name ? [`Register: ${snapshot.pos_name}`] : []),
    `Shift: ${snapshot.receipt_number}`,
    `Printed: ${new Date(snapshot.created_at).toLocaleString()}`,
    ...(snapshot.cashier_name ? [`Cashier: ${snapshot.cashier_name}`] : []),
    "-".repeat(width),
    ...(snapshot.shift_summary_lines || []).map((row) => alignLine(row.label, row.value, width)),
    "-".repeat(width),
    "SHIFT SUMMARY - NOT A SALES RECEIPT",
  ];
  return lines.map((line) => line.slice(0, width));
}

function buildEscPosLines(snapshot: ReceiptSnapshot, config: PrinterConfig) {
  const width = config.paperWidth === "58mm" ? 32 : 48;
  if (snapshot.document_type === "shift_summary") {
    return buildShiftSummaryLines(snapshot, width);
  }
  const createdAt = new Date(snapshot.created_at).toLocaleString();
  const lines: string[] = [];
  const addressLines = [
    snapshot.shop_address?.address_line_1,
    snapshot.shop_address?.address_line_2,
    [
      snapshot.shop_address?.city,
      snapshot.shop_address?.state_province,
    ]
      .filter(Boolean)
      .join(", "),
    snapshot.shop_address?.country,
    snapshot.shop_address?.phone
      ? `Phone: ${snapshot.shop_address.phone}`
      : null,
  ].filter(Boolean) as string[];

  lines.push(snapshot.business_name || "ApexRetail POS");

  if (snapshot.shop_name) {
    lines.push(`Shop: ${snapshot.shop_name}`);
  }

  for (const line of addressLines) {
    lines.push(line);
  }

  if (snapshot.branch_name) {
    lines.push(`Branch: ${snapshot.branch_name}`);
  }

  if (snapshot.pos_name || snapshot.pos_number) {
    lines.push(
      `POS: ${[snapshot.pos_number, snapshot.pos_name]
        .filter(Boolean)
        .join(" ")}`,
    );
  }

  if (snapshot.receipt_header) {
    lines.push(snapshot.receipt_header);
  }

  lines.push(`Receipt: ${snapshot.receipt_number}`);
  lines.push(`Date: ${createdAt}`);
  if (snapshot.shift_id) {
    lines.push(`Shift: ${snapshot.shift_id}`);
  }
  if (snapshot.is_duplicate) {
    lines.push("*** DUPLICATE ***");
    lines.push(`Original receipt: ${snapshot.original_receipt_number || snapshot.receipt_number}`);
    lines.push(`Original sale time: ${new Date(snapshot.original_sale_time || snapshot.created_at).toLocaleString()}`);
    lines.push(`Reprint date/time: ${new Date(snapshot.reprint_at || Date.now()).toLocaleString()}`);
    lines.push(`Reprint count: ${snapshot.reprint_count || 1}`);
  }

  if (snapshot.cashier_name) {
    lines.push(`Cashier: ${snapshot.cashier_name}`);
  }

  if (snapshot.payment_method.toLowerCase() === "credit") {
    if (snapshot.customer_name || snapshot.customer_code) {
      lines.push(
        `Customer: ${[snapshot.customer_name, snapshot.customer_code]
          .filter(Boolean)
          .join(" / ")}`,
      );
    }
    if (snapshot.credit_due_date) {
      lines.push(`Credit due: ${snapshot.credit_due_date}`);
    }
  }

  lines.push("-".repeat(width));

  for (const item of snapshot.items) {
    lines.push(...buildItemLines(item, width));
  }

  lines.push("-".repeat(width));

  lines.push(alignLine("Items before discounts", money(grossItemsTotal(snapshot)), width));

  if (
    hasExplicitDiscountComponents(snapshot)
    && Number(snapshot.sale_discount_amount || 0) > 0
  ) {
    lines.push(
      alignLine(
        "Sale-wide discount",
        `-${money(snapshot.sale_discount_amount || 0)}`,
        width,
      ),
    );
  } else if (
    !hasExplicitDiscountComponents(snapshot)
    && snapshot.discount_amount
    && Number(snapshot.discount_amount) > 0
  ) {
    lines.push(
      alignLine(
        "Discount (combined)",
        `-${money(snapshot.discount_amount)}`,
        width,
      ),
    );
  }

  if (snapshot.tax_amount && Number(snapshot.tax_amount) > 0) {
    const taxLabel =
      snapshot.tax_name?.trim() || "Tax";
    lines.push(alignLine(
      `${taxLabel}${snapshot.tax_inclusive ? " (included)" : ""}`,
      money(snapshot.tax_amount),
      width,
    ));
  }

  lines.push(...snapshotPaymentLines(snapshot, width));

  if (snapshot.receipt_footer) {
    lines.push("-".repeat(width));
    lines.push(snapshot.receipt_footer);
  }

  return lines;
}

export function buildEscPosPayload(snapshot: ReceiptSnapshot, config: PrinterConfig) {
  const encoder = new TextEncoder();
  const commands: number[] = [
    0x1b,
    0x40,
    0x1b,
    0x61,
    0x01,
  ];

  const lines = buildEscPosLines(snapshot, config);

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const centered = index <= 4 || line === (snapshot.receipt_footer || "");

    if (centered) {
      commands.push(0x1b, 0x61, 0x01);
    } else {
      commands.push(0x1b, 0x61, 0x00);
    }

    commands.push(...encoder.encode(line), 0x0a);
  }

  commands.push(0x1b, 0x61, 0x00, 0x0a, 0x0a, 0x0a);

  if (config.cutPaper) {
    commands.push(0x1d, 0x56, 0x42, 0x00);
  }

  return Uint8Array.from(commands);
}

export function encodeBase64(bytes: Uint8Array) {
  let binary = "";

  for (const value of bytes) {
    binary += String.fromCharCode(value);
  }

  return btoa(binary);
}

export function buildReceiptHtml(snapshot: ReceiptSnapshot, config: PrinterConfig) {
  const paperWidth = config.paperWidth === "58mm" ? 224 : 302;
  const createdAt = new Date(snapshot.created_at).toLocaleString();

  if (snapshot.document_type === "shift_summary") {
    const rows = (snapshot.shift_summary_lines || []).map((row) => `
      <div class="summary-row"><span>${escapeHtml(row.label)}</span><span>${escapeHtml(row.value)}</span></div>
    `).join("");
    return `<!doctype html><html><head><meta charset="utf-8"/><title>${escapeHtml(snapshot.receipt_number)}</title><style>body{margin:0;padding:16px;font-family:"Courier New",monospace;color:#111}.receipt{width:${paperWidth}px;margin:0 auto}h1,h2,p{text-align:center;margin:0}.meta{margin-top:4px;font-size:12px}.summary{margin-top:14px;font-size:12px}.summary-row{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px dashed #aaa}.notice{margin-top:14px;text-align:center;font-weight:bold}@media print{body{padding:0}}</style></head><body><div class="receipt"><h1>${escapeHtml(snapshot.business_name || "ApexRetail POS")}</h1>${snapshot.shop_name ? `<p class="meta">Shop: ${escapeHtml(snapshot.shop_name)}</p>` : ""}${snapshot.branch_name ? `<p class="meta">Branch: ${escapeHtml(snapshot.branch_name)}</p>` : ""}${snapshot.pos_name ? `<p class="meta">Register: ${escapeHtml(snapshot.pos_name)}</p>` : ""}<p class="meta">Shift: ${escapeHtml(snapshot.receipt_number)}</p><p class="meta">Printed: ${escapeHtml(createdAt)}</p>${snapshot.cashier_name ? `<p class="meta">Cashier: ${escapeHtml(snapshot.cashier_name)}</p>` : ""}<div class="summary">${rows}</div><p class="notice">SHIFT SUMMARY - NOT A SALES RECEIPT</p></div></body></html>`;
  }

  const itemRows = snapshot.items
    .map(
      (item) => {
        const lineDiscount = Number(item.line_discount_amount || 0) > 0
          ? `<tr class="discount-detail"><td colspan="3">Line discount</td><td style="text-align:right">-${money(item.line_discount_amount || 0)}</td></tr>`
          : "";
        return `
        <tr>
          <td>${escapeHtml(item.name)}</td>
          <td style="text-align:center">${Number(item.quantity).toFixed(3).replace(/\.?0+$/, "")}${item.selling_unit ? ` ${escapeHtml(item.selling_unit)}` : ""}</td>
          <td style="text-align:right">${money(item.unit_price)}${item.selling_unit ? `/${escapeHtml(item.selling_unit)}` : ""}</td>
          <td style="text-align:right">${money(multiplyPriceByQuantity(item.unit_price, item.quantity))}</td>
        </tr>
        ${lineDiscount}
      `;
      },
    )
    .join("");

  const taxRow =
    snapshot.tax_amount && Number(snapshot.tax_amount) > 0
      ? `
        <div class="summary-row">
          <span>${escapeHtml(snapshot.tax_name?.trim() || "Tax")}${snapshot.tax_inclusive ? " (included)" : ""}</span>
          <span>${money(snapshot.tax_amount)}</span>
        </div>
      `
      : "";

  const discountRow = hasExplicitDiscountComponents(snapshot)
    ? snapshot.sale_discount_amount && Number(snapshot.sale_discount_amount) > 0
      ? `
        <div class="summary-row">
          <span>Sale-wide discount</span>
          <span>-${money(snapshot.sale_discount_amount)}</span>
        </div>
      `
      : ""
    : snapshot.discount_amount && Number(snapshot.discount_amount) > 0
      ? `<div class="summary-row"><span>Discount (combined)</span><span>-${money(snapshot.discount_amount)}</span></div>`
      : "";

  return `
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>${escapeHtml(snapshot.receipt_number)}</title>
        <style>
          body {
            margin: 0;
            padding: 16px;
            font-family: "Courier New", monospace;
            color: #111;
          }
          .receipt {
            width: ${paperWidth}px;
            margin: 0 auto;
          }
          h1, h2, p {
            margin: 0;
            text-align: center;
          }
          h1 {
            font-size: 18px;
            margin-bottom: 4px;
          }
          p.meta {
            margin-top: 3px;
            font-size: 12px;
          }
          table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            font-size: 12px;
          }
          th, td {
            border-bottom: 1px dashed #999;
            padding: 6px 0;
          }
          .summary {
            margin-top: 12px;
            font-size: 13px;
          }
          .summary-row,
          .summary-total {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 4px 0;
          }
          .summary-total {
            font-weight: 700;
            font-size: 16px;
          }
          .footer {
            margin-top: 16px;
            text-align: center;
            font-size: 12px;
          }
          @media print {
            body {
              padding: 0;
            }
          }
        </style>
      </head>
      <body>
        <div class="receipt">
          <h1>${escapeHtml(snapshot.business_name || "ApexRetail POS")}</h1>
          ${snapshot.shop_name ? `<p class="meta">Shop: ${escapeHtml(snapshot.shop_name)}</p>` : ""}
          ${snapshot.shop_address?.address_line_1 ? `<p class="meta">${escapeHtml(snapshot.shop_address.address_line_1)}</p>` : ""}
          ${snapshot.shop_address?.address_line_2 ? `<p class="meta">${escapeHtml(snapshot.shop_address.address_line_2)}</p>` : ""}
          ${
            snapshot.shop_address?.city ||
            snapshot.shop_address?.state_province
              ? `<p class="meta">${escapeHtml(
                  [snapshot.shop_address?.city, snapshot.shop_address?.state_province]
                    .filter(Boolean)
                    .join(", "),
                )}</p>`
              : ""
          }
          ${snapshot.shop_address?.country ? `<p class="meta">${escapeHtml(snapshot.shop_address.country)}</p>` : ""}
          ${snapshot.branch_name ? `<p class="meta">Branch: ${escapeHtml(snapshot.branch_name)}</p>` : ""}
          ${
            snapshot.pos_name || snapshot.pos_number
              ? `<p class="meta">POS: ${escapeHtml(
                  [snapshot.pos_number, snapshot.pos_name]
                    .filter(Boolean)
                    .join(" "),
                )}</p>`
              : ""
          }
          ${snapshot.receipt_header ? `<p class="meta">${escapeHtml(snapshot.receipt_header)}</p>` : ""}
          <p class="meta">Receipt: ${escapeHtml(snapshot.receipt_number)}</p>
          <p class="meta">${escapeHtml(createdAt)}</p>
          ${snapshot.shift_id ? `<p class="meta">Shift: ${escapeHtml(snapshot.shift_id)}</p>` : ""}
          ${snapshot.is_duplicate ? `<h2 style="font-size:24px;margin:10px 0">DUPLICATE</h2><p class="meta">Original receipt: ${escapeHtml(snapshot.original_receipt_number || snapshot.receipt_number)}</p><p class="meta">Original sale time: ${escapeHtml(new Date(snapshot.original_sale_time || snapshot.created_at).toLocaleString())}</p><p class="meta">Reprint date/time: ${escapeHtml(new Date(snapshot.reprint_at || Date.now()).toLocaleString())}</p><p class="meta">Reprint count: ${snapshot.reprint_count || 1}</p>` : ""}
          ${snapshot.cashier_name ? `<p class="meta">Cashier: ${escapeHtml(snapshot.cashier_name)}</p>` : ""}
          ${snapshot.payment_method.toLowerCase() === "credit" && (snapshot.customer_name || snapshot.customer_code) ? `<p class="meta">Customer: ${escapeHtml([snapshot.customer_name, snapshot.customer_code].filter(Boolean).join(" / "))}</p>` : ""}
          ${snapshot.payment_method.toLowerCase() === "credit" && snapshot.credit_due_date ? `<p class="meta">Credit due: ${escapeHtml(snapshot.credit_due_date)}</p>` : ""}
          <table>
            <thead>
              <tr>
                <th style="text-align:left">Item</th>
                <th>Qty</th>
                <th style="text-align:right">Unit</th>
                <th style="text-align:right">Total</th>
              </tr>
            </thead>
            <tbody>${itemRows}</tbody>
          </table>
          <div class="summary">
            ${
              `
                  <div class="summary-row">
                    <span>Items before discounts</span>
                    <span>${money(grossItemsTotal(snapshot))}</span>
                  </div>
                `
            }
            ${discountRow}
            ${taxRow}
            <div class="summary-total">
              <span>Total${snapshot.base_currency_code ? ` (${escapeHtml(snapshot.base_currency_code)})` : ""}</span>
              <span>${money(snapshot.total_amount)}</span>
            </div>
            <div class="summary-row">
              <span>Payment</span>
              <span>${escapeHtml(snapshot.payment_method.toUpperCase())}</span>
            </div>
            ${snapshot.payment_currency_code ? `<div class="summary-row"><span>Payment currency</span><span>${escapeHtml(snapshot.payment_currency_code)}</span></div>` : ""}
            ${snapshot.base_currency_code && snapshot.payment_currency_code && snapshot.base_currency_code !== snapshot.payment_currency_code && snapshot.exchange_rate_snapshot ? `<div class="summary-row"><span>Rate (1 ${escapeHtml(snapshot.base_currency_code)})</span><span>${escapeHtml(snapshot.exchange_rate_snapshot)} ${escapeHtml(snapshot.payment_currency_code)}</span></div>` : ""}
            <div class="summary-row">
              <span>Paid</span>
              <span>${escapeHtml(snapshotAmount(snapshot.payment_amount_original ?? snapshot.amount_received))}${snapshot.payment_currency_code ? ` ${escapeHtml(snapshot.payment_currency_code)}` : ""}</span>
            </div>
            ${snapshot.tendered_amount_original != null ? `<div class="summary-row"><span>Tendered</span><span>${escapeHtml(snapshotAmount(snapshot.tendered_amount_original))}${snapshot.payment_currency_code ? ` ${escapeHtml(snapshot.payment_currency_code)}` : ""}</span></div>` : ""}
            <div class="summary-row">
              <span>Change</span>
              <span>${escapeHtml(snapshotAmount(snapshot.change_amount_original ?? snapshot.change_due))}${snapshot.payment_currency_code ? ` ${escapeHtml(snapshot.payment_currency_code)}` : ""}</span>
            </div>
            ${snapshot.payment_method.toLowerCase() === "credit" ? `<div class="summary-row"><span>Credit sale outstanding</span><span>${money(snapshot.credit_outstanding_balance || snapshot.total_amount)}</span></div>` : ""}
          </div>
          ${snapshot.receipt_footer ? `<p class="footer">${escapeHtml(snapshot.receipt_footer)}</p>` : ""}
        </div>
      </body>
    </html>
  `;
}
