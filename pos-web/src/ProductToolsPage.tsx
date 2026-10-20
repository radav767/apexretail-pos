import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, getApiErrorMessage } from "./api/client";

export type ProductToolFeature =
  | "categories" | "composite-products" | "product-variants" | "units"
  | "price-levels" | "barcode-labels" | "import-export";

type Product = {
  id: string; name: string; sku?: string | null; barcode?: string | null;
  category_id?: string | null; product_type: string; unit: string;
  purchase_unit?: string | null; units_per_purchase: string | number;
  track_inventory: boolean; cost_price?: string | number | null;
  selling_price?: string | number | null;
};

type Category = { id: string; name: string; parent_id?: string | null; image_url?: string | null; active: boolean };
type ComponentRow = { component_product_id: string; component_name: string; quantity: string; unit: string; component_cost: string | null; total_cost: string | null };
type VariantRow = { id: string; name: string; sku?: string | null; barcode?: string | null; cost_price?: string | null; selling_price?: string | null; stock_qty?: string; reorder_level?: string; active: boolean };
type PriceRow = { id: string; name: string; price: string; minimum_quantity: string; active: boolean };
type ImportPreviewRow = { row_number: number; values: Record<string, string | null>; errors: string[] };

export default function ProductToolsPage({
  feature, companyId, branchId, canManage, canViewCosts = false, onDataChanged,
}: {
  feature: ProductToolFeature;
  companyId: string;
  branchId: string;
  canManage: boolean;
  canViewCosts?: boolean;
  onDataChanged?: () => void;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [selectedProductId, setSelectedProductId] = useState("");
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [categoryParentId, setCategoryParentId] = useState("");
  const [categoryImageUrl, setCategoryImageUrl] = useState("");
  const [editingCategoryId, setEditingCategoryId] = useState("");
  const [components, setComponents] = useState<ComponentRow[]>([]);
  const [componentProductId, setComponentProductId] = useState("");
  const [componentQuantity, setComponentQuantity] = useState("1");
  const [variants, setVariants] = useState<VariantRow[]>([]);
  const [variantName, setVariantName] = useState("");
  const [variantSku, setVariantSku] = useState("");
  const [variantBarcode, setVariantBarcode] = useState("");
  const [variantCost, setVariantCost] = useState("");
  const [variantPrice, setVariantPrice] = useState("");
  const [variantStock, setVariantStock] = useState("0");
  const [variantReorder, setVariantReorder] = useState("0");
  const [prices, setPrices] = useState<PriceRow[]>([]);
  const [priceName, setPriceName] = useState("");
  const [priceValue, setPriceValue] = useState("");
  const [minimumQuantity, setMinimumQuantity] = useState("1");
  const [editingVariantId, setEditingVariantId] = useState("");
  const [editingPriceId, setEditingPriceId] = useState("");
  const mutationLock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [importPreview, setImportPreview] = useState<ImportPreviewRow[]>([]);
  const [importFilename, setImportFilename] = useState("");

  async function mutate(action: () => Promise<void>) {
    if (mutationLock.current || !canManage) return;
    mutationLock.current = true; setBusy(true); setMessage("");
    try { await action(); }
    catch (error) { setMessage(getApiErrorMessage(error, "Unable to save product changes")); }
    finally { mutationLock.current = false; setBusy(false); }
  }

  function resetVariant() {
    setEditingVariantId(""); setVariantName(""); setVariantSku(""); setVariantBarcode("");
    setVariantCost(""); setVariantPrice(""); setVariantStock("0"); setVariantReorder("0");
  }
  function resetPrice() { setEditingPriceId(""); setPriceName(""); setPriceValue(""); setMinimumQuantity("1"); }

  useEffect(() => {
    resetVariant(); resetPrice(); setComponents([]); setVariants([]); setPrices([]);
  }, [selectedProductId, companyId, branchId, feature]);

  const loadCatalog = useCallback(async () => {
    const [productResponse, categoryResponse] = await Promise.all([
      api.get(`/products/${companyId}`), api.get(`/products/categories/${companyId}`),
    ]);
    setProducts(productResponse.data);
    setCategories(categoryResponse.data);
  }, [companyId]);

  useEffect(() => {
    void loadCatalog().catch((error) => setMessage(getApiErrorMessage(error, "Unable to load products")));
  }, [loadCatalog]);

  useEffect(() => {
    if (!selectedProductId) { setComponents([]); setVariants([]); setPrices([]); return; }
    let current = true;
    const request = feature === "composite-products"
      ? api.get(`/products/components/${companyId}/${selectedProductId}`)
      : feature === "product-variants"
        ? api.get(`/products/variants/${companyId}`, { params: { product_id: selectedProductId, branch_id: branchId } })
        : feature === "price-levels"
          ? api.get(`/products/price-levels/${companyId}`, { params: { product_id: selectedProductId } })
          : null;
    if (!request) return;
    void request.then((response) => {
      if (!current) return;
      if (feature === "composite-products") setComponents(response.data);
      if (feature === "product-variants") setVariants(response.data);
      if (feature === "price-levels") setPrices(response.data);
    }).catch((error) => { if (current) setMessage(getApiErrorMessage(error, "Unable to load product details")); });
    return () => { current = false; };
  }, [branchId, companyId, feature, selectedProductId]);

  const filteredCategories = useMemo(() => {
    const query = search.trim().toLowerCase();
    return categories.filter((category) => category.name.toLowerCase().includes(query));
  }, [categories, search]);

  async function saveCategory() {
    if (!categoryName.trim() || !canManage) return;
    const payload = { name: categoryName.trim(), parent_id: categoryParentId || null, image_url: categoryImageUrl.trim() || null };
    try {
      if (editingCategoryId) await api.patch(`/products/categories/${companyId}/${editingCategoryId}`, payload);
      else await api.post("/products/categories", { company_id: companyId, ...payload });
      setCategoryName(""); setCategoryParentId(""); setCategoryImageUrl(""); setEditingCategoryId("");
      await loadCatalog(); setMessage(editingCategoryId ? "Category updated" : "Category created"); onDataChanged?.();
    } catch (error) { setMessage(getApiErrorMessage(error, "Unable to save category")); }
  }

  async function deleteCategory(category: Category) {
    if (!canManage || !window.confirm(`Delete ${category.name}? Dependent categories and products will block deletion.`)) return;
    try { await api.delete(`/products/categories/${companyId}/${category.id}`); await loadCatalog(); setMessage("Category deleted"); }
    catch (error) { setMessage(getApiErrorMessage(error, "Unable to delete category")); }
  }

  function addComponent() {
    const product = products.find((item) => item.id === componentProductId);
    if (!product || Number(componentQuantity) <= 0) return;
    setComponents((current) => [...current.filter((row) => row.component_product_id !== product.id), {
      component_product_id: product.id, component_name: product.name, quantity: componentQuantity,
      unit: product.unit, component_cost: product.cost_price == null ? null : String(product.cost_price),
      total_cost: product.cost_price == null ? null : String(Number(product.cost_price) * Number(componentQuantity)),
    }]);
    setComponentProductId(""); setComponentQuantity("1");
  }

  async function saveComponents() {
    if (!canManage || !selectedProductId || !components.length) return;
    try {
      const response = await api.put(`/products/components/${companyId}/${selectedProductId}`, components.map((row) => ({ component_product_id: row.component_product_id, quantity: row.quantity, unit: row.unit })));
      setComponents(response.data); setMessage("Composite recipe saved"); await loadCatalog(); onDataChanged?.();
    } catch (error) { setMessage(getApiErrorMessage(error, "Unable to save recipe")); }
  }

  async function createVariant() {
    if (!canManage || !selectedProductId || !variantName.trim()) return;
    try {
      const metadata = {
        name: variantName.trim(), sku: variantSku.trim() || null,
        barcode: variantBarcode.trim() || null,
        ...(canViewCosts ? { cost_price: variantCost || null } : {}), selling_price: variantPrice || null,
        branch_id: branchId,
        reorder_level: variantReorder || "0",
      };
      if (editingVariantId) await api.patch(`/products/variants/${companyId}/item/${editingVariantId}`, metadata);
      else await api.post(`/products/variants/${companyId}/${selectedProductId}`, { ...metadata, attributes: {}, stock_qty: variantStock || "0" });
      resetVariant();
      const response = await api.get(`/products/variants/${companyId}`, { params: { product_id: selectedProductId, branch_id: branchId } }); setVariants(response.data); setMessage(editingVariantId ? "Variant updated" : "Variant created"); onDataChanged?.();
    } catch (error) { setMessage(getApiErrorMessage(error, "Unable to create variant")); }
  }

  async function createPrice() {
    if (!canManage || !selectedProductId || !priceName.trim() || priceValue === "") return;
    try {
      const payload = { name: priceName.trim(), price: priceValue, minimum_quantity: minimumQuantity };
      if (editingPriceId) await api.patch(`/products/price-levels/${companyId}/item/${editingPriceId}`, payload);
      else await api.post(`/products/price-levels/${companyId}/${selectedProductId}`, payload);
      resetPrice();
      const response = await api.get(`/products/price-levels/${companyId}`, { params: { product_id: selectedProductId } }); setPrices(response.data); setMessage(editingPriceId ? "Price level updated" : "Price level created"); onDataChanged?.();
    } catch (error) { setMessage(getApiErrorMessage(error, "Unable to create price level")); }
  }

  async function previewImport(file: File) {
    if (!canManage) return;
    try {
      const body = new FormData(); body.append("file", file);
      const response = await api.post(`/products/import/preview/${companyId}`, body, { headers: { "Content-Type": "multipart/form-data" } });
      setImportFilename(response.data.filename); setImportPreview(response.data.rows);
      setMessage(`${response.data.valid_rows} of ${response.data.total_rows} rows are valid`);
    } catch (error) { setImportPreview([]); setMessage(getApiErrorMessage(error, "Product import preview failed")); }
  }

  async function commitImport() {
    if (!canManage || !importPreview.length || importPreview.some((row) => row.errors.length)) return;
    try {
      await api.post("/products/import", { company_id: companyId, branch_id: branchId, rows: importPreview.map((row) => row.values) });
      await loadCatalog(); setMessage(`${importPreview.length} product rows imported`); setImportPreview([]); setImportFilename(""); onDataChanged?.();
    } catch (error) { setMessage(getApiErrorMessage(error, "Product import failed")); }
  }

  async function exportCsv() {
    try {
      const response = await api.get(`/products/export/${companyId}`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data); const link = document.createElement("a"); link.href = url; link.download = "products.csv"; link.click(); URL.revokeObjectURL(url);
    } catch (error) { setMessage(getApiErrorMessage(error, "Unable to export products")); }
  }

  async function setVariantActive(row: VariantRow) {
    if (!window.confirm(`${row.active ? "Archive" : "Restore"} ${row.name}?`)) return;
    await api.patch(`/products/variants/${companyId}/item/${row.id}`, { active: !row.active });
    setVariants((current) => current.map(item => item.id === row.id ? { ...item, active: !row.active } : item));
    if (editingVariantId === row.id) resetVariant();
    setMessage(row.active ? "Variant archived" : "Variant restored"); onDataChanged?.();
  }

  async function deletePrice(row: PriceRow) {
    if (!window.confirm(`Delete price level ${row.name}?`)) return;
    await api.delete(`/products/price-levels/${companyId}/item/${row.id}`);
    setPrices((current) => current.filter(item => item.id !== row.id));
    if (editingPriceId === row.id) resetPrice();
    setMessage("Price level deleted"); onDataChanged?.();
  }

  const title = feature === "categories" ? "Categories" : feature === "composite-products" ? "Composite Products" : feature === "product-variants" ? "Product Variants" : feature === "units" ? "Units & Case Breaking" : feature === "price-levels" ? "Price Levels" : feature === "barcode-labels" ? "Barcode Labels" : "Import / Export";
  const selectedProduct = products.find((item) => item.id === selectedProductId);

  return <section className="pos-module-card pos-product-tools">
    <div className="pos-module-card-heading"><div><h2>{title}</h2></div></div>
    {message && <div className="pos-module-notice">{message}</div>}
    <fieldset disabled={busy} style={{border:0,padding:0,margin:0,minWidth:0}} aria-busy={busy}>

    {feature === "categories" && <>
      {canManage && <div className="pos-product-tool-form"><input placeholder="Category name" value={categoryName} onChange={(event) => setCategoryName(event.target.value)} /><select value={categoryParentId} onChange={(event) => setCategoryParentId(event.target.value)}><option value="">Top level</option>{categories.filter((item) => item.id !== editingCategoryId).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><input placeholder="Image URL" value={categoryImageUrl} onChange={(event) => setCategoryImageUrl(event.target.value)} /><button onClick={() => void mutate(saveCategory)}>{editingCategoryId ? "Update" : "Add"}</button></div>}
      <input className="pos-product-search" placeholder="Search categories" value={search} onChange={(event) => setSearch(event.target.value)} />
      <div className="pos-module-table-wrap"><table className="pos-module-table"><thead><tr><th>Category</th><th>Parent</th><th>Status</th>{canManage && <th>Actions</th>}</tr></thead><tbody>{filteredCategories.map((category) => <tr key={category.id}><td>{category.name}</td><td>{categories.find((item) => item.id === category.parent_id)?.name || "Top level"}</td><td>{category.active ? "Active" : "Inactive"}</td>{canManage && <td><button className="pos-inline-button" onClick={() => { setEditingCategoryId(category.id); setCategoryName(category.name); setCategoryParentId(category.parent_id || ""); setCategoryImageUrl(category.image_url || ""); }}>Edit</button> <button className="pos-inline-button danger" onClick={() => void mutate(()=>deleteCategory(category))}>Delete</button></td>}</tr>)}</tbody></table></div>
    </>}

    {feature !== "categories" && feature !== "import-export" && <label className="pos-product-picker">Product<select value={selectedProductId} onChange={(event) => setSelectedProductId(event.target.value)}><option value="">Select product</option>{products.filter((product) => feature !== "composite-products" || ["composite", "bundle"].includes(product.product_type)).map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>}

    {feature === "composite-products" && selectedProductId && <>{canManage && <div className="pos-product-tool-form"><select value={componentProductId} onChange={(event) => setComponentProductId(event.target.value)}><option value="">Component</option>{products.filter((item) => item.id !== selectedProductId && item.track_inventory && !["composite", "bundle"].includes(item.product_type)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><input type="number" min="0.001" step="0.001" value={componentQuantity} onChange={(event) => setComponentQuantity(event.target.value)} /><button onClick={addComponent}>Add</button></div>}<div className="pos-module-table-wrap"><table className="pos-module-table"><thead><tr><th>Component</th><th>Quantity</th>{canViewCosts && <th>Cost</th>}{canManage && <th />}</tr></thead><tbody>{components.map((row) => <tr key={row.component_product_id}><td>{row.component_name}</td><td>{row.quantity} {row.unit}</td>{canViewCosts && <td>{row.total_cost == null ? "Unavailable" : Number(row.total_cost).toFixed(2)}</td>}{canManage && <td><button className="pos-inline-button danger" onClick={() => setComponents((current) => current.filter((item) => item.component_product_id !== row.component_product_id))}>Remove</button></td>}</tr>)}</tbody></table></div>{canManage && <button className="pos-primary-action" onClick={() => void mutate(saveComponents)}>Save Recipe</button>}</>}

    {feature === "product-variants" && selectedProductId && <>{canManage && <div className="pos-product-tool-form pos-variant-form"><input placeholder="Variant name" value={variantName} onChange={(event) => setVariantName(event.target.value)} /><input placeholder="SKU" value={variantSku} onChange={(event) => setVariantSku(event.target.value)} /><input placeholder="Barcode" value={variantBarcode} onChange={(event) => setVariantBarcode(event.target.value)} />{canViewCosts && <input type="number" min="0" step="0.01" placeholder="Cost" value={variantCost} onChange={(event) => setVariantCost(event.target.value)} />}<input type="number" min="0" step="0.01" placeholder="Selling price" value={variantPrice} onChange={(event) => setVariantPrice(event.target.value)} />{!editingVariantId && <input type="number" min="0" step="0.001" placeholder="Opening stock" value={variantStock} onChange={(event) => setVariantStock(event.target.value)} />}<input type="number" min="0" step="0.001" placeholder="Reorder" value={variantReorder} onChange={(event) => setVariantReorder(event.target.value)} /><button onClick={() => void mutate(createVariant)}>{editingVariantId ? "Update variant" : "Add variant"}</button>{editingVariantId && <button onClick={resetVariant}>Cancel edit</button>}</div>}<div className="pos-module-table-wrap"><table className="pos-module-table"><thead><tr><th>Variant</th><th>SKU</th><th>Barcode</th>{canViewCosts && <th>Cost</th>}<th>Selling</th><th>Stock</th><th>Reorder</th><th>Status</th>{canManage && <th>Actions</th>}</tr></thead><tbody>{variants.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.sku || "—"}</td><td>{row.barcode || "—"}</td>{canViewCosts && <td>{row.cost_price == null ? "Inherited" : Number(row.cost_price).toFixed(2)}</td>}<td>{row.selling_price == null ? "Inherited" : Number(row.selling_price).toFixed(2)}</td><td>{Number(row.stock_qty || 0)}</td><td>{Number(row.reorder_level || 0)}</td><td>{row.active ? "Active" : "Inactive"}</td>{canManage && <td><button className="pos-inline-button" onClick={()=>{setEditingVariantId(row.id);setVariantName(row.name);setVariantSku(row.sku || "");setVariantBarcode(row.barcode || "");setVariantCost(row.cost_price ?? "");setVariantPrice(row.selling_price ?? "");setVariantReorder(row.reorder_level || "0");}}>Edit</button> <button className="pos-inline-button" onClick={()=>void mutate(()=>setVariantActive(row))}>{row.active ? "Archive" : "Restore"}</button></td>}</tr>)}</tbody></table></div></>}

    {feature === "units" && selectedProduct && <div className="pos-unit-conversion"><strong>1 {selectedProduct.purchase_unit || selectedProduct.unit}</strong><span>=</span><strong>{selectedProduct.units_per_purchase} {selectedProduct.unit}</strong><small>Goods received in the purchase unit are converted to base selling units by the backend.</small></div>}

    {feature === "price-levels" && selectedProductId && <>{canManage && <div className="pos-product-tool-form"><input placeholder="Price level" value={priceName} onChange={(event) => setPriceName(event.target.value)} /><input type="number" min="0" step="0.01" placeholder="Price" value={priceValue} onChange={(event) => setPriceValue(event.target.value)} /><input type="number" min="0.001" step="0.001" placeholder="Minimum quantity" value={minimumQuantity} onChange={(event) => setMinimumQuantity(event.target.value)} /><button onClick={() => void mutate(createPrice)}>{editingPriceId ? "Update price level" : "Add price level"}</button>{editingPriceId && <button onClick={resetPrice}>Cancel edit</button>}</div>}<div className="pos-module-table-wrap"><table className="pos-module-table"><thead><tr><th>Level</th><th>Price</th><th>Minimum</th><th>Status</th>{canManage && <th>Actions</th>}</tr></thead><tbody>{prices.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.price}</td><td>{row.minimum_quantity}</td><td>{row.active ? "Active" : "Inactive"}</td>{canManage && <td><button className="pos-inline-button" onClick={()=>{setEditingPriceId(row.id);setPriceName(row.name);setPriceValue(row.price);setMinimumQuantity(row.minimum_quantity);}}>Edit</button> <button className="pos-inline-button danger" onClick={()=>void mutate(()=>deletePrice(row))}>Delete</button></td>}</tr>)}</tbody></table></div></>}

    {feature === "barcode-labels" && <div className="pos-barcode-labels">{products.filter((item) => !selectedProductId || item.id === selectedProductId).map((item) => <article key={item.id}><strong>{item.name}</strong><span>{item.barcode || item.sku || "No barcode"}</span><small>{item.selling_price == null ? "" : Number(item.selling_price).toFixed(2)}</small></article>)}<button className="pos-primary-action" onClick={() => window.print()}>Print Labels</button></div>}

    {feature === "import-export" && <div className="pos-import-export">{canManage && <label>Import CSV or Excel<input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => { const file = event.target.files?.[0]; if (file) void previewImport(file); }} /></label>}<button className="pos-primary-action" onClick={() => void exportCsv()}>Export CSV</button>{importPreview.length > 0 && <section className="pos-import-preview"><h3>{importFilename}</h3><p>{importPreview.length} rows · {importPreview.filter((row) => row.errors.length).length} errors</p><div className="pos-module-table-wrap"><table className="pos-module-table"><thead><tr><th>Row</th><th>Product</th><th>SKU</th><th>Variant</th><th>Validation</th></tr></thead><tbody>{importPreview.map((row) => <tr key={row.row_number} className={row.errors.length ? "pos-import-error" : ""}><td>{row.row_number}</td><td>{row.values.name || "—"}</td><td>{row.values.sku || "—"}</td><td>{row.values.variant_name || "—"}</td><td>{row.errors.length ? row.errors.join("; ") : "Ready"}</td></tr>)}</tbody></table></div>{canManage && <button className="pos-primary-action" disabled={importPreview.some((row) => row.errors.length > 0)} onClick={() => void mutate(commitImport)}>Import valid preview</button>}</section>}</div>}
    </fieldset>
  </section>;
}
