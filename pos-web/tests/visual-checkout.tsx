import { useEffect, useState, type CSSProperties } from "react";
import { createRoot } from "react-dom/client";
import { applyDiscounts } from "../src/discounts";
import "../src/index.css";
import "../src/theme.css";
import "../src/sales-responsive.css";
import "../src/premium-theme.css";
import PosNavigation from "../src/components/PosNavigation";
import PosSessionHeader from "../src/components/PosSessionHeader";

export function CheckoutPreview() {
  const [quantity, setQuantity] = useState(2);
  const [itemDiscount, setItemDiscount] = useState("");
  const [wholeSaleDiscount, setWholeSaleDiscount] = useState("0");
  const [overflow, setOverflow] = useState(false);
  const [menuOpen, setMenuOpen] = useState(() => new URLSearchParams(location.search).get("menu") === "open" || window.matchMedia("(min-width: 1024px)").matches);
  const cart = [{ id: "fixture-coffee", name: "Fixture Coffee", selling_price: "5.00", stock_qty: "20", quantity: String(quantity), selling_unit: "each", line_total: (quantity * 5).toFixed(2), line_discount: itemDiscount }];
  let error = "";
  let discounted = { items: cart, line_discount_total: "0.00", sale_discount_amount: "0.00", discount_amount: "0.00", total: (quantity * 5).toFixed(2) };
  try { discounted = applyDiscounts(cart, wholeSaleDiscount); } catch (caught) { error = (caught as Error).message; }

  useEffect(() => {
    const check = () => setOverflow(document.documentElement.scrollWidth > document.documentElement.clientWidth);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  });

  return <div className={`pos-sales-shell ${menuOpen ? "pos-navigation-open" : ""}`} style={shell}>
    <PosNavigation open={menuOpen} activeModule="Sales" cashierName="Tariro Moyo" cashierRole="cashier" canManageProducts canManageInventory canManageExpenses canManageCredit onToggle={() => setMenuOpen((open) => !open)} onClose={() => setMenuOpen(false)} onNavigate={() => {}} onBackoffice={() => {}} onLogout={() => {}} />
    <main className="pos-sales-main" style={main}>
      <PosSessionHeader eyebrow="Checkout preview" title="Sales" cashierName="Tariro Moyo" shopName="Harare Central" branchName="Main Floor" shiftStatus="open" actions={<><button className="pos-topbar-action">Switch cashier</button><button className="pos-topbar-action">Log out</button></>} />
      <input className="pos-sales-search" style={search} readOnly value="" placeholder="Search product by name, SKU or barcode..." />
      <div className="pos-sales-product-grid" style={products}><button className="pos-product-card" style={product}><span className="pos-product-visual">FC</span><h3>Fixture Coffee</h3><p>SKU: SAFE-001</p><p>Stock: 20 each</p><h2>$5.00</h2></button><button className="pos-product-card" style={product}><span className="pos-product-visual">FB</span><h3>Fresh Bread</h3><p>SKU: SAFE-002</p><p>Stock: 16 each</p><h2>$2.50</h2></button><button className="pos-product-card" style={product}><span className="pos-product-visual">OJ</span><h3>Orange Juice</h3><p>SKU: SAFE-003</p><p>Stock: 12 each</p><h2>$3.25</h2></button></div>
    </main>
    <aside className="pos-sales-cart" style={cartPanel}>
      <div style={{ padding: "8px 10px", marginBottom: 12, borderRadius: 9, background: overflow ? "#fee2e2" : "#dcfce7", color: overflow ? "#991b1b" : "#166534", fontWeight: 800 }}>{overflow ? "Horizontal overflow detected" : "No page-level horizontal overflow"}</div>
      <h2>Current Sale</h2>
      <div style={{ flex: 1, minHeight: 250, maxHeight: "50vh", overflowY: "auto", overflowX: "hidden" }}>
        <div className="pos-cart-row" style={{ borderBottom: "1px solid #eee", padding: "12px 0" }}>
          <div className="pos-cart-item-summary"><strong>Fixture Coffee</strong><p style={{ margin: "5px 0 0" }}>{quantity} each × $5.00</p><p style={{ margin: "5px 0 0", fontWeight: 700 }}>Item total: ${discounted.items[0].line_total}</p></div>
          <label className="pos-item-discount-field"><span>Item discount</span><input aria-label="Item discount for Fixture Coffee" inputMode="decimal" value={itemDiscount} onChange={(event) => setItemDiscount(event.target.value)} /></label>
          <div className="pos-quantity-control" style={{ display: "flex", gap: 8, alignItems: "center" }}><button onClick={() => setQuantity((value) => Math.max(1, value - 1))}>−</button><strong>{quantity}</strong><button onClick={() => setQuantity((value) => value + 1)}>+</button></div>
          <button className="pos-remove-item" aria-label="Remove Fixture Coffee" style={{ width: 30, background: "#fee2e2", color: "#b91c1c", border: 0, borderRadius: 7 }}>×</button>
        </div>
      </div>
      <label className="pos-whole-sale-discount-field"><span>Whole-sale discount</span><input aria-label="Whole-sale discount" inputMode="decimal" value={wholeSaleDiscount} onChange={(event) => setWholeSaleDiscount(event.target.value)} /></label>
      {error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
      {Number(discounted.line_discount_total) > 0 && <p className="pos-discount-applied">Item discounts applied: −${discounted.line_discount_total}</p>}
      {Number(discounted.sale_discount_amount) > 0 && <p className="pos-discount-applied">Whole-sale discount applied: −${discounted.sale_discount_amount}</p>}
      <div style={{ marginTop: 22, display: "grid", gap: 9 }}><div style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 18 }}><span>{Number(discounted.discount_amount) > 0 ? "Subtotal after discounts" : "Subtotal"}</span><strong>${discounted.total}</strong></div><h1 style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><span>Total:</span><span>${discounted.total}</span></h1></div>
      <div className="pos-payment-grid"><button>Cash</button><button>Card</button><button>Mobile</button><button>Credit</button></div>
      <button style={{ marginTop: 16, minHeight: 50, border: 0, borderRadius: 12, background: "#07583B", color: "white", fontWeight: 800 }}>Pay ${discounted.total}</button>
    </aside>
  </div>;
}

const shell: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 1fr) 420px", minHeight: "100vh", background: "#eef2f7" };
const main: CSSProperties = { minWidth: 0, padding: 28 };
const search: CSSProperties = { width: "100%", padding: 16, borderRadius: 14, border: "1px solid #d1d5db", marginBottom: 22 };
const products: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 18 };
const product: CSSProperties = { background: "white", border: 0, borderRadius: 18, padding: 24, textAlign: "left", boxShadow: "0 8px 22px #0001" };
const cartPanel: CSSProperties = { background: "white", padding: 26, display: "flex", flexDirection: "column" };

createRoot(document.getElementById("root")!).render(<CheckoutPreview />);
