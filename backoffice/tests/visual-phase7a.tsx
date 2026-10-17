import { createRoot } from "react-dom/client";
import { useEffect } from "react";
import "../src/App.css";
import "../src/theme.css";
import "../src/ui-system.css";
import "../src/premium-theme.css";
import ProductsPage from "../src/pages/ProductsPage";
import { api } from "../src/api/client";

const categories = [
  { id: "cat-drinks", company_id: "fixture-company", name: "Beverages", parent_id: null, image_url: null, active: true },
  { id: "cat-cold", company_id: "fixture-company", name: "Cold Drinks", parent_id: "cat-drinks", image_url: null, active: true },
  { id: "cat-food", company_id: "fixture-company", name: "Prepared Food", parent_id: null, image_url: null, active: true },
];
const product = (id: string, name: string, type: string, unit = "each", purchaseUnit: string | null = null, units = "1", cost = "1.00", price = "2.00") => ({
  id, company_id: "fixture-company", category_id: "cat-food", name, sku: id.toUpperCase(), barcode: `60010${id.length}01`, product_type: type, image_url: null,
  unit, purchase_unit: purchaseUnit, units_per_purchase: units, track_inventory: !["service", "non_stock"].includes(type), tax_rate: "15.00", tax_exempt: false,
  cost_price: cost, selling_price: price, stock_qty: "48", reorder_level: "8", active: true,
});
const products = [
  product("burger", "Classic Burger", "composite", "each", null, "1", "2.65", "6.50"),
  product("bun", "Burger Bun", "standard", "each", "crate", "48", "0.45", "1.00"),
  product("patty", "Beef Patty", "standard", "each", "carton", "24", "1.80", "3.25"),
  product("sauce", "House Sauce", "standard", "ml", "litre", "1000", "0.01", "0.03"),
];

api.defaults.adapter = async (config) => {
  const url = config.url || "";
  let data: unknown = [];
  if (url.includes("/products/categories/")) data = categories;
  else if (url.includes("/inventory/branches/")) data = [{ id: "fixture-branch", shop_id: "fixture-shop", shop_name: "Harare Central", name: "Main Floor" }];
  else if (url.includes("/products/components/")) data = [
    { component_product_id: "bun", component_name: "Burger Bun", quantity: "1", unit: "each", component_cost: "0.45", total_cost: "0.45" },
    { component_product_id: "patty", component_name: "Beef Patty", quantity: "1", unit: "each", component_cost: "1.80", total_cost: "1.80" },
    { component_product_id: "sauce", component_name: "House Sauce", quantity: "40", unit: "ml", component_cost: "0.01", total_cost: "0.40" },
  ];
  else if (url.includes("/products/variants/")) data = [{ id: "v1", product_id: "burger", name: "Large", sku: "BURGER-L", barcode: "600100010", attributes: {}, selling_price: "8.25", active: true }];
  else if (url.includes("/products/price-levels/")) data = [{ id: "p1", product_id: "burger", name: "Wholesale", price: "5.80", minimum_quantity: "10", active: true }];
  else if (url.includes("/products/")) data = products;
  return { data, status: 200, statusText: "OK", headers: {}, config };
};

function Preview() {
  useEffect(() => {
    if (!new URLSearchParams(location.search).has("feature")) return;
    const timer = window.setTimeout(() => {
      const select = document.querySelector<HTMLSelectElement>(".advanced-product-picker select");
      if (!select) return;
      select.value = "burger";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }, 250);
    return () => clearTimeout(timer);
  }, []);
  return <div className="backoffice-shell"><aside className="sidebar"><div className="sidebar-header"><div className="sidebar-brand"><div className="logo-mark small">A</div><div><strong>ApexRetail</strong><span>Backoffice preview</span></div></div></div><nav><button className="active">Products</button><button>Inventory</button><button>Suppliers</button><button>Reports</button><button>Settings</button></nav></aside><main className="content"><header className="topbar"><div><h1>Products</h1><p>Catalog, pricing and product composition</p></div><button className="refresh-button">Refresh</button></header><ProductsPage companyId="fixture-company" /></main></div>;
}

createRoot(document.getElementById("root")!).render(<Preview />);
