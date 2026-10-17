import { createRoot } from "react-dom/client";
import { useEffect } from "react";
import "../src/index.css";
import "../src/pos-modules.css";
import "../src/premium-theme.css";
import ProductToolsPage, { type ProductToolFeature } from "../src/ProductToolsPage";
import PosSessionHeader from "../src/components/PosSessionHeader";
import { api } from "../src/api/client";

const categories = [
  { id: "cat-drinks", name: "Beverages", parent_id: null, image_url: null, active: true },
  { id: "cat-cold", name: "Cold Drinks", parent_id: "cat-drinks", image_url: null, active: true },
  { id: "cat-food", name: "Prepared Food", parent_id: null, image_url: null, active: true },
];

const products = [
  { id: "burger", name: "Classic Burger", sku: "CMP-001", barcode: "600100001", category_id: "cat-food", product_type: "composite", unit: "each", purchase_unit: null, units_per_purchase: "1", track_inventory: true, cost_price: "2.65", selling_price: "6.50" },
  { id: "bun", name: "Burger Bun", sku: "ING-001", barcode: "600100002", category_id: "cat-food", product_type: "standard", unit: "each", purchase_unit: "crate", units_per_purchase: "48", track_inventory: true, cost_price: "0.45", selling_price: "1.00" },
  { id: "patty", name: "Beef Patty", sku: "ING-002", barcode: "600100003", category_id: "cat-food", product_type: "standard", unit: "each", purchase_unit: "carton", units_per_purchase: "24", track_inventory: true, cost_price: "1.80", selling_price: "3.25" },
  { id: "sauce", name: "House Sauce", sku: "ING-003", barcode: "600100004", category_id: "cat-food", product_type: "standard", unit: "ml", purchase_unit: "litre", units_per_purchase: "1000", track_inventory: true, cost_price: "0.01", selling_price: "0.03" },
];

api.defaults.adapter = async (config) => {
  const url = config.url || "";
  let data: unknown = [];
  if (url.includes("/products/categories/")) data = categories;
  else if (url.includes("/products/components/")) data = [
    { component_product_id: "bun", component_name: "Burger Bun", quantity: "1", unit: "each", component_cost: "0.45", total_cost: "0.45" },
    { component_product_id: "patty", component_name: "Beef Patty", quantity: "1", unit: "each", component_cost: "1.80", total_cost: "1.80" },
    { component_product_id: "sauce", component_name: "House Sauce", quantity: "40", unit: "ml", component_cost: "0.01", total_cost: "0.40" },
  ];
  else if (url.includes("/products/variants/")) data = [{ id: "v1", name: "Large", sku: "BURGER-L", barcode: "600100010", active: true }];
  else if (url.includes("/products/price-levels/")) data = [{ id: "p1", name: "Wholesale", price: "5.80", minimum_quantity: "10", active: true }];
  else if (url.includes("/products/")) data = products;
  return { data, status: 200, statusText: "OK", headers: {}, config };
};

const requested = new URLSearchParams(location.search).get("feature") || "categories";
const feature = requested as ProductToolFeature;

function Preview() {
  useEffect(() => {
    if (!["composite-products", "product-variants", "units", "price-levels", "barcode-labels"].includes(feature)) return;
    const timer = window.setTimeout(() => {
      const select = document.querySelector<HTMLSelectElement>(".pos-product-picker select");
      if (!select) return;
      select.value = feature === "composite-products" ? "burger" : feature === "units" ? "bun" : "burger";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }, 250);
    return () => clearTimeout(timer);
  }, []);

  const title = feature === "composite-products" ? "Composite Products" : feature === "categories" ? "Categories" : "Product Management";
  return <main className="pos-module-overlay" style={{ position: "relative", inset: 0, minHeight: "100vh" }}>
    <section className="pos-module-container">
      <PosSessionHeader title={title} cashierName="Tariro Moyo" shopName="Harare Central" branchName="Main Floor" shiftStatus="open" />
      <button className="pos-feature-back" type="button">← Products</button>
      <ProductToolsPage feature={feature} companyId="fixture-company" branchId="fixture-branch" canManage />
    </section>
  </main>;
}

createRoot(document.getElementById("root")!).render(<Preview />);
