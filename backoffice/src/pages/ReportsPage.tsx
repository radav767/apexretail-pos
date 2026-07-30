import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import "./reports.css";

type ReportRow = Record<string, unknown>;

type SalesReport = {
  date_from?: string;
  date_to?: string;
  summary?: ReportRow;
  totals?: ReportRow;
  payment_methods?: ReportRow[];
  cashiers?: ReportRow[];
  products?: ReportRow[];
  branches?: ReportRow[];
  [key: string]: unknown;
};

type ReportsPageProps = {
  companyId: string;
};

function localDateValue(date: Date): string {
  const adjusted = new Date(
    date.getTime() - date.getTimezoneOffset() * 60_000,
  );

  return adjusted.toISOString().slice(0, 10);
}

function numberValue(value: unknown): number | undefined {
  if (value === null || value === undefined || value === "") {
    return undefined;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function firstNumber(...values: unknown[]): number | undefined {
  for (const value of values) {
    const parsed = numberValue(value);

    if (parsed !== undefined) {
      return parsed;
    }
  }

  return undefined;
}

function textValue(value: unknown, fallback = ""): string {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }

  return String(value);
}

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

export default function ReportsPage({
  companyId,
}: ReportsPageProps) {
  const today = useMemo(() => new Date(), []);

  const firstDayOfMonth = useMemo(
    () => new Date(today.getFullYear(), today.getMonth(), 1),
    [today],
  );

  const [dateFrom, setDateFrom] = useState(
    localDateValue(firstDayOfMonth),
  );

  const [dateTo, setDateTo] = useState(localDateValue(today));
  const [report, setReport] = useState<SalesReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function loadReport() {
    if (!companyId) {
      return;
    }

    if (dateFrom > dateTo) {
      setMessage("Start date cannot be after the end date");
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      const response = await api.get(
        `/reports/sales/${companyId}`,
        {
          params: {
            date_from: dateFrom,
            date_to: dateTo,
          },
        },
      );

      setReport(response.data);
    } catch (error: any) {
      setReport(null);
      setMessage(
        error.response?.data?.detail ||
          "Failed to load the sales report",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadReport();
  }, [companyId]);

  const cashiers = Array.isArray(report?.cashiers)
    ? report.cashiers
    : [];

  const products = Array.isArray(report?.products)
    ? report.products
    : [];

  const paymentMethods = Array.isArray(report?.payment_methods)
    ? report.payment_methods
    : [];

  const branches = Array.isArray(report?.branches)
    ? report.branches
    : [];

  const calculated = useMemo(() => {
    const summary =
      report?.summary && typeof report.summary === "object"
        ? report.summary
        : report?.totals && typeof report.totals === "object"
          ? report.totals
          : report || {};

    const cashierTransactions = cashiers.reduce(
      (total, row) =>
        total + (numberValue(row.transactions) || 0),
      0,
    );

    const cashierSales = cashiers.reduce(
      (total, row) => total + (numberValue(row.sales) || 0),
      0,
    );

    const cashierCost = cashiers.reduce(
      (total, row) => total + (numberValue(row.cost) || 0),
      0,
    );

    const productSales = products.reduce(
      (total, row) => total + (numberValue(row.sales) || 0),
      0,
    );

    const productCost = products.reduce(
      (total, row) => total + (numberValue(row.cost) || 0),
      0,
    );

    const transactions =
      firstNumber(
        summary.transactions,
        summary.total_transactions,
        report?.transactions,
      ) ?? cashierTransactions;

    const sales =
      firstNumber(
        summary.sales,
        summary.total_sales,
        summary.gross_sales,
        report?.sales,
        report?.total_sales,
      ) ??
      cashierSales ??
      productSales;

    const cost =
      firstNumber(
        summary.cost,
        summary.total_cost,
        summary.cost_of_sales,
        report?.cost,
        report?.total_cost,
      ) ??
      cashierCost ??
      productCost;

    const profit =
      firstNumber(
        summary.profit,
        summary.gross_profit,
        report?.profit,
      ) ?? sales - cost;

    const averageSale =
      transactions > 0 ? sales / transactions : 0;

    return {
      transactions,
      sales,
      cost,
      profit,
      averageSale,
    };
  }, [report, cashiers, products]);

  function setToday() {
    const value = localDateValue(new Date());
    setDateFrom(value);
    setDateTo(value);
  }

  function setThisMonth() {
    const current = new Date();

    setDateFrom(
      localDateValue(
        new Date(current.getFullYear(), current.getMonth(), 1),
      ),
    );

    setDateTo(localDateValue(current));
  }

  function setLastThirtyDays() {
    const end = new Date();
    const start = new Date();

    start.setDate(start.getDate() - 29);

    setDateFrom(localDateValue(start));
    setDateTo(localDateValue(end));
  }

  return (
    <div className="reports-page">
      <section className="reports-toolbar">
        <div>
          <h2>Sales Report</h2>
          <p>
            Review sales, costs, profits, cashiers and product
            performance.
          </p>
        </div>

        <div className="reports-date-fields">
          <label>
            Date from
            <input
              type="date"
              value={dateFrom}
              onChange={(event) =>
                setDateFrom(event.target.value)
              }
            />
          </label>

          <label>
            Date to
            <input
              type="date"
              value={dateTo}
              onChange={(event) =>
                setDateTo(event.target.value)
              }
            />
          </label>

          <button
            className="reports-primary-button"
            onClick={() => void loadReport()}
            disabled={loading}
          >
            {loading ? "Loading..." : "Run Report"}
          </button>
        </div>

        <div className="reports-presets">
          <button onClick={setToday}>Today</button>
          <button onClick={setThisMonth}>This Month</button>
          <button onClick={setLastThirtyDays}>
            Last 30 Days
          </button>
          <button onClick={() => window.print()}>
            Print Report
          </button>
        </div>
      </section>

      {message && (
        <p className="reports-message">{message}</p>
      )}

      <section className="reports-summary-grid">
        <article>
          <span>Total Sales</span>
          <strong>{currency.format(calculated.sales)}</strong>
          <small>Gross sales for the selected period</small>
        </article>

        <article>
          <span>Transactions</span>
          <strong>{calculated.transactions}</strong>
          <small>Completed sales</small>
        </article>

        <article>
          <span>Cost of Sales</span>
          <strong>{currency.format(calculated.cost)}</strong>
          <small>Recorded product cost</small>
        </article>

        <article>
          <span>Gross Profit</span>
          <strong>{currency.format(calculated.profit)}</strong>
          <small>Sales less product cost</small>
        </article>

        <article>
          <span>Average Sale</span>
          <strong>
            {currency.format(calculated.averageSale)}
          </strong>
          <small>Average transaction value</small>
        </article>
      </section>

      <section className="reports-panel">
        <div className="reports-panel-header">
          <div>
            <h2>Cashier Performance</h2>
            <p>Sales attributed to each employee.</p>
          </div>
        </div>

        <div className="reports-table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Cashier</th>
                <th>Transactions</th>
                <th>Sales</th>
                <th>Cost</th>
                <th>Profit</th>
              </tr>
            </thead>

            <tbody>
              {!cashiers.length ? (
                <tr>
                  <td colSpan={5} className="reports-empty">
                    No cashier data for this period.
                  </td>
                </tr>
              ) : (
                cashiers.map((cashier, index) => (
                  <tr
                    key={
                      textValue(cashier.employee_id) ||
                      `cashier-${index}`
                    }
                  >
                    <td>
                      <strong>
                        {textValue(
                          cashier.cashier_name,
                          "Unassigned",
                        )}
                      </strong>
                    </td>

                    <td>
                      {numberValue(cashier.transactions) || 0}
                    </td>

                    <td>
                      {currency.format(
                        numberValue(cashier.sales) || 0,
                      )}
                    </td>

                    <td>
                      {currency.format(
                        numberValue(cashier.cost) || 0,
                      )}
                    </td>

                    <td>
                      {currency.format(
                        numberValue(cashier.profit) || 0,
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="reports-panel">
        <div className="reports-panel-header">
          <div>
            <h2>Product Performance</h2>
            <p>Quantity sold, revenue, cost and profit.</p>
          </div>
        </div>

        <div className="reports-table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Quantity</th>
                <th>Sales</th>
                <th>Cost</th>
                <th>Profit</th>
              </tr>
            </thead>

            <tbody>
              {!products.length ? (
                <tr>
                  <td colSpan={5} className="reports-empty">
                    No product sales for this period.
                  </td>
                </tr>
              ) : (
                products.map((product, index) => (
                  <tr
                    key={
                      textValue(product.product_id) ||
                      `product-${index}`
                    }
                  >
                    <td>
                      <strong>
                        {textValue(
                          product.product_name,
                          "Unknown product",
                        )}
                      </strong>
                    </td>

                    <td>
                      {Number(
                        numberValue(product.quantity) || 0,
                      ).toFixed(3)}
                    </td>

                    <td>
                      {currency.format(
                        numberValue(product.sales) || 0,
                      )}
                    </td>

                    <td>
                      {currency.format(
                        numberValue(product.cost) || 0,
                      )}
                    </td>

                    <td>
                      {currency.format(
                        numberValue(product.profit) || 0,
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {paymentMethods.length > 0 && (
        <section className="reports-panel">
          <div className="reports-panel-header">
            <div>
              <h2>Payment Methods</h2>
              <p>Sales grouped by payment method.</p>
            </div>
          </div>

          <div className="reports-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Method</th>
                  <th>Transactions</th>
                  <th>Sales</th>
                  <th>Profit</th>
                </tr>
              </thead>

              <tbody>
                {paymentMethods.map((method, index) => (
                  <tr key={`method-${index}`}>
                    <td>
                      <strong>
                        {textValue(
                          method.payment_method,
                          "Unknown",
                        ).toUpperCase()}
                      </strong>
                    </td>

                    <td>
                      {numberValue(method.transactions) || 0}
                    </td>

                    <td>
                      {currency.format(
                        numberValue(method.sales) || 0,
                      )}
                    </td>

                    <td>
                      {currency.format(
                        numberValue(method.profit) || 0,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {branches.length > 0 && (
        <section className="reports-panel">
          <div className="reports-panel-header">
            <div>
              <h2>Branch Performance</h2>
              <p>Sales grouped by shop branch.</p>
            </div>
          </div>

          <div className="reports-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Branch</th>
                  <th>Transactions</th>
                  <th>Sales</th>
                  <th>Profit</th>
                </tr>
              </thead>

              <tbody>
                {branches.map((branch, index) => (
                  <tr
                    key={
                      textValue(branch.branch_id) ||
                      `branch-${index}`
                    }
                  >
                    <td>
                      <strong>
                        {textValue(
                          branch.branch_name,
                          "Unknown branch",
                        )}
                      </strong>
                    </td>

                    <td>
                      {numberValue(branch.transactions) || 0}
                    </td>

                    <td>
                      {currency.format(
                        numberValue(branch.sales) || 0,
                      )}
                    </td>

                    <td>
                      {currency.format(
                        numberValue(branch.profit) || 0,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
