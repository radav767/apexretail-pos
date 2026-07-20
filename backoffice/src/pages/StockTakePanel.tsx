import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

type Product = {
  product_id: string;
  name: string;
  sku: string | null;
  unit: string;
  stock_qty: string;
};

export default function StockTakePanel({
  companyId,
  onDataChanged,
}: {
  companyId: string;
  onDataChanged?: () => void;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [counts, setCounts] = useState<Record<string, string>>({});
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const countedProducts = useMemo(
    () =>
      products.filter(
        (product) =>
          counts[product.product_id] !== undefined &&
          counts[product.product_id] !== "",
      ),
    [products, counts],
  );

  async function loadProducts() {
    try {
      setLoading(true);

      const response = await api.get(
        `/inventory/overview/${companyId}`,
      );

      setProducts(response.data);
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to load stock-take products",
      );
    } finally {
      setLoading(false);
    }
  }

  function fillSystemQuantities() {
    const values: Record<string, string> = {};

    products.forEach((product) => {
      values[product.product_id] = String(
        Number(product.stock_qty),
      );
    });

    setCounts(values);
  }

  function clearCounts() {
    setCounts({});
  }

  async function submitStockTake() {
    if (!countedProducts.length) {
      setMessage(
        "Enter the physical quantity for at least one product",
      );
      return;
    }

    const invalid = countedProducts.some((product) => {
      const value = Number(counts[product.product_id]);

      return !Number.isFinite(value) || value < 0;
    });

    if (invalid) {
      setMessage(
        "Physical quantities must be zero or greater",
      );
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      await api.post("/inventory/stock-take", {
        company_id: companyId,
        reference: reference.trim() || null,
        notes: notes.trim() || null,
        items: countedProducts.map((product) => ({
          product_id: product.product_id,
          physical_qty: counts[product.product_id],
        })),
      });

      setMessage(
        `Stock take completed for ${countedProducts.length} product(s)`,
      );

      setCounts({});
      setReference("");
      setNotes("");

      await loadProducts();
      onDataChanged?.();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to complete stock take",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadProducts();
  }, [companyId]);

  return (
    <section className="inventory-form-card">
      <div className="inventory-panel-header stock-take-header">
        <div>
          <h2>Stock Take</h2>
          <p>
            Compare system stock with the physical quantity counted.
          </p>
        </div>

        <div className="stock-take-header-actions">
          <button onClick={fillSystemQuantities}>
            Fill system quantities
          </button>

          <button onClick={clearCounts}>
            Clear counts
          </button>
        </div>
      </div>

      <div className="stock-take-details">
        <label>
          Stock-take reference
          <input
            value={reference}
            placeholder="Example: COUNT-2026-001"
            onChange={(event) =>
              setReference(event.target.value)
            }
          />
        </label>

        <label>
          Notes
          <input
            value={notes}
            placeholder="Optional notes"
            onChange={(event) =>
              setNotes(event.target.value)
            }
          />
        </label>
      </div>

      <div className="inventory-table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>SKU</th>
              <th>Unit</th>
              <th>System Quantity</th>
              <th>Physical Quantity</th>
              <th>Variance</th>
            </tr>
          </thead>

          <tbody>
            {products.map((product) => {
              const entered = counts[product.product_id];
              const hasCount =
                entered !== undefined && entered !== "";

              const variance = hasCount
                ? Number(entered) - Number(product.stock_qty)
                : 0;

              return (
                <tr key={product.product_id}>
                  <td>
                    <strong>{product.name}</strong>
                  </td>

                  <td>{product.sku || "—"}</td>
                  <td>{product.unit}</td>
                  <td>{Number(product.stock_qty)}</td>

                  <td>
                    <input
                      className="physical-count-input"
                      type="number"
                      min="0"
                      step="0.001"
                      value={entered || ""}
                      placeholder="Not counted"
                      onChange={(event) =>
                        setCounts((current) => ({
                          ...current,
                          [product.product_id]:
                            event.target.value,
                        }))
                      }
                    />
                  </td>

                  <td>
                    <span
                      className={
                        !hasCount || variance === 0
                          ? "variance-neutral"
                          : variance > 0
                            ? "variance-positive"
                            : "variance-negative"
                      }
                    >
                      {hasCount
                        ? variance > 0
                          ? `+${variance}`
                          : variance
                        : "—"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <button
        className="inventory-primary-button"
        onClick={submitStockTake}
        disabled={loading || !countedProducts.length}
      >
        {loading
          ? "Applying Count..."
          : `Complete Stock Take (${countedProducts.length})`}
      </button>

      <p className="inventory-message">{message}</p>
    </section>
  );
}
