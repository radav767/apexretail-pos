import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import "./products.css";

type Category = {
  id: string;
  company_id: string;
  name: string;
  parent_id: string | null;
  image_url: string | null;
  active: boolean;
};

type Product = {
  id: string;
  company_id: string;
  category_id: string | null;
  name: string;
  sku: string | null;
  barcode: string | null;
  product_type: string;
  image_url: string | null;
  unit: string;
  purchase_unit: string | null;
  units_per_purchase: string;
  track_inventory: boolean;
  tax_rate: string | null;
  tax_exempt: boolean;
  cost_price: string | null;
  selling_price: string | null;
  stock_qty: string;
  reorder_level: string;
  active: boolean;
};

type Branch = {
  id: string;
  shop_id: string;
  shop_name: string;
  name: string;
};

type ProductForm = {
  branch_id: string;
  create_request_key: string;
  name: string;
  category_id: string;
  sku: string;
  barcode: string;
  product_type: string;
  image_url: string;
  unit: string;
  purchase_unit: string;
  units_per_purchase: string;
  track_inventory: boolean;
  tax_rate: string;
  tax_exempt: boolean;
  cost_price: string;
  selling_price: string;
  stock_qty: string;
  reorder_level: string;
};

const emptyForm: ProductForm = {
  branch_id: "",
  create_request_key: "",
  name: "",
  category_id: "",
  sku: "",
  barcode: "",
  product_type: "standard",
  image_url: "",
  unit: "each",
  purchase_unit: "",
  units_per_purchase: "1",
  track_inventory: true,
  tax_rate: "",
  tax_exempt: false,
  cost_price: "",
  selling_price: "",
  stock_qty: "0",
  reorder_level: "0",
};

type ProductFeature =
  | "home" | "all-products" | "categories" | "composites" | "variants"
  | "units" | "price-levels" | "barcode-labels" | "import-export";

type ComponentRow = {
  component_product_id: string;
  component_name: string;
  quantity: string;
  unit: string;
  component_cost: string;
  total_cost: string;
};

type VariantRow = {
  id: string;
  product_id: string;
  name: string;
  sku: string | null;
  barcode: string | null;
  attributes: Record<string, string>;
  selling_price: string | null;
  active: boolean;
};

type PriceLevelRow = {
  id: string;
  product_id: string;
  name: string;
  price: string;
  minimum_quantity: string;
  active: boolean;
};

function featureFromLocation(): ProductFeature {
  const feature = new URLSearchParams(window.location.search).get("feature") as ProductFeature | null;
  return feature && ["all-products", "categories", "composites", "variants", "units", "price-levels", "barcode-labels", "import-export"].includes(feature)
    ? feature
    : "home";
}

export default function ProductsPage({
  companyId,
  onDataChanged,
}: {
  companyId: string;
  onDataChanged?: () => void;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);

  const [form, setForm] = useState<ProductForm>(emptyForm);
  const [editingProductId, setEditingProductId] = useState<string | null>(
    null,
  );

  const [categoryName, setCategoryName] = useState("");
  const [categoryParentId, setCategoryParentId] = useState("");
  const [categoryImageUrl, setCategoryImageUrl] = useState("");
  const [categorySearch, setCategorySearch] = useState("");
  const [editingCategoryId, setEditingCategoryId] = useState<
    string | null
  >(null);

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeFeature, setActiveFeature] = useState<ProductFeature>(() => featureFromLocation());
  const [selectedAdvancedProductId, setSelectedAdvancedProductId] = useState("");
  const [components, setComponents] = useState<ComponentRow[]>([]);
  const [componentProductId, setComponentProductId] = useState("");
  const [componentQuantity, setComponentQuantity] = useState("1");
  const [variants, setVariants] = useState<VariantRow[]>([]);
  const [variantName, setVariantName] = useState("");
  const [variantSku, setVariantSku] = useState("");
  const [variantBarcode, setVariantBarcode] = useState("");
  const [priceLevels, setPriceLevels] = useState<PriceLevelRow[]>([]);
  const [priceName, setPriceName] = useState("");
  const [priceValue, setPriceValue] = useState("");
  const [priceMinimum, setPriceMinimum] = useState("1");

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();

    return products.filter((product) => {
      const matchesText =
        product.name.toLowerCase().includes(query) ||
        (product.sku || "").toLowerCase().includes(query) ||
        (product.barcode || "").toLowerCase().includes(query);

      const matchesCategory =
        !categoryFilter || product.category_id === categoryFilter;

      return matchesText && matchesCategory;
    });
  }, [products, search, categoryFilter]);

  const filteredCategories = useMemo(() => {
    const query = categorySearch.trim().toLowerCase();
    return categories.filter((category) => category.name.toLowerCase().includes(query));
  }, [categories, categorySearch]);

  const loadData = useCallback(async () => {
    if (!companyId) return;

    try {
      setLoading(true);
      setMessage("");

      const [
        productsResponse,
        categoriesResponse,
        branchesResponse,
      ] = await Promise.all([
        api.get(`/products/${companyId}`),
        api.get(`/products/categories/${companyId}`),
        api.get(`/inventory/branches/${companyId}`),
      ]);

      setProducts(productsResponse.data);
      setCategories(categoriesResponse.data);
      setBranches(branchesResponse.data);
      setForm((current) => ({
        ...current,
        branch_id:
          current.branch_id ||
          branchesResponse.data[0]?.id ||
          "",
      }));
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to load products and categories",
      );
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  function updateForm(field: keyof ProductForm, value: string) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function openFeature(feature: ProductFeature) {
    setActiveFeature(feature);
    const url = new URL(window.location.href);
    if (feature === "home") url.searchParams.delete("feature");
    else url.searchParams.set("feature", feature);
    window.history.pushState(null, "", url);
  }

  function resetProductForm() {
    setForm((current) => ({
      ...emptyForm,
      branch_id: current.branch_id || branches[0]?.id || "",
    }));
    setEditingProductId(null);
  }

  function startEditingProduct(product: Product) {
    setEditingProductId(product.id);

    setForm({
      name: product.name,
      branch_id: form.branch_id || branches[0]?.id || "",
      create_request_key: "",
      category_id: product.category_id || "",
      sku: product.sku || "",
      barcode: product.barcode || "",
      product_type: product.product_type || "standard",
      image_url: product.image_url || "",
      unit: product.unit,
      purchase_unit: product.purchase_unit || "",
      units_per_purchase: product.units_per_purchase || "1",
      track_inventory: product.track_inventory !== false,
      tax_rate: product.tax_rate ?? "",
      tax_exempt: Boolean(product.tax_exempt),
      cost_price: product.cost_price ?? "",
      selling_price: product.selling_price ?? "",
      stock_qty: product.stock_qty,
      reorder_level: product.reorder_level,
    });

    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  }

  async function saveProduct() {
    if (!form.name.trim()) {
      setMessage("Product name is required");
      return;
    }

    if (!editingProductId && !form.branch_id) {
      setMessage("Select the branch for opening stock");
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      const payload = {
        category_id: form.category_id || null,
        name: form.name.trim(),
        sku: form.sku.trim() || null,
        barcode: form.barcode.trim() || null,
        product_type: form.product_type,
        image_url: form.image_url.trim() || null,
        unit: form.unit,
        purchase_unit: form.purchase_unit.trim() || null,
        units_per_purchase: form.units_per_purchase || "1",
        track_inventory: form.track_inventory,
        tax_rate: form.tax_rate || null,
        tax_exempt: form.tax_exempt,
        cost_price: form.cost_price || null,
        selling_price: form.selling_price || null,
        reorder_level: form.reorder_level || "0",
      };

      if (editingProductId) {
        await api.patch(
          `/products/${companyId}/${editingProductId}`,
          payload,
        );

        setMessage("Product updated successfully");
      } else {
        const createRequestKey =
          form.create_request_key ||
          globalThis.crypto?.randomUUID?.() ||
          `product-${Date.now()}-${Math.random()
            .toString(36)
            .slice(2)}`;

        if (createRequestKey !== form.create_request_key) {
          updateForm(
            "create_request_key",
            createRequestKey,
          );
        }

        await api.post("/products", {
          company_id: companyId,
          branch_id: form.branch_id || null,
          create_request_key: createRequestKey,
          ...payload,
          stock_qty: form.stock_qty || "0",
        });

        setMessage("Product created successfully");
      }

      resetProductForm();
      await loadData();
      onDataChanged?.();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail || "Failed to save product",
      );
    } finally {
      setLoading(false);
    }
  }

  async function deleteProduct(product: Product) {
    const confirmed = window.confirm(
      `Remove "${product.name}" from active products?`,
    );

    if (!confirmed) return;

    try {
      setLoading(true);

      await api.delete(`/products/${companyId}/${product.id}`);

      setMessage("Product deleted successfully");

      if (editingProductId === product.id) {
        resetProductForm();
      }

      await loadData();
      onDataChanged?.();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail || "Failed to delete product",
      );
    } finally {
      setLoading(false);
    }
  }

  function startEditingCategory(category: Category) {
    setEditingCategoryId(category.id);
    setCategoryName(category.name);
    setCategoryParentId(category.parent_id || "");
    setCategoryImageUrl(category.image_url || "");
  }

  function resetCategoryForm() {
    setEditingCategoryId(null);
    setCategoryName("");
    setCategoryParentId("");
    setCategoryImageUrl("");
  }

  async function saveCategory() {
    const name = categoryName.trim();

    if (!name) {
      setMessage("Category name is required");
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      if (editingCategoryId) {
        await api.patch(
          `/products/categories/${companyId}/${editingCategoryId}`,
          {
            name,
            parent_id: categoryParentId || null,
            image_url: categoryImageUrl.trim() || null,
          },
        );

        setMessage("Category updated successfully");
      } else {
        await api.post("/products/categories", {
          company_id: companyId,
          name,
          parent_id: categoryParentId || null,
          image_url: categoryImageUrl.trim() || null,
        });

        setMessage("Category created successfully");
      }

      resetCategoryForm();
      await loadData();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail || "Failed to save category",
      );
    } finally {
      setLoading(false);
    }
  }

  async function deleteCategory(category: Category) {
    const confirmed = window.confirm(
      `Delete category "${category.name}"? Deletion is blocked while products or child categories depend on it.`,
    );

    if (!confirmed) return;

    try {
      setLoading(true);

      await api.delete(
        `/products/categories/${companyId}/${category.id}`,
      );

      if (categoryFilter === category.id) {
        setCategoryFilter("");
      }

      if (editingCategoryId === category.id) {
        resetCategoryForm();
      }

      setMessage("Category deleted successfully");
      await loadData();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail || "Failed to delete category",
      );
    } finally {
      setLoading(false);
    }
  }

  function categoryNameFor(product: Product) {
    if (!product.category_id) return "Uncategorized";

    return (
      categories.find(
        (category) => category.id === product.category_id,
      )?.name || "Unknown"
    );
  }

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    const sync = () => setActiveFeature(featureFromLocation());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  useEffect(() => {
    if (!selectedAdvancedProductId) {
      setComponents([]);
      return;
    }
    if (activeFeature === "composites") {
      void api.get(`/products/components/${companyId}/${selectedAdvancedProductId}`)
        .then((response) => setComponents(response.data))
        .catch((error: any) => setMessage(error.response?.data?.detail || "Failed to load components"));
    }
    if (activeFeature === "variants") {
      void api.get(`/products/variants/${companyId}`, { params: { product_id: selectedAdvancedProductId } })
        .then((response) => setVariants(response.data))
        .catch((error: any) => setMessage(error.response?.data?.detail || "Failed to load variants"));
    }
    if (activeFeature === "price-levels") {
      void api.get(`/products/price-levels/${companyId}`, { params: { product_id: selectedAdvancedProductId } })
        .then((response) => setPriceLevels(response.data))
        .catch((error: any) => setMessage(error.response?.data?.detail || "Failed to load price levels"));
    }
  }, [activeFeature, companyId, selectedAdvancedProductId]);

  function addComponentDraft() {
    const product = products.find((item) => item.id === componentProductId);
    if (!product || Number(componentQuantity) <= 0) return;
    setComponents((current) => [
      ...current.filter((item) => item.component_product_id !== product.id),
      {
        component_product_id: product.id,
        component_name: product.name,
        quantity: componentQuantity,
        unit: product.unit,
        component_cost: product.cost_price || "0",
        total_cost: String(Number(product.cost_price || 0) * Number(componentQuantity)),
      },
    ]);
    setComponentProductId("");
    setComponentQuantity("1");
  }

  async function saveComponents() {
    if (!selectedAdvancedProductId || !components.length) return;
    try {
      setLoading(true);
      const response = await api.put(`/products/components/${companyId}/${selectedAdvancedProductId}`, components.map((item) => ({
        component_product_id: item.component_product_id,
        quantity: item.quantity,
        unit: item.unit,
      })));
      setComponents(response.data);
      setMessage("Composite recipe saved");
      await loadData();
    } catch (error: any) {
      setMessage(error.response?.data?.detail || "Failed to save composite recipe");
    } finally { setLoading(false); }
  }

  async function createVariant() {
    if (!selectedAdvancedProductId || !variantName.trim()) return;
    try {
      await api.post(`/products/variants/${companyId}/${selectedAdvancedProductId}`, {
        name: variantName.trim(), sku: variantSku.trim() || null,
        barcode: variantBarcode.trim() || null, attributes: {},
      });
      setVariantName(""); setVariantSku(""); setVariantBarcode("");
      const response = await api.get(`/products/variants/${companyId}`, { params: { product_id: selectedAdvancedProductId } });
      setVariants(response.data); setMessage("Variant created");
    } catch (error: any) { setMessage(error.response?.data?.detail || "Failed to create variant"); }
  }

  async function createPriceLevel() {
    if (!selectedAdvancedProductId || !priceName.trim() || priceValue === "") return;
    try {
      await api.post(`/products/price-levels/${companyId}/${selectedAdvancedProductId}`, {
        name: priceName.trim(), price: priceValue, minimum_quantity: priceMinimum || "1",
      });
      setPriceName(""); setPriceValue(""); setPriceMinimum("1");
      const response = await api.get(`/products/price-levels/${companyId}`, { params: { product_id: selectedAdvancedProductId } });
      setPriceLevels(response.data); setMessage("Price level created");
    } catch (error: any) { setMessage(error.response?.data?.detail || "Failed to create price level"); }
  }

  async function exportProducts() {
    const response = await api.get(`/products/export/${companyId}`, { responseType: "blob" });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "products.csv"; anchor.click();
    URL.revokeObjectURL(url);
  }

  async function importProducts(file: File) {
    const lines = (await file.text()).split(/\r?\n/).filter(Boolean);
    if (lines.length < 2) return;
    const headers = lines[0].split(",").map((value) => value.trim());
    const rows = lines.slice(1).map((line) => {
      const values = line.split(",").map((value) => value.trim());
      const record = Object.fromEntries(headers.map((header, index) => [header, values[index] || null]));
      return { ...record, reorder_level: record.reorder_level || "0" };
    });
    try {
      await api.post("/products/import", { company_id: companyId, branch_id: form.branch_id || branches[0]?.id || null, rows });
      setMessage(`${rows.length} products imported`); await loadData();
    } catch (error: any) { setMessage(error.response?.data?.detail || "Product import failed"); }
  }

  return (
    <div className="products-page">
      {activeFeature === "home" && (
        <section className="product-feature-card">
          <div className="product-feature-grid">
            {[
              ["all-products", "All Products", "Products, pricing and stock", "▣"],
              ["categories", "Categories", "Hierarchy and assignments", "⌘"],
              ["composites", "Composite Products", "Recipes and calculated cost", "◇"],
              ["variants", "Product Variants", "SKU and barcode options", "⌗"],
              ["units", "Units", "Bulk purchasing and case breaking", "⇄"],
              ["price-levels", "Price Levels", "Quantity and customer pricing", "$"],
              ["barcode-labels", "Barcode Labels", "Printable product labels", "▥"],
              ["import-export", "Import / Export", "Portable product records", "⇅"],
            ].map(([id, title, detail, icon]) => (
              <button key={id} type="button" onClick={() => openFeature(id as ProductFeature)}>
                <span className="product-feature-icon">{icon}</span>
                <span><strong>{title}</strong><small>{detail}</small></span>
              </button>
            ))}
          </div>
        </section>
      )}

      {activeFeature !== "home" && (
        <button type="button" className="product-feature-back" onClick={() => openFeature("home")}>← Back to Products</button>
      )}

      {(activeFeature === "all-products" || activeFeature === "categories") && <section className="products-form-grid single-feature">
        {activeFeature === "all-products" && <article className="product-management-card">
          <div className="management-card-header">
            <div>
              <h2>
                {editingProductId ? "Edit Product" : "Add Product"}
              </h2>

              <p>
                Products saved here use the same database as the POS.
              </p>
            </div>

            {editingProductId && (
              <button
                className="cancel-edit-button"
                onClick={resetProductForm}
              >
                Cancel edit
              </button>
            )}
          </div>

          <div className="product-form">
            <label>
              Opening stock branch
              <select
                value={form.branch_id}
                onChange={(event) =>
                  updateForm("branch_id", event.target.value)
                }
                disabled={Boolean(editingProductId)}
              >
                <option value="">Select branch</option>

                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.shop_name} — {branch.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Product name
              <input
                value={form.name}
                placeholder="Example: Coca Cola 500ml"
                onChange={(event) =>
                  updateForm("name", event.target.value)
                }
              />
            </label>

            <label>
              Category
              <select
                value={form.category_id}
                onChange={(event) =>
                  updateForm("category_id", event.target.value)
                }
              >
                <option value="">Uncategorized</option>

                {categories
                  .filter((category) => category.active)
                  .map((category) => (
                    <option
                      key={category.id}
                      value={category.id}
                    >
                      {category.name}
                    </option>
                  ))}
              </select>
            </label>

            <label>
              SKU
              <input
                value={form.sku}
                placeholder="Optional"
                onChange={(event) =>
                  updateForm("sku", event.target.value)
                }
              />
            </label>

            <label>
              Product type
              <select value={form.product_type} onChange={(event) => updateForm("product_type", event.target.value)}>
                <option value="standard">Standard stock</option>
                <option value="non_stock">Non-stock</option>
                <option value="service">Service</option>
                <option value="composite">Composite</option>
                <option value="bundle">Bundle</option>
                <option value="variable_weight">Variable weight</option>
              </select>
            </label>

            <label>
              Product image URL
              <input value={form.image_url} placeholder="Optional HTTPS image" onChange={(event) => updateForm("image_url", event.target.value)} />
            </label>

            <label>
              Barcode
              <input
                value={form.barcode}
                placeholder="Optional"
                onChange={(event) =>
                  updateForm("barcode", event.target.value)
                }
              />
            </label>

            <label>
              Sold by
              <select
                value={form.unit}
                onChange={(event) =>
                  updateForm("unit", event.target.value)
                }
              >
                <option value="each">Each</option>
                <option value="kg">Kilogram</option>
                <option value="litre">Litre</option>
                <option value="ml">Millilitre</option>
                <option value="g">Gram</option>
              </select>
            </label>

            <label>
              Purchase unit
              <input value={form.purchase_unit} placeholder="Example: carton" onChange={(event) => updateForm("purchase_unit", event.target.value)} />
            </label>

            <label>
              Units per purchase unit
              <input type="number" min="0.001" step="0.001" value={form.units_per_purchase} onChange={(event) => updateForm("units_per_purchase", event.target.value)} />
            </label>

            <label>
              Product tax rate (%)
              <input type="number" min="0" max="100" step="0.01" value={form.tax_rate} disabled={form.tax_exempt} onChange={(event) => updateForm("tax_rate", event.target.value)} />
            </label>

            <label className="product-checkbox-field">
              <input type="checkbox" checked={form.tax_exempt} onChange={(event) => setForm((current) => ({ ...current, tax_exempt: event.target.checked }))} />
              Tax exempt
            </label>

            <label>
              Cost price
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.cost_price}
                onChange={(event) =>
                  updateForm("cost_price", event.target.value)
                }
              />
            </label>

            <label>
              Selling price
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.selling_price}
                onChange={(event) =>
                  updateForm("selling_price", event.target.value)
                }
              />
              <small>
                {form.unit === "kg"
                  ? "For kg items, this is the price per kilogram."
                  : "Selling price per unit."}
              </small>
            </label>

            <label>
              Opening stock
              <input
                type="number"
                min="0"
                step={form.unit === "each" ? "1" : "0.001"}
                value={form.stock_qty}
                disabled={Boolean(editingProductId)}
                onChange={(event) =>
                  updateForm("stock_qty", event.target.value)
                }
              />
              {editingProductId && (
                <small>
                  Use Inventory Management to change stock quantities.
                </small>
              )}
            </label>

            <label>
              Reorder level
              <input
                type="number"
                min="0"
                step={form.unit === "each" ? "1" : "0.001"}
                value={form.reorder_level}
                onChange={(event) =>
                  updateForm("reorder_level", event.target.value)
                }
              />
            </label>
          </div>

          <button
            className="save-product-button"
            onClick={saveProduct}
            disabled={loading}
          >
            {loading
              ? "Saving..."
              : editingProductId
                ? "Update Product"
                : "Create Product"}
          </button>
        </article>}

        {activeFeature === "categories" && <article className="product-management-card">
          <div className="management-card-header">
            <div>
              <h2>Categories</h2>
            </div>
          </div>

          <div className="category-entry">
            <input
              value={categoryName}
              placeholder="Category name"
              onChange={(event) =>
                setCategoryName(event.target.value)
              }
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void saveCategory();
                }
              }}
            />

            <button onClick={saveCategory} disabled={loading}>
              {editingCategoryId ? "Update" : "Add"}
            </button>
          </div>

          <div className="category-meta-grid">
            <label>Parent category
              <select value={categoryParentId} onChange={(event) => setCategoryParentId(event.target.value)}>
                <option value="">Top level</option>
                {categories.filter((item) => item.id !== editingCategoryId).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            <label>Image URL
              <input value={categoryImageUrl} onChange={(event) => setCategoryImageUrl(event.target.value)} placeholder="Optional HTTPS image" />
            </label>
          </div>

          <input className="category-search" value={categorySearch} onChange={(event) => setCategorySearch(event.target.value)} placeholder="Search categories" />

          {editingCategoryId && (
            <button
              className="cancel-category-edit"
              onClick={resetCategoryForm}
            >
              Cancel category edit
            </button>
          )}

          <div className="category-list">
            {!categories.length && (
              <p className="empty-products-message">
                No categories created yet.
              </p>
            )}

            {filteredCategories.map((category) => (
              <div className="category-row" key={category.id}>
                <div>
                  <strong>{category.name}</strong>
                  <span>
                    {category.active ? "Active" : "Inactive"}
                  </span>
                </div>

                <div className="category-actions">
                  <button
                    onClick={() =>
                      startEditingCategory(category)
                    }
                  >
                    Edit
                  </button>

                  <button
                    className="danger-action"
                    onClick={() =>
                      void deleteCategory(category)
                    }
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </article>}
      </section>}

      {activeFeature === "all-products" && <section className="product-management-card product-list-card">
        <div className="products-list-header">
          <div>
            <h2>Product List</h2>
            <p>
              {filteredProducts.length} of {products.length} products
            </p>
          </div>

          <button onClick={loadData} disabled={loading}>
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        <div className="products-filters">
          <input
            value={search}
            placeholder="Search name, SKU or barcode..."
            onChange={(event) => setSearch(event.target.value)}
          />

          <select
            value={categoryFilter}
            onChange={(event) =>
              setCategoryFilter(event.target.value)
            }
          >
            <option value="">All categories</option>

            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </div>

        {!filteredProducts.length ? (
          <div className="empty-products-message">
            No matching products found.
          </div>
        ) : (
          <div className="products-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Category</th>
                  <th>SKU</th>
                  <th>Unit</th>
                  <th>Cost</th>
                  <th>Selling</th>
                  <th>Stock</th>
                  <th>Reorder</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {filteredProducts.map((product) => (
                  <tr key={product.id}>
                    <td>
                      <strong>{product.name}</strong>
                      <small className="product-barcode">
                        {product.barcode || "No barcode"}
                      </small>
                    </td>

                    <td>{categoryNameFor(product)}</td>
                    <td>{product.sku || "—"}</td>
                    <td>{product.unit}</td>

                    <td>
                      {product.cost_price == null
                        ? "Unavailable"
                        : `$${Number(product.cost_price).toFixed(2)}`}
                    </td>

                    <td>
                      {product.selling_price == null
                        ? "Unavailable"
                        : `$${Number(product.selling_price).toFixed(2)}`}
                    </td>

                    <td>{Number(product.stock_qty)}</td>
                    <td>{Number(product.reorder_level)}</td>

                    <td>
                      <span
                        className={
                          product.active
                            ? "product-active-badge"
                            : "product-inactive-badge"
                        }
                      >
                        {product.active ? "Active" : "Inactive"}
                      </span>
                    </td>

                    <td>
                      <div className="product-actions">
                        <button
                          onClick={() =>
                            startEditingProduct(product)
                          }
                        >
                          Edit
                        </button>

                        <button
                          className="danger-action"
                          onClick={() =>
                            void deleteProduct(product)
                          }
                        >
                          Archive
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>}

      {["composites", "variants", "units", "price-levels", "barcode-labels"].includes(activeFeature) && (
        <section className="product-management-card product-advanced-page">
          <div className="management-card-header"><div><h2>{
            activeFeature === "composites" ? "Composite Products" : activeFeature === "variants" ? "Product Variants" :
            activeFeature === "units" ? "Units & Case Breaking" : activeFeature === "price-levels" ? "Price Levels" : "Barcode Labels"
          }</h2></div></div>
          <label className="advanced-product-picker">Product
            <select value={selectedAdvancedProductId} onChange={(event) => setSelectedAdvancedProductId(event.target.value)}>
              <option value="">Select product</option>
              {products.filter((product) => activeFeature !== "composites" || ["composite", "bundle"].includes(product.product_type)).map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
            </select>
          </label>

          {activeFeature === "composites" && selectedAdvancedProductId && <>
            <div className="advanced-inline-form">
              <select value={componentProductId} onChange={(event) => setComponentProductId(event.target.value)}><option value="">Component product</option>{products.filter((product) => product.id !== selectedAdvancedProductId && product.track_inventory && !["composite", "bundle"].includes(product.product_type)).map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select>
              <input type="number" min="0.001" step="0.001" value={componentQuantity} onChange={(event) => setComponentQuantity(event.target.value)} />
              <button type="button" onClick={addComponentDraft}>Add component</button>
            </div>
            <div className="products-table-wrapper"><table><thead><tr><th>Component</th><th>Quantity</th><th>Unit</th><th>Unit cost</th><th>Total cost</th><th /></tr></thead><tbody>{components.map((item) => <tr key={item.component_product_id}><td>{item.component_name}</td><td>{item.quantity}</td><td>{item.unit}</td><td>{Number(item.component_cost).toFixed(2)}</td><td>{Number(item.total_cost).toFixed(2)}</td><td><button className="danger-action" onClick={() => setComponents((current) => current.filter((row) => row.component_product_id !== item.component_product_id))}>Remove</button></td></tr>)}</tbody></table></div>
            <button className="save-product-button" type="button" onClick={() => void saveComponents()} disabled={!components.length || loading}>Save Recipe</button>
          </>}

          {activeFeature === "variants" && selectedAdvancedProductId && <>
            <div className="advanced-inline-form"><input placeholder="Variant name" value={variantName} onChange={(event) => setVariantName(event.target.value)} /><input placeholder="SKU" value={variantSku} onChange={(event) => setVariantSku(event.target.value)} /><input placeholder="Barcode" value={variantBarcode} onChange={(event) => setVariantBarcode(event.target.value)} /><button onClick={() => void createVariant()}>Add variant</button></div>
            <div className="products-table-wrapper"><table><thead><tr><th>Variant</th><th>SKU</th><th>Barcode</th><th>Status</th></tr></thead><tbody>{variants.map((item) => <tr key={item.id}><td>{item.name}</td><td>{item.sku || "—"}</td><td>{item.barcode || "—"}</td><td>{item.active ? "Active" : "Inactive"}</td></tr>)}</tbody></table></div>
          </>}

          {activeFeature === "units" && selectedAdvancedProductId && (() => { const product = products.find((item) => item.id === selectedAdvancedProductId); return product ? <div className="unit-conversion-card"><strong>1 {product.purchase_unit || product.unit}</strong><span>=</span><strong>{product.units_per_purchase} {product.unit}</strong><button onClick={() => { startEditingProduct(product); openFeature("all-products"); }}>Edit conversion</button></div> : null; })()}

          {activeFeature === "price-levels" && selectedAdvancedProductId && <>
            <div className="advanced-inline-form"><input placeholder="Level name" value={priceName} onChange={(event) => setPriceName(event.target.value)} /><input type="number" min="0" step="0.01" placeholder="Price" value={priceValue} onChange={(event) => setPriceValue(event.target.value)} /><input type="number" min="0.001" step="0.001" placeholder="Minimum quantity" value={priceMinimum} onChange={(event) => setPriceMinimum(event.target.value)} /><button onClick={() => void createPriceLevel()}>Add price</button></div>
            <div className="products-table-wrapper"><table><thead><tr><th>Level</th><th>Price</th><th>Minimum quantity</th><th>Status</th></tr></thead><tbody>{priceLevels.map((item) => <tr key={item.id}><td>{item.name}</td><td>{Number(item.price).toFixed(2)}</td><td>{item.minimum_quantity}</td><td>{item.active ? "Active" : "Inactive"}</td></tr>)}</tbody></table></div>
          </>}

          {activeFeature === "barcode-labels" && <div className="barcode-label-grid">{products.filter((item) => !selectedAdvancedProductId || item.id === selectedAdvancedProductId).map((item) => <article key={item.id}><strong>{item.name}</strong><span>{item.barcode || item.sku}</span><small>{item.selling_price == null ? "" : `$${Number(item.selling_price).toFixed(2)}`}</small></article>)}<button className="save-product-button" onClick={() => window.print()}>Print Labels</button></div>}
        </section>
      )}

      {activeFeature === "import-export" && <section className="product-management-card import-export-page">
        <h2>Import / Export</h2>
        <div className="import-export-actions"><label>Import CSV<input type="file" accept=".csv,text/csv" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importProducts(file); }} /></label><button type="button" onClick={() => void exportProducts()}>Export CSV</button></div>
      </section>}

      <p className="products-message">{message}</p>
    </div>
  );
}
