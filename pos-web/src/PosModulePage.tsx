import { useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import "./pos-modules.css";

export type PosModuleName =
  | "Sales"
  | "Sales Management"
  | "Products"
  | "Inventory"
  | "Reports"
  | "Settings";

type Sale = {
  id: string;
  receipt_number?: string;
  cashier_name?: string | null;
  payment_method?: string;
  total_amount?: string | number;
  status?: string;
  created_at?: string;
};

type Product = {
  id: string;
  name: string;
  sku?: string | null;
  barcode?: string | null;
  selling_price?: string | number;
  cost_price?: string | number;
  stock_qty?: string | number;
  reorder_level?: string | number;
  active?: boolean;
};

type DashboardSummary = {
  today_sales?: string | number;
  today_transactions?: number;
  total_products?: number;
  low_stock_products?: number;
  stock_value?: string | number;
};

type BusinessSettings = {
  name?: string;
  owner_name?: string | null;
  owner_email?: string;
  business_type?: string;
  country?: string | null;
  phone?: string | null;
  address?: string | null;
  contact_email?: string | null;
  currency_code?: string;
  currency_symbol?: string;
  decimal_places?: number;
  tax_name?: string;
  tax_rate?: string | number;
  tax_inclusive?: boolean;
  receipt_header?: string | null;
  receipt_footer?: string | null;
  paper_size?: string;
  auto_print?: boolean;
  payment_methods?: string[];
};

type Props = {
  activeModule: PosModuleName;
  companyId: string;
  branchId: string;
  currencySymbol: string;
  decimalPlaces: number;
  onBackToSales: () => void;
};

function extractRows<T>(value: unknown): T[] {
  if (Array.isArray(value)) {
    return value as T[];
  }

  if (
    value &&
    typeof value === "object" &&
    "items" in value &&
    Array.isArray((value as { items?: unknown[] }).items)
  ) {
    return (value as { items: T[] }).items;
  }

  return [];
}

function harareDateValue(date: Date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Harare",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);

  const year =
    parts.find((part) => part.type === "year")?.value || "";
  const month =
    parts.find((part) => part.type === "month")?.value || "";
  const day =
    parts.find((part) => part.type === "day")?.value || "";

  return `${year}-${month}-${day}`;
}


function localDateValue(date: Date = new Date()) {
  const timezoneOffset = date.getTimezoneOffset() * 60_000;

  return new Date(date.getTime() - timezoneOffset)
    .toISOString()
    .slice(0, 10);
}

export default function PosModulePage({
  activeModule,
  companyId,
  branchId,
  currencySymbol,
  decimalPlaces,
  onBackToSales,
}: Props) {
  const [sales, setSales] = useState<Sale[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [settings, setSettings] = useState<BusinessSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [salesDate, setSalesDate] = useState(
    () => harareDateValue(),
  );
  function money(value: string | number | undefined) {
    return `${currencySymbol}${Number(value || 0).toFixed(decimalPlaces)}`;
  }

  useEffect(() => {
    let cancelled = false;

    async function loadModuleData() {
      if (!companyId || activeModule === "Sales") {
        return;
      }

      setLoading(true);
      setError("");

      try {
        if (activeModule === "Sales Management") {
          const response = await api.get(`/sales/history/${companyId}`, {
            params: {
              limit: 100,
              branch_id: branchId || undefined,
              sale_date: salesDate,
            },
          });

          if (!cancelled) {
            setSales(extractRows<Sale>(response.data));
          }
        }

        if (activeModule === "Products" || activeModule === "Inventory") {
          const response = await api.get(`/products/${companyId}`);

          if (!cancelled) {
            setProducts(extractRows<Product>(response.data));
          }
        }

        if (activeModule === "Reports") {
          const response = await api.get(
            `/dashboard/summary/${companyId}`,
          );

          if (!cancelled) {
            setSummary(response.data as DashboardSummary);
          }
        }

        if (activeModule === "Settings") {
          const response = await api.get(`/settings/${companyId}`);

          if (!cancelled) {
            setSettings(response.data as BusinessSettings);
          }
        }
      } catch (requestError: any) {
        if (!cancelled) {
          setError(
            requestError?.response?.data?.detail ||
              `Failed to load ${activeModule}`,
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadModuleData();

    return () => {
      cancelled = true;
    };
  }, [activeModule, companyId, branchId, salesDate]);

  const inventoryProducts = useMemo(() => {
    return [...products].sort(
      (first, second) =>
        Number(first.stock_qty || 0) - Number(second.stock_qty || 0),
    );
  }, [products]);

  if (activeModule === "Sales") {
    return null;
  }

  return (
    <section className="pos-module-overlay">
      <div className="pos-module-container">
        <header className="pos-module-header">
          <div>
            <p className="pos-module-eyebrow">ApexRetail POS</p>
            <h1>{activeModule}</h1>
            <p>Live information for the currently selected business.</p>
          </div>

          <button
            type="button"
            className="pos-module-sales-button"
            onClick={onBackToSales}
          >
            Return to Sales
          </button>
        </header>

        {loading && (
          <div className="pos-module-notice">Loading {activeModule}…</div>
        )}

        {error && (
          <div className="pos-module-notice pos-module-error">{error}</div>
        )}

        {!loading && !error && activeModule === "Sales Management" && (
          <div className="pos-module-card">
            <div className="pos-module-card-heading">
              <div>
                <h2>Sales History</h2>

              <div className="pos-module-date-filter">
                <label htmlFor="sales-history-date">
                  Transaction date
                </label>

                <div className="pos-module-date-actions">
                  <input
                    id="sales-history-date"
                    type="date"
                    value={salesDate}
                    max={localDateValue()}
                    onChange={(event) =>
                      setSalesDate(event.target.value)
                    }
                  />

                  <button
                    type="button"
                    onClick={() =>
                      setSalesDate(localDateValue())
                    }
                  >
                    Today
                  </button>
                </div>
              </div>

                
                <p>{sales.length} transaction records for {salesDate}</p>
              </div>

              

            </div>

            <div className="pos-module-table-wrap">
              <table className="pos-module-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Receipt</th>
                    <th>Cashier</th>
                    <th>Payment</th>
                    <th>Status</th>
                    <th className="number">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {sales.map((sale) => (
                    <tr key={sale.id}>
                      <td>
                        {sale.created_at
                          ? new Date(sale.created_at).toLocaleString()
                          : "—"}
                      </td>
                      <td>{sale.receipt_number || "—"}</td>
                      <td>{sale.cashier_name || "Unassigned"}</td>
                      <td>
                        {(sale.payment_method || "unknown").toUpperCase()}
                      </td>
                      <td>{sale.status || "completed"}</td>
                      <td className="number">
                        {money(sale.total_amount)}
                      </td>
                    </tr>
                  ))}

                  {!sales.length && (
                    <tr>
                      <td colSpan={6} className="empty">
                        No sales have been recorded.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!loading && !error && activeModule === "Products" && (
          <div className="pos-module-card">
            <div className="pos-module-card-heading">
              <div>
                <h2>Available Products</h2>
                <p>{products.length} products available on this POS</p>
              </div>
            </div>

            <div className="pos-module-table-wrap">
              <table className="pos-module-table">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>SKU</th>
                    <th>Barcode</th>
                    <th className="number">Selling Price</th>
                    <th className="number">Stock</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((product) => (
                    <tr key={product.id}>
                      <td>
                        <strong>{product.name}</strong>
                      </td>
                      <td>{product.sku || "—"}</td>
                      <td>{product.barcode || "—"}</td>
                      <td className="number">
                        {money(product.selling_price)}
                      </td>
                      <td className="number">
                        {Number(product.stock_qty || 0).toFixed(3)}
                      </td>
                      <td>
                        <span
                          className={
                            product.active === false
                              ? "pos-status inactive"
                              : "pos-status active"
                          }
                        >
                          {product.active === false ? "Inactive" : "Active"}
                        </span>
                      </td>
                    </tr>
                  ))}

                  {!products.length && (
                    <tr>
                      <td colSpan={6} className="empty">
                        No products are available.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!loading && !error && activeModule === "Inventory" && (
          <div className="pos-module-card">
            <div className="pos-module-card-heading">
              <div>
                <h2>Inventory Overview</h2>
                <p>Stock levels and reorder warnings</p>
              </div>
            </div>

            <div className="pos-module-table-wrap">
              <table className="pos-module-table">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>SKU</th>
                    <th className="number">Current Stock</th>
                    <th className="number">Reorder Level</th>
                    <th className="number">Cost Value</th>
                    <th>Stock Status</th>
                  </tr>
                </thead>
                <tbody>
                  {inventoryProducts.map((product) => {
                    const stock = Number(product.stock_qty || 0);
                    const reorderLevel = Number(product.reorder_level || 0);
                    const lowStock =
                      stock <= reorderLevel || stock <= 0;

                    return (
                      <tr key={product.id}>
                        <td>
                          <strong>{product.name}</strong>
                        </td>
                        <td>{product.sku || "—"}</td>
                        <td className="number">{stock.toFixed(3)}</td>
                        <td className="number">
                          {reorderLevel.toFixed(3)}
                        </td>
                        <td className="number">
                          {money(
                            stock * Number(product.cost_price || 0),
                          )}
                        </td>
                        <td>
                          <span
                            className={
                              lowStock
                                ? "pos-status low"
                                : "pos-status active"
                            }
                          >
                            {stock <= 0
                              ? "Out of stock"
                              : lowStock
                                ? "Low stock"
                                : "Available"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}

                  {!inventoryProducts.length && (
                    <tr>
                      <td colSpan={6} className="empty">
                        No inventory records are available.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!loading && !error && activeModule === "Reports" && (
          <>
            <div className="pos-report-grid">
              <ReportCard
                title="Today's Sales"
                value={money(summary?.today_sales)}
                detail="Completed transaction value"
              />
              <ReportCard
                title="Transactions"
                value={String(summary?.today_transactions || 0)}
                detail="Sales completed today"
              />
              <ReportCard
                title="Products"
                value={String(summary?.total_products || 0)}
                detail="Active product records"
              />
              <ReportCard
                title="Low Stock"
                value={String(summary?.low_stock_products || 0)}
                detail="Products requiring attention"
                warning
              />
              <ReportCard
                title="Stock Value"
                value={money(summary?.stock_value)}
                detail="Current inventory cost value"
              />
            </div>

            <div className="pos-module-card">
              <h2>Detailed Reports</h2>
              <p>
                Full date filtering, product performance, cashier
                performance, profit and inventory reports are available in
                Backoffice.
              </p>
            </div>
          </>
        )}

        {!loading && !error && activeModule === "Settings" && (
          <div className="pos-settings-grid">
            <SettingsCard
              title="Business"
              rows={[
                ["Business name", settings?.name || "—"],
                ["Owner", settings?.owner_name || "—"],
                ["Business type", settings?.business_type || "—"],
                ["Country", settings?.country || "—"],
                ["Phone", settings?.phone || "—"],
                ["Email", settings?.contact_email || settings?.owner_email || "—"],
                ["Address", settings?.address || "—"],
              ]}
            />

            <SettingsCard
              title="Currency and Tax"
              rows={[
                ["Currency", settings?.currency_code || "—"],
                ["Symbol", settings?.currency_symbol || "—"],
                [
                  "Decimal places",
                  String(settings?.decimal_places ?? 2),
                ],
                ["Tax name", settings?.tax_name || "—"],
                ["Tax rate", `${Number(settings?.tax_rate || 0)}%`],
                [
                  "Tax inclusive",
                  settings?.tax_inclusive ? "Yes" : "No",
                ],
              ]}
            />

            <SettingsCard
              title="Receipt and Payments"
              rows={[
                ["Paper size", settings?.paper_size || "—"],
                [
                  "Auto print",
                  settings?.auto_print ? "Enabled" : "Disabled",
                ],
                [
                  "Payment methods",
                  settings?.payment_methods?.join(", ").toUpperCase() ||
                    "—",
                ],
                ["Receipt header", settings?.receipt_header || "—"],
                ["Receipt footer", settings?.receipt_footer || "—"],
              ]}
            />

            <div className="pos-module-card">
              <h2>Manage Settings</h2>
              <p>
                Business settings are controlled from Backoffice so that
                all POS devices use the same configuration.
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function ReportCard({
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
      className={`pos-report-card${warning ? " warning" : ""}`}
    >
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function SettingsCard({
  title,
  rows,
}: {
  title: string;
  rows: Array<[string, string]>;
}) {
  return (
    <article className="pos-module-card">
      <h2>{title}</h2>

      <dl className="pos-settings-list">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}
