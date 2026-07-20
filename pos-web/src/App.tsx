import { useEffect, useMemo, useState } from "react";
import { api } from "./api/client";

type Product = {
  id: string;
  name: string;
  sku?: string;
  barcode?: string;
  selling_price: string;
  stock_qty: string;
};

type CartItem = Product & { qty: number };

function App() {
  const [email, setEmail] = useState("owner001@example.com");
  const [password, setPassword] = useState("12345678");
  const [companyId, setCompanyId] = useState(localStorage.getItem("company_id") || "");
  const [loggedIn, setLoggedIn] = useState(!!localStorage.getItem("token"));
  const [products, setProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [search, setSearch] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [message, setMessage] = useState("");

  const filteredProducts = useMemo(() => {
    const q = search.toLowerCase();
    return products.filter(p =>
      p.name.toLowerCase().includes(q) ||
      (p.sku || "").toLowerCase().includes(q) ||
      (p.barcode || "").toLowerCase().includes(q)
    );
  }, [products, search]);

  const total = cart.reduce((sum, item) => sum + Number(item.selling_price) * item.qty, 0);

  async function loadProducts(cid = companyId) {
    if (!cid) return;
    const res = await api.get(`/products/${cid}`);
    setProducts(res.data);
  }

  async function login() {
    try {
      const res = await api.post("/auth/login", { email, password });
      localStorage.setItem("token", res.data.token);
      localStorage.setItem("company_id", res.data.company_id);
      setCompanyId(res.data.company_id);
      setLoggedIn(true);
      await loadProducts(res.data.company_id);
    } catch {
      setMessage("Login failed");
    }
  }

  function addToCart(product: Product) {
    const stock = Number(product.stock_qty);
    const existingQty = cart.find(i => i.id === product.id)?.qty || 0;
    if (existingQty >= stock) return;

    setCart(prev => {
      const found = prev.find(i => i.id === product.id);
      if (found) return prev.map(i => i.id === product.id ? { ...i, qty: i.qty + 1 } : i);
      return [...prev, { ...product, qty: 1 }];
    });
  }

  function changeQty(id: string, diff: number) {
    setCart(prev => prev
      .map(i => i.id === id ? { ...i, qty: Math.max(1, i.qty + diff) } : i)
    );
  }

  function removeFromCart(id: string) {
    setCart(prev => prev.filter(i => i.id !== id));
  }

  async function completeSale() {
    if (!cart.length) return;

    try {
      await api.post("/sales", {
        company_id: companyId,
        payment_method: paymentMethod,
        items: cart.map(i => ({ product_id: i.id, quantity: i.qty })),
      });

      setCart([]);
      setMessage("Sale completed successfully");
      await loadProducts(companyId);
    } catch (e: any) {
      setMessage(e.response?.data?.detail || "Sale failed");
    }
  }

  function logout() {
    localStorage.clear();
    setLoggedIn(false);
    setProducts([]);
    setCart([]);
  }

  useEffect(() => {
    if (loggedIn && companyId) loadProducts(companyId);
  }, []);

  if (!loggedIn) {
    return (
      <div style={pageCenter}>
        <div style={loginCard}>
          <h1 style={brand}>ApexRetail POS</h1>
          <p style={{ textAlign: "center" }}>Sign in to your shop</p>
          <input style={input} value={email} onChange={e => setEmail(e.target.value)} />
          <input style={input} type="password" value={password} onChange={e => setPassword(e.target.value)} />
          <button style={primaryBtn} onClick={login}>Login</button>
          <p style={{ color: "crimson", textAlign: "center" }}>{message}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={appShell}>
      <main style={mainArea}>
        <div style={topBar}>
          <div>
            <h1 style={{ margin: 0 }}>ApexRetail POS</h1>
            <p style={{ marginTop: 4 }}>Sales screen</p>
          </div>
          <button onClick={logout} style={{ ...secondaryBtn, width: 120, marginTop: 0 }}>Logout</button>
        </div>

        <input
          style={searchBox}
          placeholder="Search product by name, SKU or barcode..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />

        <div style={productGrid}>
          {filteredProducts.map(p => (
            <button key={p.id} onClick={() => addToCart(p)} style={productCard}>
              <h3>{p.name}</h3>
              <p>SKU: {p.sku || "-"}</p>
              <p>Stock: {p.stock_qty}</p>
              <h2>${Number(p.selling_price).toFixed(2)}</h2>
            </button>
          ))}
        </div>
      </main>

      <aside style={cartPanel}>
        <h2>Current Sale</h2>

        <div style={{ minHeight: 260 }}>
          {cart.map(item => (
            <div key={item.id} style={cartRow}>
              <div>
                <strong>{item.name}</strong>
                <p>${Number(item.selling_price).toFixed(2)}</p>
              </div>
              <div style={qtyBox}>
                <button onClick={() => changeQty(item.id, -1)}>-</button>
                <span>{item.qty}</span>
                <button onClick={() => changeQty(item.id, 1)}>+</button>
              </div>
              <button onClick={() => removeFromCart(item.id)}>x</button>
            </div>
          ))}
        </div>

        <h1>Total: ${total.toFixed(2)}</h1>

        <div style={payGrid}>
          {["cash", "card", "mobile", "credit"].map(m => (
            <button
              key={m}
              onClick={() => setPaymentMethod(m)}
              style={paymentMethod === m ? activePayBtn : secondaryBtn}
            >
              {m.toUpperCase()}
            </button>
          ))}
        </div>

        <button style={primaryBtn} onClick={completeSale}>Complete Sale</button>
        <button style={secondaryBtn} onClick={() => setCart([])}>Clear Cart</button>

        <p>{message}</p>
      </aside>
    </div>
  );
}

const pageCenter = { minHeight: "100vh", display: "grid", placeItems: "center", background: "#eef2f7" };
const loginCard = { width: 400, background: "white", padding: 34, borderRadius: 22, boxShadow: "0 12px 35px #0002" };
const brand = { textAlign: "center" as const, fontSize: 34, fontWeight: 900 };
const input = { width: "100%", padding: 14, marginTop: 14, boxSizing: "border-box" as const, borderRadius: 10, border: "1px solid #ddd" };
const appShell = { minHeight: "100vh", display: "grid", gridTemplateColumns: "1fr 420px", background: "#eef2f7" };
const mainArea = { padding: 28 };
const topBar = { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 };
const searchBox = { width: "100%", padding: 16, borderRadius: 14, border: "1px solid #ddd", marginBottom: 22, boxSizing: "border-box" as const };
const productGrid = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 18 };
const productCard = { background: "white", border: 0, borderRadius: 18, padding: 24, textAlign: "left" as const, boxShadow: "0 8px 22px #0001", cursor: "pointer" };
const cartPanel = { background: "white", padding: 26, boxShadow: "-6px 0 24px #0001" };
const cartRow = { display: "grid", gridTemplateColumns: "1fr 95px 35px", gap: 8, alignItems: "center", borderBottom: "1px solid #eee", padding: "12px 0" };
const qtyBox = { display: "flex", gap: 8, alignItems: "center", justifyContent: "center" };
const payGrid = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 };
const primaryBtn = { width: "100%", padding: 15, marginTop: 16, background: "#111827", color: "white", border: 0, borderRadius: 12, fontWeight: 800 };
const secondaryBtn = { width: "100%", padding: 13, marginTop: 10, background: "#e5e7eb", color: "#111827", border: 0, borderRadius: 12, fontWeight: 700 };
const activePayBtn = { ...secondaryBtn, background: "#111827", color: "white" };

export default App;
