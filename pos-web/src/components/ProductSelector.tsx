import { useEffect, useId, useRef, useState } from "react";
import "./product-selector.css";

export type SelectionProduct = { id: string; name: string; sku: string | null; barcode: string | null; unit: string; category_name: string | null; selling_price: string | number | null; branch_stock_qty: string | number | null };
export type SelectionPage = { items: SelectionProduct[]; page: number; total_pages: number; total: number };
type Client = { get: (path: string, config: { params: Record<string, unknown>; signal: AbortSignal }) => Promise<{ data: SelectionPage }> };
export default function ProductSelector({ companyId, branchId, scopeKey, value, selectedLabel, onChange, client, disabled = false, label = "Product", categoryId }: {
  companyId: string; branchId: string; scopeKey: string; value: string; selectedLabel?: string;
  onChange: (id: string, product: SelectionProduct) => void; client: Client; disabled?: boolean; label?: string; categoryId?: string;
}) {
  const id = useId(), generation = useRef(0), searchInput = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState(""), [page, setPage] = useState(1), [result, setResult] = useState<SelectionPage | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [choice, setChoice] = useState<{ id: string; name: string } | null>(null);
  const [cursor, setCursor] = useState(0), [retry, setRetry] = useState(0), [resultScope, setResultScope] = useState("");
  const scope = JSON.stringify([companyId, branchId, scopeKey, query, categoryId, page, disabled, retry]);
  const visible = resultScope === scope ? result : null;
  useEffect(() => { setQuery(""); setPage(1); setChoice(null); }, [companyId, branchId, scopeKey]);
  useEffect(() => {
    const request = ++generation.current, controller = new AbortController();
    setResult(null); setCursor(0); setError("");
    if (!companyId || !branchId || disabled) { setBusy(false); return; }
    setBusy(true);
    const timer = window.setTimeout(() => {
      void client.get(`/products/${companyId}/selection`, { params: { branch_id: branchId, search: query, category_id: categoryId, page, page_size: 25 }, signal: controller.signal }).then(({ data }) => {
        if (generation.current !== request || controller.signal.aborted) return;
        if (!Array.isArray(data.items) || data.page !== page || !Number.isInteger(data.total) || !Number.isInteger(data.total_pages)) throw new Error("Invalid product search response");
        setResultScope(scope); setResult(data); setBusy(false);
      }).catch(() => { if (generation.current === request && !controller.signal.aborted) { setError("Product search failed. Retry when connected."); setBusy(false); } });
    }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [client, companyId, branchId, scopeKey, query, categoryId, page, disabled, retry, scope]);
  function choose(product: SelectionProduct) { if (busy || disabled || !visible) return; setChoice(product); onChange(product.id, product); searchInput.current?.focus(); }
  const rows = visible?.items || [];
  return <div className="product-selector">
    <label htmlFor={id}>{label}: search name, SKU or barcode</label>
    <input id={id} ref={searchInput} type="search" autoComplete="off" value={query} disabled={disabled || !branchId} aria-controls={`${id}-results`} aria-describedby={`${id}-status`}
      onChange={e => { setQuery(e.target.value); setPage(1); }} onKeyDown={e => {
        if (["ArrowDown", "ArrowUp", "Enter"].includes(e.key)) e.preventDefault();
        if (e.key === "ArrowDown") setCursor(n => Math.min(n + 1, rows.length - 1));
        if (e.key === "ArrowUp") setCursor(n => Math.max(n - 1, 0));
        if (e.key === "Enter" && rows[cursor]) choose(rows[cursor]);
      }} />
    <p id={`${id}-status`} role="status">{busy ? "Searching…" : error || (visible ? `${visible.total} products · Page ${visible.page} of ${Math.max(1, visible.total_pages)}` : "Choose a branch to search")}</p>
    {value && <p>Selected: {choice?.id === value ? choice.name : selectedLabel || "Previously selected product"}</p>}
    <div className="product-selector-scroll"><table id={`${id}-results`} aria-label={`${label} results`} aria-busy={busy}>
      <thead><tr><th>Product</th><th>SKU / Barcode</th><th>Category</th><th>Unit</th><th>Price</th><th>Branch stock</th><th>Select</th></tr></thead>
      <tbody>{rows.map((product, index) => <tr key={product.id} className={index === cursor ? "product-selector-focused" : undefined}>
        <td>{product.name}</td><td>{product.sku || "—"}<br />{product.barcode || "—"}</td><td>{product.category_name || "—"}</td><td>{product.unit}</td><td>{product.selling_price ?? "Unavailable"}</td><td>{product.branch_stock_qty ?? "Not tracked"}</td>
        <td><button type="button" disabled={busy || disabled} aria-label={`Select ${product.name}`} aria-pressed={value === product.id} onClick={() => choose(product)}>Select</button></td>
      </tr>)}</tbody>
    </table></div>
    {!busy && visible && rows.length === 0 && <p>No matching products.</p>}
    <div className="product-selector-pages"><button type="button" disabled={busy || disabled || page <= 1} onClick={() => setPage(n => n - 1)}>Previous products</button><button type="button" disabled={busy || disabled || !visible || page >= visible.total_pages} onClick={() => setPage(n => n + 1)}>Next products</button>
    {error && <button type="button" onClick={() => setRetry(n => n + 1)}>Retry product search</button>}</div>
  </div>;
}
