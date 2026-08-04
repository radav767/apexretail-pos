import { useEffect, useState } from "react";
import { api } from "./api/client";
import "./App.css";
import ProductsPage from "./pages/ProductsPage";
import InventoryPage from "./pages/InventoryPage";
import ShopsDevicesPage from "./pages/ShopsDevicesPage";
import EmployeesPage from "./pages/EmployeesPage";
import ReportsPage from "./pages/ReportsPage";
import SettingsPage from "./pages/SettingsPage";

type DashboardSummary = {
  today_sales: string;
  today_transactions: number;
  total_products: number;
  low_stock_products: number;
  stock_value: string;
};

type Sale = {
  id: string;
  receipt_number: string;
  total_amount: string;
  amount_received: string;
  change_due: string;
  payment_method: string;
  status: string;
  created_at: string;
};

const emptySummary: DashboardSummary = {
  today_sales: "0",
  today_transactions: 0,
  total_products: 0,
  low_stock_products: 0,
  stock_value: "0",
};

function App() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [loggedIn, setLoggedIn] = useState(
    Boolean(localStorage.getItem("backoffice_token")),
  );

  const [companyId, setCompanyId] = useState(
    localStorage.getItem("backoffice_company_id") || "",
  );

  const [summary, setSummary] = useState<DashboardSummary>(emptySummary);
  const [sales, setSales] = useState<Sale[]>([]);
  const [page, setPage] = useState<"dashboard" | "sales" | "products" | "inventory" | "devices" | "employees" | "reports" | "settings">("dashboard");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function login() {
    try {
      setLoading(true);
      setMessage("");

      const response = await api.post("/auth/login", {
        email,
        password,
      });

      localStorage.setItem(
        "backoffice_token",
        response.data.token,
      );

      localStorage.setItem(
        "backoffice_company_id",
        response.data.company_id,
      );

      setCompanyId(response.data.company_id);
      setLoggedIn(true);

      await loadBackofficeData(response.data.company_id);
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail || "Backoffice login failed",
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadBackofficeData(id = companyId) {
    if (!id) return;

    try {
      setLoading(true);
      setMessage("");

      const [summaryResponse, salesResponse] = await Promise.all([
        api.get(`/dashboard/summary/${id}`),
        api.get(`/sales/${id}?limit=100`),
      ]);

      setSummary(summaryResponse.data);
      setSales(salesResponse.data);
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to load Backoffice data",
      );
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    localStorage.removeItem("backoffice_token");
    localStorage.removeItem("backoffice_company_id");

    setLoggedIn(false);
    setCompanyId("");
    setSummary(emptySummary);
    setSales([]);
  }

  useEffect(() => {
    if (loggedIn && companyId) {
      void loadBackofficeData(companyId);
    }
  }, []);

  if (!loggedIn) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="logo-mark">A</div>

          <h1>ApexRetail Backoffice</h1>
          <p>Remote business management</p>

          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void login();
              }
            }}
          />

          <button
            className="primary-button"
            onClick={login}
            disabled={loading}
          >
            {loading ? "Signing in..." : "Login"}
          </button>

          <p className="error-message">{message}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="backoffice-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="logo-mark small">A</div>

          <div>
            <strong>ApexRetail</strong>
            <span>Backoffice</span>
          </div>
        </div>

        <nav>
          <button
            className={page === "dashboard" ? "active" : ""}
            onClick={() => setPage("dashboard")}
          >
            Dashboard
          </button>

          <button
            className={page === "sales" ? "active" : ""}
            onClick={() => setPage("sales")}
          >
            Sales History
          </button>

          <button
            className={page === "products" ? "active" : ""}
            onClick={() => setPage("products")}
          >
            Products
          </button>
          <button
            className={page === "inventory" ? "active" : ""}
            onClick={() => setPage("inventory")}
          >
            Inventory
          </button>
          <button
            className={page === "employees" ? "active" : ""}
            onClick={() => setPage("employees")}
          >
            Employees
          </button>
          <button
              className={page === "reports" ? "active" : ""}
              onClick={() => setPage("reports")}
            >
              Reports
            </button>
          <button
            className={page === "devices" ? "active" : ""}
            onClick={() => setPage("devices")}
          >
            Shops &amp; Devices
          </button>
          <button
          className={page === "settings" ? "active" : ""}
          onClick={() => setPage("settings")}
        >
          Settings
        </button>
        </nav>

        <button className="logout-button" onClick={logout}>
          Log out
        </button>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <h1>
              {page === "dashboard"
                ? "Business Dashboard"
                : page === "sales"
                  ? "Sales History"
                  : page === "products"
                    ? "Products & Categories"
                    : page === "inventory"
            ? "Inventory Management"
            : page === "employees"
              ? "Employees & Permissions"
              :
                  page === "reports"
                    ? "Sales Reports"
                    : page === "settings"
                    ? "Business Settings"
                    : "Shops & Devices"}
            </h1>

            <p>Live data from ApexRetail POS</p>
          </div>

          <button
            className="refresh-button"
            onClick={() => loadBackofficeData()}
            disabled={loading}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </header>

        {page === "dashboard" && (
          <>
            <section className="summary-grid">
              <SummaryCard
                title="Today's Sales"
                value={`$${Number(summary.today_sales).toFixed(2)}`}
                detail="Completed transactions"
              />

              <SummaryCard
                title="Transactions"
                value={String(summary.today_transactions)}
                detail="Sales completed today"
              />

              <SummaryCard
                title="Products"
                value={String(summary.total_products)}
                detail="Active products"
              />

              <SummaryCard
                title="Stock Value"
                value={`$${Number(summary.stock_value).toFixed(2)}`}
                detail="Based on cost price"
              />

              <SummaryCard
                title="Low Stock"
                value={String(summary.low_stock_products)}
                detail="Require attention"
                warning={summary.low_stock_products > 0}
              />
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Recent Sales</h2>
                  <p>Latest transactions received from the POS</p>
                </div>

                <button onClick={() => setPage("sales")}>
                  View all
                </button>
              </div>

              <SalesTable sales={sales.slice(0, 8)} />
            </section>
          </>
        )}

        {page === "sales" && (
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>Sales and Receipts</h2>
                <p>{sales.length} transaction records loaded</p>
              </div>
            </div>

            <SalesTable sales={sales} />
          </section>
        )}


        {page === "products" && (
          <ProductsPage
            companyId={companyId}
            onDataChanged={() =>
              void loadBackofficeData(companyId)
            }
          />
        )}


        {page === "inventory" && (
          <InventoryPage
            companyId={companyId}
            onDataChanged={() =>
              void loadBackofficeData(companyId)
            }
          />
        )}
        {page === "employees" && (
          <EmployeesPage companyId={companyId} />
        )}

        {page === "reports" && (
          <ReportsPage companyId={companyId} />
        )}




        {page === "settings" && (
          <SettingsPage
            companyId={companyId}
            onDataChanged={() =>
              void loadBackofficeData(companyId)
            }
          />
        )}

        {page === "devices" && (
          <ShopsDevicesPage companyId={companyId} />
        )}

        <p className="status-message">{message}</p>
      </main>
    </div>
  );
}

function SummaryCard({
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
    <article className={`summary-card ${warning ? "warning" : ""}`}>
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function SalesTable({ sales }: { sales: Sale[] }) {
  if (!sales.length) {
    return <div className="empty-state">No sales found yet.</div>;
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Receipt</th>
            <th>Date</th>
            <th>Payment</th>
            <th>Total</th>
            <th>Received</th>
            <th>Change</th>
            <th>Status</th>
          </tr>
        </thead>

        <tbody>
          {sales.map((sale) => (
            <tr key={sale.id}>
              <td className="receipt-number">
                {sale.receipt_number}
              </td>

              <td>
                {new Date(sale.created_at).toLocaleString()}
              </td>

              <td>
                <span className="payment-badge">
                  {sale.payment_method.toUpperCase()}
                </span>
              </td>

              <td>${Number(sale.total_amount).toFixed(2)}</td>

              <td>
                ${Number(sale.amount_received).toFixed(2)}
              </td>

              <td>${Number(sale.change_due).toFixed(2)}</td>

              <td>
                <span className="status-badge">
                  {sale.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
