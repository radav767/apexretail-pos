import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import "./products.css";

type Category = {
  id: string;
  company_id: string;
  name: string;
  active: boolean;
};

type Product = {
  id: string;
  company_id: string;
  category_id: string | null;
  name: string;
  sku: string | null;
  barcode: string | null;
  unit: string;
  cost_price: string;
  selling_price: string;
  stock_qty: string;
  reorder_level: string;
  active: boolean;
};

type ProductForm = {
  name: string;
  category_id: string;
  sku: string;
  barcode: string;
  unit: string;
  cost_price: string;
  selling_price: string;
  stock_qty: string;
  reorder_level: string;
};

const emptyForm: ProductForm = {
  name: "",
  category_id: "",
  sku: "",
  barcode: "",
  unit: "each",
  cost_price: "0.00",
  selling_price: "0.00",
  stock_qty: "0",
  reorder_level: "0",
};

export default function ProductsPage({
  companyId,
  onDataChanged,
}: {
  companyId: string;
  onDataChanged?: () => void;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);

  const [form, setForm] = useState<ProductForm>(emptyForm);
  const [editingProductId, setEditingProductId] = useState<string | null>(
    null,
  );

  const [categoryName, setCategoryName] = useState("");
  const [editingCategoryId, setEditingCategoryId] = useState<
    string | null
  >(null);

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

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

  async function loadData() {
    if (!companyId) return;

    try {
      setLoading(true);
      setMessage("");

      const [productsResponse, categoriesResponse] = await Promise.all([
        api.get(`/products/${companyId}`),
        api.get(`/products/categories/${companyId}`),
      ]);

      setProducts(productsResponse.data);
      setCategories(categoriesResponse.data);
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to load products and categories",
      );
    } finally {
      setLoading(false);
    }
  }

  function updateForm(field: keyof ProductForm, value: string) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function resetProductForm() {
    setForm(emptyForm);
    setEditingProductId(null);
  }

  function startEditingProduct(product: Product) {
    setEditingProductId(product.id);

    setForm({
      name: product.name,
      category_id: product.category_id || "",
      sku: product.sku || "",
      barcode: product.barcode || "",
      unit: product.unit,
      cost_price: product.cost_price,
      selling_price: product.selling_price,
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

    try {
      setLoading(true);
      setMessage("");

      const payload = {
        category_id: form.category_id || null,
        name: form.name.trim(),
        sku: form.sku.trim() || null,
        barcode: form.barcode.trim() || null,
        unit: form.unit,
        cost_price: form.cost_price || "0",
        selling_price: form.selling_price || "0",
        stock_qty: form.stock_qty || "0",
        reorder_level: form.reorder_level || "0",
      };

      if (editingProductId) {
        await api.patch(
          `/products/${companyId}/${editingProductId}`,
          payload,
        );

        setMessage("Product updated successfully");
      } else {
        await api.post("/products", {
          company_id: companyId,
          ...payload,
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
  }

  function resetCategoryForm() {
    setEditingCategoryId(null);
    setCategoryName("");
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
          },
        );

        setMessage("Category updated successfully");
      } else {
        await api.post("/products/categories", {
          company_id: companyId,
          name,
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
      `Delete category "${category.name}"? Products in it will become uncategorized.`,
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
  }, [companyId]);

  return (
    <div className="products-page">
      <section className="products-form-grid">
        <article className="product-management-card">
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
              Unit
              <select
                value={form.unit}
                onChange={(event) =>
                  updateForm("unit", event.target.value)
                }
              >
                <option value="each">Each</option>
                <option value="kg">Kilogram</option>
                <option value="g">Gram</option>
              </select>
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
            </label>

            <label>
              Opening stock
              <input
                type="number"
                min="0"
                step="0.001"
                value={form.stock_qty}
                onChange={(event) =>
                  updateForm("stock_qty", event.target.value)
                }
              />
            </label>

            <label>
              Reorder level
              <input
                type="number"
                min="0"
                step="0.001"
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
        </article>

        <article className="product-management-card">
          <div className="management-card-header">
            <div>
              <h2>Categories</h2>
              <p>Organize products for the POS sales screen.</p>
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

            {categories.map((category) => (
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
        </article>
      </section>

      <section className="product-management-card product-list-card">
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
                      ${Number(product.cost_price).toFixed(2)}
                    </td>

                    <td>
                      ${Number(product.selling_price).toFixed(2)}
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
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="products-message">{message}</p>
    </div>
  );
}
