const escapeHtml = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

export function quotationHtml(order: { number: string; estimated_subtotal: string; items: { name: string; quantity: string; price: string; unit: string }[] }) {
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Quotation ${escapeHtml(order.number)}</title><style>body{font:14px system-ui;color:#20252b;margin:24px}h1{color:#07583b}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px;border-bottom:1px solid #ddd}p{line-height:1.5}</style></head><body><h1>QUOTATION</h1><p>${escapeHtml(order.number)}</p><table><thead><tr><th>Product</th><th>Quantity</th><th>Unit price</th></tr></thead><tbody>${order.items.filter(i => Number(i.quantity) > 0).map(i => `<tr><td>${escapeHtml(i.name)}</td><td>${escapeHtml(i.quantity)} ${escapeHtml(i.unit)}</td><td>${escapeHtml(i.price)}</td></tr>`).join("")}</tbody></table><p>Estimated subtotal: ${escapeHtml(order.estimated_subtotal)}</p><p>NOT A PAYMENT RECEIPT. Final customer pricing, discounts and taxes are validated at checkout.</p></body></html>`;
}

export function batchCsv(batches: { product_name: string; code: string; quantity: string; expires_on: string }[]) {
  const field = (value: unknown) => {
    let text = String(value ?? "");
    if (/^\s*[=+@-]|^[\t\r]/.test(text)) text = "'" + text;
    return `"${text.replaceAll('"', '""')}"`;
  };
  return [["Product", "Batch", "Quantity", "Expiry"], ...batches.map(b => [b.product_name, b.code, b.quantity, b.expires_on])].map(row => row.map(field).join(",")).join("\r\n");
}
