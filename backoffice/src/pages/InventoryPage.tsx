import { useEffect, useState } from "react";
import { api } from "../api/client";
import "./inventory.css";
import StockTakePanel from "./StockTakePanel";

type InventoryProduct = {
  product_id: string;
  name: string;
  sku: string | null;
  unit: string;
  cost_price: string;
  selling_price: string;
  stock_qty: string;
  reorder_level: string;
  stock_value: string;
  low_stock: boolean;
};

type Valuation = {
  total_products: number;
  total_quantity: string;
  total_cost_value: string;
  low_stock_products: number;
};

type Movement = {
  id: string;
  product_id: string;
  product_name: string;
  movement_type: string;
  quantity: string;
  before_qty: string;
  after_qty: string;
  unit_cost: string;
  reference: string | null;
  supplier: string | null;
  reason: string | null;
  notes: string | null;
  created_at: string;
};

type InventoryTab =
  | "overview"
  | "grn"
  | "adjustment"
  | "stocktake"
  | "valuation"
  | "history";

const emptyValuation: Valuation = {
  total_products: 0,
  total_quantity: "0",
  total_cost_value: "0",
  low_stock_products: 0,
};

export default function InventoryPage({
  companyId,
  onDataChanged,
}: {
  companyId: string;
  onDataChanged?: () => void;
}) {
  const [tab, setTab] = useState<InventoryTab>("overview");
  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [history, setHistory] = useState<Movement[]>([]);
  const [valuation, setValuation] =
    useState<Valuation>(emptyValuation);

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const [grn, setGrn] = useState({
    product_id: "",
    quantity: "",
    unit_cost: "",
    reference: "",
    supplier: "",
    notes: "",
  });

  const [adjustment, setAdjustment] = useState({
    product_id: "",
    adjustment_type: "add",
    quantity: "",
    reason: "",
    reference: "",
    notes: "",
  });

  async function loadInventory() {
    if (!companyId) return;

    try {
      setLoading(true);

      const [overviewResponse, valuationResponse, historyResponse] =
        await Promise.all([
          api.get(`/inventory/overview/${companyId}`),
          api.get(`/inventory/valuation/${companyId}`),
          api.get(`/inventory/history/${companyId}?limit=200`),
        ]);

      const loadedProducts: InventoryProduct[] =
        overviewResponse.data;

      setProducts(loadedProducts);
      setValuation(valuationResponse.data);
      setHistory(historyResponse.data);

      const firstProductId = loadedProducts[0]?.product_id || "";

      setGrn((current) => ({
        ...current,
        product_id: current.product_id || firstProductId,
      }));

      setAdjustment((current) => ({
        ...current,
        product_id: current.product_id || firstProductId,
      }));
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to load inventory information",
      );
    } finally {
      setLoading(false);
    }
  }

  async function saveGrn() {
    const quantity = Number(grn.quantity);

    if (!grn.product_id) {
      setMessage("Select a product");
      return;
    }

    if (!Number.isFinite(quantity) || quantity <= 0) {
      setMessage("GRN quantity must be greater than zero");
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      await api.post("/inventory/grn", {
        company_id: companyId,
        product_id: grn.product_id,
        quantity: grn.quantity,
        unit_cost: grn.unit_cost || null,
        reference: grn.reference.trim() || null,
        supplier: grn.supplier.trim() || null,
        notes: grn.notes.trim() || null,
      });

      setGrn((current) => ({
        ...current,
        quantity: "",
        reference: "",
        supplier: "",
        notes: "",
      }));

      setMessage("Goods received successfully");
      await loadInventory();
      onDataChanged?.();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to receive goods",
      );
    } finally {
      setLoading(false);
    }
  }

  async function saveAdjustment() {
    const quantity = Number(adjustment.quantity);

    if (!adjustment.product_id) {
      setMessage("Select a product");
      return;
    }

    if (
      !Number.isFinite(quantity) ||
      quantity < 0 ||
      (adjustment.adjustment_type !== "set" && quantity <= 0)
    ) {
      setMessage("Enter a valid adjustment quantity");
      return;
    }

    if (!adjustment.reason.trim()) {
      setMessage("Adjustment reason is required");
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      await api.post("/inventory/adjustments", {
        company_id: companyId,
        product_id: adjustment.product_id,
        adjustment_type: adjustment.adjustment_type,
        quantity: adjustment.quantity,
        reason: adjustment.reason.trim(),
        reference: adjustment.reference.trim() || null,
        notes: adjustment.notes.trim() || null,
      });

      setAdjustment((current) => ({
        ...current,
        quantity: "",
        reason: "",
        reference: "",
        notes: "",
      }));

      setMessage("Stock adjustment completed");
      await loadInventory();
      onDataChanged?.();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to adjust stock",
      );
    } finally {
      setLoading(false);
    }
  }

  function productName(productId: string) {
    return (
      products.find(
        (product) => product.product_id === productId,
      )?.name || "Unknown product"
    );
  }

  useEffect(() => {
    void loadInventory();
  }, [companyId]);

  return (
    <div className="inventory-page">
      <div className="inventory-tabs">
        {[
          ["overview", "Overview"],
          ["grn", "Goods Received"],
          ["adjustment", "Stock Adjustment"],
          ["stocktake", "Stock Take"],
          ["valuation", "Valuation"],
          ["history", "History"],
        ].map(([value, label]) => (
          <button
            key={value}
            className={tab === value ? "active" : ""}
            onClick={() => setTab(value as InventoryTab)}
          >
            {label}
          </button>
        ))}

        <button
          className="inventory-refresh"
          onClick={loadInventory}
          disabled={loading}
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {tab === "overview" && (
        <>
          <section className="inventory-summary">
            <InventoryCard
              title="Products"
              value={String(valuation.total_products)}
              detail="Active inventory products"
            />

            <InventoryCard
              title="Total Quantity"
              value={Number(
                valuation.total_quantity,
              ).toLocaleString()}
              detail="Units currently available"
            />

            <InventoryCard
              title="Stock Value"
              value={`$${Number(
                valuation.total_cost_value,
              ).toFixed(2)}`}
              detail="Based on cost price"
            />

            <InventoryCard
              title="Low Stock"
              value={String(valuation.low_stock_products)}
              detail="Require attention"
              warning={valuation.low_stock_products > 0}
            />
          </section>

          <section className="inventory-panel">
            <div className="inventory-panel-header">
              <div>
                <h2>Inventory Overview</h2>
                <p>Current quantities used by the POS</p>
              </div>
            </div>

            <InventoryTable products={products} />
          </section>
        </>
      )}

      {tab === "grn" && (
        <section className="inventory-form-card">
          <div className="inventory-panel-header">
            <div>
              <h2>Goods Received Note</h2>
              <p>Add supplier deliveries to current stock.</p>
            </div>
          </div>

          <div className="inventory-form-grid">
            <label>
              Product
              <select
                value={grn.product_id}
                onChange={(event) =>
                  setGrn({
                    ...grn,
                    product_id: event.target.value,
                  })
                }
              >
                <option value="">Select product</option>

                {products.map((product) => (
                  <option
                    key={product.product_id}
                    value={product.product_id}
                  >
                    {product.name} — Stock {product.stock_qty}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Quantity received
              <input
                type="number"
                min="0.001"
                step="0.001"
                value={grn.quantity}
                onChange={(event) =>
                  setGrn({
                    ...grn,
                    quantity: event.target.value,
                  })
                }
              />
            </label>

            <label>
              Unit cost
              <input
                type="number"
                min="0"
                step="0.01"
                value={grn.unit_cost}
                placeholder="Keep current cost"
                onChange={(event) =>
                  setGrn({
                    ...grn,
                    unit_cost: event.target.value,
                  })
                }
              />
            </label>

            <label>
              GRN reference
              <input
                value={grn.reference}
                placeholder="Example: GRN-0001"
                onChange={(event) =>
                  setGrn({
                    ...grn,
                    reference: event.target.value,
                  })
                }
              />
            </label>

            <label>
              Supplier
              <input
                value={grn.supplier}
                placeholder="Supplier name"
                onChange={(event) =>
                  setGrn({
                    ...grn,
                    supplier: event.target.value,
                  })
                }
              />
            </label>

            <label className="inventory-full-field">
              Notes
              <textarea
                value={grn.notes}
                onChange={(event) =>
                  setGrn({
                    ...grn,
                    notes: event.target.value,
                  })
                }
              />
            </label>
          </div>

          <button
            className="inventory-primary-button"
            onClick={saveGrn}
            disabled={loading}
          >
            {loading ? "Saving..." : "Receive Goods"}
          </button>
        </section>
      )}

      {tab === "adjustment" && (
        <section className="inventory-form-card">
          <div className="inventory-panel-header">
            <div>
              <h2>Stock Adjustment</h2>
              <p>
                Add, remove or set the physical stock quantity.
              </p>
            </div>
          </div>

          <div className="inventory-form-grid">
            <label>
              Product
              <select
                value={adjustment.product_id}
                onChange={(event) =>
                  setAdjustment({
                    ...adjustment,
                    product_id: event.target.value,
                  })
                }
              >
                <option value="">Select product</option>

                {products.map((product) => (
                  <option
                    key={product.product_id}
                    value={product.product_id}
                  >
                    {product.name} — Stock {product.stock_qty}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Adjustment type
              <select
                value={adjustment.adjustment_type}
                onChange={(event) =>
                  setAdjustment({
                    ...adjustment,
                    adjustment_type: event.target.value,
                  })
                }
              >
                <option value="add">Add stock</option>
                <option value="remove">Remove stock</option>
                <option value="set">Set physical quantity</option>
              </select>
            </label>

            <label>
              Quantity
              <input
                type="number"
                min="0"
                step="0.001"
                value={adjustment.quantity}
                onChange={(event) =>
                  setAdjustment({
                    ...adjustment,
                    quantity: event.target.value,
                  })
                }
              />
            </label>

            <label>
              Reason
              <input
                value={adjustment.reason}
                placeholder="Example: Damaged stock"
                onChange={(event) =>
                  setAdjustment({
                    ...adjustment,
                    reason: event.target.value,
                  })
                }
              />
            </label>

            <label>
              Reference
              <input
                value={adjustment.reference}
                placeholder="Example: SA-0001"
                onChange={(event) =>
                  setAdjustment({
                    ...adjustment,
                    reference: event.target.value,
                  })
                }
              />
            </label>

            <label className="inventory-full-field">
              Notes
              <textarea
                value={adjustment.notes}
                onChange={(event) =>
                  setAdjustment({
                    ...adjustment,
                    notes: event.target.value,
                  })
                }
              />
            </label>
          </div>

          <button
            className="inventory-primary-button"
            onClick={saveAdjustment}
            disabled={loading}
          >
            {loading ? "Saving..." : "Save Adjustment"}
          </button>
        </section>
      )}


      {tab === "stocktake" && (
        <StockTakePanel
          companyId={companyId}
          onDataChanged={() => {
            void loadInventory();
            onDataChanged?.();
          }}
        />
      )}

      {tab === "valuation" && (
        <section className="inventory-panel">
          <div className="inventory-panel-header">
            <div>
              <h2>Inventory Valuation</h2>
              <p>Stock quantity multiplied by cost price.</p>
            </div>
          </div>

          <section className="inventory-summary">
            <InventoryCard
              title="Total Products"
              value={String(valuation.total_products)}
              detail="Included in valuation"
            />

            <InventoryCard
              title="Total Quantity"
              value={Number(
                valuation.total_quantity,
              ).toLocaleString()}
              detail="Available units"
            />

            <InventoryCard
              title="Total Cost Value"
              value={`$${Number(
                valuation.total_cost_value,
              ).toFixed(2)}`}
              detail="Current inventory asset value"
            />

            <InventoryCard
              title="Low Stock"
              value={String(valuation.low_stock_products)}
              detail="Products at reorder level"
              warning={valuation.low_stock_products > 0}
            />
          </section>

          <InventoryTable products={products} />
        </section>
      )}

      {tab === "history" && (
        <section className="inventory-panel">
          <div className="inventory-panel-header">
            <div>
              <h2>Inventory History</h2>
              <p>
                Permanent audit record of GRNs and adjustments.
              </p>
            </div>
          </div>

          {!history.length ? (
            <div className="inventory-empty">
              No inventory movements found.
            </div>
          ) : (
            <div className="inventory-table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Product</th>
                    <th>Movement</th>
                    <th>Quantity</th>
                    <th>Before</th>
                    <th>After</th>
                    <th>Reference</th>
                    <th>Supplier / Reason</th>
                  </tr>
                </thead>

                <tbody>
                  {history.map((movement) => (
                    <tr key={movement.id}>
                      <td>
                        {new Date(
                          movement.created_at,
                        ).toLocaleString()}
                      </td>

                      <td>
                        {movement.product_name ||
                          productName(movement.product_id)}
                      </td>

                      <td>
                        <span className="movement-badge">
                          {movement.movement_type
                            .replace(/_/g, " ")
                            .toUpperCase()}
                        </span>
                      </td>

                      <td>{Number(movement.quantity)}</td>
                      <td>{Number(movement.before_qty)}</td>
                      <td>{Number(movement.after_qty)}</td>
                      <td>{movement.reference || "—"}</td>

                      <td>
                        {movement.supplier ||
                          movement.reason ||
                          "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <p className="inventory-message">{message}</p>
    </div>
  );
}

function InventoryCard({
  title,
  value,
  detail,
  warning = false,
}: {
  title: string;
  value: string;
  detail: string;
  warning?: boolean;
}) {
  return (
    <article
      className={`inventory-card ${warning ? "warning" : ""}`}
    >
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function InventoryTable({
  products,
}: {
  products: InventoryProduct[];
}) {
  if (!products.length) {
    return (
      <div className="inventory-empty">
        No inventory products found.
      </div>
    );
  }

  return (
    <div className="inventory-table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Product</th>
            <th>SKU</th>
            <th>Unit</th>
            <th>Cost</th>
            <th>Selling</th>
            <th>Stock</th>
            <th>Reorder</th>
            <th>Value</th>
            <th>Status</th>
          </tr>
        </thead>

        <tbody>
          {products.map((product) => (
            <tr key={product.product_id}>
              <td>
                <strong>{product.name}</strong>
              </td>

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
                ${Number(product.stock_value).toFixed(2)}
              </td>

              <td>
                <span
                  className={
                    product.low_stock
                      ? "inventory-low-badge"
                      : "inventory-ok-badge"
                  }
                >
                  {product.low_stock ? "Low stock" : "In stock"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
