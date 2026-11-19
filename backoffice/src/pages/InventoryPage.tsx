import ProductSelector from "../../../pos-web/src/components/ProductSelector";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import BranchTransferPanel from "./BranchTransferPanel";
import "./inventory.css";
import StockTakePanel from "./StockTakePanel";

type InventoryProduct = {
  product_id: string;
  name: string;
  sku: string | null;
  unit: string;
  purchase_unit: string | null;
  units_per_purchase: string;
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
  low_stock_products: number;
};

type FinancialMetric = { available: boolean; value: string | null; reason?: string | null };
type ProjectedValuation = {
  basis: string; currency_symbol: string; decimal_places: number; total: number;
  summary: { quantity: string; selling_value: FinancialMetric; cost_value: FinancialMetric; projected_gross_profit: FinancialMetric; margin_percentage: FinancialMetric };
  rows: Array<{ product_id: string; product_name: string; sku: string | null; branch_id: string; branch_name: string; shop_name: string; quantity: string; selling_value: FinancialMetric; cost_value: FinancialMetric; projected_gross_profit: FinancialMetric; margin_percentage: FinancialMetric }>;
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


type InventoryBranch = {
  id: string;
  shop_id: string;
  shop_name: string;
  name: string;
};

type InventoryTab =
  | "overview"
  | "grn"
  | "adjustment"
  | "stocktake"
  | "transfers"
  | "valuation"
  | "history";

const emptyValuation: Valuation = {
  total_products: 0,
  total_quantity: "0",
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

  const [branches, setBranches] =
    useState<InventoryBranch[]>([]);

  const [selectedBranchId, setSelectedBranchId] =
    useState("");

  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [history, setHistory] = useState<Movement[]>([]);
  const [valuation, setValuation] =
    useState<Valuation>(emptyValuation);
  const [projectedValuation, setProjectedValuation] = useState<ProjectedValuation | null>(null);
  const [valuationMessage, setValuationMessage] = useState("");
  const [valuationLoading, setValuationLoading] = useState(false);

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const [grn, setGrn] = useState({
    product_id: "",
    quantity: "",
    received_unit: "",
    reason: "",
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


  async function loadBranches() {
    if (!companyId) return;

    try {
      const response = await api.get(
        `/inventory/branches/${companyId}`,
      );

      const loadedBranches: InventoryBranch[] =
        response.data;

      setBranches(loadedBranches);

      setSelectedBranchId((current) => {
        return loadedBranches.some(
          (branch) => branch.id === current,
        )
          ? current
          : loadedBranches[0]?.id || "";
      });
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to load branches",
      );
    }
  }

  async function loadInventory() {
    if (!companyId) return;

    try {
      setLoading(true);

      const [overviewResponse, historyResponse] =
        await Promise.all([
          api.get(`/inventory/overview/${companyId}`),
          api.get(`/inventory/history/${companyId}?limit=200`),
        ]);

      const loadedProducts: InventoryProduct[] =
        overviewResponse.data;

      setProducts(loadedProducts);
      setValuation({
        total_products: loadedProducts.length,
        total_quantity: loadedProducts
          .reduce((total, product) => total + Number(product.stock_qty), 0)
          .toString(),
        low_stock_products: loadedProducts.filter((product) => product.low_stock).length,
      });
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

  const loadProjectedValuation = useCallback(async () => {
    if (!companyId) return;
    try {
      setValuationLoading(true);
      setValuationMessage("");
      const response = await api.get(`/reports/inventory-valuation/${companyId}`, { params: { branch_id: selectedBranchId || undefined, limit: 100 } });
      setProjectedValuation(response.data);
    } catch (error: any) {
      setProjectedValuation(null);
      setValuationMessage(error.response?.status === 403 ? "You do not have permission to view inventory cost, profit or margin." : error.response?.data?.detail || "Failed to load inventory valuation");
    } finally {
      setValuationLoading(false);
    }
  }, [companyId, selectedBranchId]);

  async function exportProjectedValuation() {
    try {
      const response = await api.get(`/reports/inventory-valuation/${companyId}/export.csv`, { params: { branch_id: selectedBranchId || undefined }, responseType: "blob" });
      const url = URL.createObjectURL(response.data); const anchor = document.createElement("a");
      anchor.href = url; anchor.download = "inventory-valuation.csv"; anchor.click(); URL.revokeObjectURL(url);
    } catch (error: any) { setValuationMessage(error.response?.data?.detail || "Failed to export inventory valuation"); }
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

    if (!grn.reason.trim()) {
      setMessage("A receiving reason is required");
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      await api.post("/inventory/grn", {
        company_id: companyId,
        branch_id: selectedBranchId || null,
        product_id: grn.product_id,
        quantity: grn.quantity,
        received_unit: grn.received_unit || null,
        reason: grn.reason.trim(),
        unit_cost: grn.unit_cost || null,
        reference: grn.reference.trim() || null,
        supplier: grn.supplier.trim() || null,
        notes: grn.notes.trim() || null,
      });

      setGrn((current) => ({
        ...current,
        quantity: "",
        reason: "",
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
        branch_id: selectedBranchId || null,
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
    void loadBranches();
    void loadInventory();
  }, [companyId]);

  useEffect(() => { void loadProjectedValuation(); }, [loadProjectedValuation]);

  return (
    <div className="inventory-page">

      <section className="inventory-branch-toolbar">
        <div>
          <span>Working branch</span>
          <strong>
            {branches.find(
              (branch) =>
                branch.id === selectedBranchId,
            )?.name || "No branch selected"}
          </strong>
        </div>

        <label>
          Select branch
          <select
            value={selectedBranchId}
            onChange={(event) =>
              setSelectedBranchId(event.target.value)
            }
          >
            {branches.map((branch) => (
              <option
                key={branch.id}
                value={branch.id}
              >
                {branch.shop_name} — {branch.name}
              </option>
            ))}
          </select>
        </label>
      </section>

      <div className="inventory-tabs">
        {[
          ["overview", "Overview"],
          ["grn", "Goods Received"],
          ["adjustment", "Stock Adjustment"],
          ["stocktake", "Stock Take"],
          ["transfers", "Branches & Transfers"],
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
            <ProductSelector companyId={companyId} branchId={selectedBranchId} scopeKey={companyId} value={grn.product_id} selectedLabel={products.find(p => p.product_id === grn.product_id)?.name} onChange={id => setGrn(current => ({ ...current, product_id: id }))} client={api} disabled={loading}/>

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
              Receiving unit
              <select value={grn.received_unit} onChange={(event) => setGrn({ ...grn, received_unit: event.target.value })}>
                <option value="">Base selling unit</option>
                {(() => {
                  const product = products.find((item) => item.product_id === grn.product_id);
                  return product?.purchase_unit
                    ? <option value={product.purchase_unit}>{product.purchase_unit} ({product.units_per_purchase} {product.unit})</option>
                    : null;
                })()}
              </select>
            </label>

            <label>
              Reason
              <input
                value={grn.reason}
                placeholder="Example: Supplier delivery"
                onChange={(event) =>
                  setGrn({
                    ...grn,
                    reason: event.target.value,
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
            <ProductSelector companyId={companyId} branchId={selectedBranchId} scopeKey={companyId} value={adjustment.product_id} selectedLabel={products.find(p => p.product_id === adjustment.product_id)?.name} onChange={id => setAdjustment(current => ({ ...current, product_id: id }))} client={api} disabled={loading}/>

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
            branchId={selectedBranchId}
          onDataChanged={() => {
            void loadInventory();
            onDataChanged?.();
          }}
        />
      )}


      {tab === "transfers" && (
        <BranchTransferPanel
          companyId={companyId}
          onDataChanged={async () => {
            await loadBranches();
            await loadInventory();
            onDataChanged?.();
          }}
        />
      )}

      {tab === "valuation" && (
        <section className="inventory-panel">
          <div className="inventory-panel-header">
            <div>
              <h2>Inventory Valuation</h2>
              <p>{projectedValuation?.basis || "Valuation uses current prices, not historical realized profit."}</p>
            </div>
            <button className="inventory-refresh" onClick={() => void exportProjectedValuation()}>Export CSV</button>
          </div>

          {valuationMessage && <p className="inventory-message" role="alert">{valuationMessage}</p>}
          {valuationLoading && <div className="inventory-empty">Loading current-price valuation…</div>}
          {projectedValuation && <><section className="inventory-summary">
            <InventoryCard
              title="Quantity on hand"
              value={Number(projectedValuation.summary.quantity).toLocaleString()}
              detail="Authoritative branch balances"
            />
            <InventoryCard
              title="Stock selling value"
              value={formatFinancial(projectedValuation.summary.selling_value, projectedValuation)}
              detail="Quantity × current selling price"
            />
            <InventoryCard
              title="Stock cost value"
              value={formatFinancial(projectedValuation.summary.cost_value, projectedValuation)}
              detail="Quantity × recorded unit cost"
            />
            <InventoryCard
              title="Projected gross profit"
              value={formatFinancial(projectedValuation.summary.projected_gross_profit, projectedValuation)}
              detail="Selling value less cost value"
            />
            <InventoryCard title="Margin" value={formatFinancial(projectedValuation.summary.margin_percentage, projectedValuation, true)} detail="Projected profit ÷ selling value" />
          </section>
          <div className="inventory-table-wrapper"><table><thead><tr><th>Shop / branch</th><th>Product</th><th>Quantity</th><th>Selling value</th><th>Cost value</th><th>Projected profit</th><th>Margin</th></tr></thead><tbody>{projectedValuation.rows.length ? projectedValuation.rows.map((row,index) => <tr key={`${row.branch_id}-${row.product_id}-${index}`}><td>{row.shop_name} — {row.branch_name}</td><td><strong>{row.product_name}</strong><br/><small>{row.sku || "No SKU"}</small></td><td>{Number(row.quantity).toLocaleString()}</td><td>{formatFinancial(row.selling_value, projectedValuation)}</td><td>{formatFinancial(row.cost_value, projectedValuation)}</td><td>{formatFinancial(row.projected_gross_profit, projectedValuation)}</td><td>{formatFinancial(row.margin_percentage, projectedValuation, true)}</td></tr>) : <tr><td colSpan={7} className="inventory-empty">No inventory balances match this branch.</td></tr>}</tbody></table></div></>}
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

function formatFinancial(metric: FinancialMetric, valuation: ProjectedValuation, percent = false) {
  if (!metric.available) return "Unavailable";
  return percent ? `${Number(metric.value).toFixed(2)}%` : `${valuation.currency_symbol}${Number(metric.value).toFixed(valuation.decimal_places)}`;
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
            <th>Stock</th>
            <th>Reorder</th>
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

              <td>{Number(product.stock_qty)}</td>
              <td>{Number(product.reorder_level)}</td>

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
