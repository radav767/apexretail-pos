import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import "./App.css";
import {
  type DashboardPhase2Summary,
  type DashboardRangeKey,
} from "./dashboard";
import { DashboardPanel } from "./DashboardPanel";
import ProductsPage from "./pages/ProductsPage";
import InventoryPage from "./pages/InventoryPage";
import ShopsDevicesPage from "./pages/ShopsDevicesPage";
import EmployeesPage from "./pages/EmployeesPage";
import ReportsPage from "./pages/ReportsPage";
import SettingsPage from "./pages/SettingsPage";

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

function localDateValue(date: Date): string {
  const adjusted = new Date(
    date.getTime() - date.getTimezoneOffset() * 60_000,
  );

  return adjusted.toISOString().slice(0, 10);
}

function App() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [loggedIn, setLoggedIn] = useState(
    Boolean(localStorage.getItem("backoffice_token")),
  );
  const [companyId, setCompanyId] = useState(
    localStorage.getItem("backoffice_company_id") || "",
  );
  const [dashboardSummary, setDashboardSummary] =
    useState<DashboardPhase2Summary | null>(null);
  const [sales, setSales] = useState<Sale[]>([]);
  const [dashboardShops, setDashboardShops] = useState<DashboardPhase2Summary["shops"]>([]);
  const [page, setPage] = useState<
    | "dashboard"
    | "sales"
    | "products"
    | "inventory"
    | "devices"
    | "employees"
    | "reports"
    | "settings"
  >("dashboard");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const dashboardRequest = useRef(0);
  const [rangeKey, setRangeKey] =
    useState<DashboardRangeKey>("today");
  const [selectedShopId, setSelectedShopId] = useState("");
  const [customDateFrom, setCustomDateFrom] = useState(
    localDateValue(new Date()),
  );
  const [customDateTo, setCustomDateTo] = useState(
    localDateValue(new Date()),
  );

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

    } catch (error: any) {
      setMessage(
        error.response?.data?.detail || "Backoffice login failed",
      );
    } finally {
      setLoading(false);
    }
  }

  const loadRecentSales = useCallback(async (id: string) => {
    if (!id) {
      return;
    }

    const salesResponse = await api.get(`/sales/${id}?limit=100`);
    setSales(salesResponse.data);
  }, []);

  const loadDashboardSummary = useCallback(
    async (id: string) => {
      if (!id) {
        return;
      }

      const requestId = ++dashboardRequest.current;
      setDashboardSummary(null);
      if (rangeKey === "custom" && (!customDateFrom || !customDateTo || customDateFrom > customDateTo)) {
        setDashboardLoading(false);
        setMessage("Choose a start date and an end date on or after it");
        return;
      }

      try {
        setDashboardLoading(true);
        setMessage("");

        const response = await api.get(
          `/dashboard/summary-v2/${id}`,
          {
            params: {
              range_key: rangeKey,
              shop_id: selectedShopId || undefined,
              date_from:
                rangeKey === "custom"
                  ? customDateFrom
                  : undefined,
              date_to:
                rangeKey === "custom"
                  ? customDateTo
                  : undefined,
            },
          },
        );

        if (requestId !== dashboardRequest.current) return;
        setDashboardSummary(response.data);
        setDashboardShops(response.data.shops);
      } catch (error: any) {
        if (requestId !== dashboardRequest.current) return;
        setDashboardSummary(null);
        setMessage(
          error.response?.data?.detail ||
            "Failed to load dashboard summary",
        );
      } finally {
        if (requestId === dashboardRequest.current) setDashboardLoading(false);
      }
    },
    [rangeKey, selectedShopId, customDateFrom, customDateTo],
  );

  const loadBackofficeData = useCallback(
    async (id: string) => {
      if (!id) {
        return;
      }

      try {
        setLoading(true);
        setMessage("");

        await Promise.all([
          loadRecentSales(id),
          loadDashboardSummary(id),
        ]);
      } catch (error: any) {
        setMessage(
          error.response?.data?.detail ||
            "Failed to load Backoffice data",
        );
      } finally {
        setLoading(false);
      }
    },
    [loadDashboardSummary, loadRecentSales],
  );

  function logout() {
    localStorage.removeItem("backoffice_token");
    localStorage.removeItem("backoffice_company_id");

    dashboardRequest.current += 1;
    setDashboardLoading(false);
    setSelectedShopId("");
    setDashboardShops([]);
    setMobileMenuOpen(false);
    setLoggedIn(false);
    setCompanyId("");
    setDashboardSummary(null);
    setSales([]);
  }

  function navigateTo(nextPage: typeof page) {
    setPage(nextPage);
    setMobileMenuOpen(false);
  }

  useEffect(() => {
    if (loggedIn && companyId) {
      void loadRecentSales(companyId).catch(() => {
        setMessage("Failed to load recent sales");
      });
    }
  }, [loggedIn, companyId, loadRecentSales]);

  useEffect(() => {
    if (loggedIn && companyId) {
      void loadDashboardSummary(companyId);
    }
    return () => { dashboardRequest.current += 1; };
  }, [loggedIn, companyId, loadDashboardSummary]);

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
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <div className="logo-mark small">A</div>

            <div>
              <strong>ApexRetail</strong>
              <span>Backoffice</span>
            </div>
          </div>

          <button
            className="mobile-menu-toggle"
            type="button"
            aria-expanded={mobileMenuOpen}
            aria-controls="backoffice-navigation"
            onClick={() => setMobileMenuOpen((open) => !open)}
          >
            Menu
          </button>
        </div>

        <nav
          id="backoffice-navigation"
          className={mobileMenuOpen ? "mobile-open" : ""}
        >
          <button
            className={page === "dashboard" ? "active" : ""}
            onClick={() => navigateTo("dashboard")}
          >
            Dashboard
          </button>

          <button
            className={page === "sales" ? "active" : ""}
            onClick={() => navigateTo("sales")}
          >
            Sales History
          </button>

          <button
            className={page === "products" ? "active" : ""}
            onClick={() => navigateTo("products")}
          >
            Products
          </button>
          <button
            className={page === "inventory" ? "active" : ""}
            onClick={() => navigateTo("inventory")}
          >
            Inventory
          </button>
          <button
            className={page === "employees" ? "active" : ""}
            onClick={() => navigateTo("employees")}
          >
            Employees
          </button>
          <button
            className={page === "reports" ? "active" : ""}
            onClick={() => navigateTo("reports")}
          >
            Reports
          </button>
          <button
            className={page === "devices" ? "active" : ""}
            onClick={() => navigateTo("devices")}
          >
            Devices/POS
          </button>
          <button
            className={page === "settings" ? "active" : ""}
            onClick={() => navigateTo("settings")}
          >
            Settings
          </button>
          <button
            className="logout-nav-button"
            type="button"
            onClick={logout}
          >
            Log out
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
                        : page === "reports"
                          ? "Sales Reports"
                          : page === "settings"
                            ? "Business Settings"
                            : "Shops & Devices"}
            </h1>

            <p>Live data from ApexRetail POS</p>
          </div>

          <button
            className="refresh-button"
            onClick={() => loadBackofficeData(companyId)}
            disabled={loading || dashboardLoading}
          >
            {loading || dashboardLoading ? "Loading..." : "Refresh"}
          </button>
        </header>

        {page === "dashboard" && (
          <DashboardPanel
            summary={dashboardSummary}
            shops={dashboardShops}
            rangeKey={rangeKey}
            selectedShopId={selectedShopId}
            customDateFrom={customDateFrom}
            customDateTo={customDateTo}
            onRangeChange={setRangeKey}
            onShopChange={setSelectedShopId}
            onDateFromChange={setCustomDateFrom}
            onDateToChange={setCustomDateTo}
          />
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
            onDataChanged={() => void loadBackofficeData(companyId)}
          />
        )}

        {page === "inventory" && (
          <InventoryPage
            companyId={companyId}
            onDataChanged={() => void loadBackofficeData(companyId)}
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
            onDataChanged={() => void loadBackofficeData(companyId)}
          />
        )}

        {page === "devices" && (
          <ShopsDevicesPage companyId={companyId} />
        )}

        <p className="status-message">
          {message ||
            (dashboardLoading
              ? "Updating dashboard summary..."
              : "")}
        </p>
      </main>
    </div>
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

              <td>{new Date(sale.created_at).toLocaleString()}</td>

              <td>
                <span className="payment-badge">
                  {sale.payment_method.toUpperCase()}
                </span>
              </td>

              <td>${Number(sale.total_amount).toFixed(2)}</td>

              <td>${Number(sale.amount_received).toFixed(2)}</td>

              <td>${Number(sale.change_due).toFixed(2)}</td>

              <td>
                <span className="status-badge">{sale.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
