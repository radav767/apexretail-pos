import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import "./App.css";
import {
  type DashboardDrilldown,
  type DashboardDrilldownRequest,
  type DashboardPhase3Summary,
  type DashboardRangeKey,
} from "./dashboard";
import { DashboardPanel, type ExportSection } from "./DashboardPanel";
import { DashboardDrilldownDialog } from "./DashboardDrilldownDialog";
import ProductsPage from "./pages/ProductsPage";
import InventoryPage from "./pages/InventoryPage";
import ShopsDevicesPage from "./pages/ShopsDevicesPage";
import EmployeesPage from "./pages/EmployeesPage";
import ReportsPage from "./pages/ReportsPage";
import SalesHistoryPage from "./pages/SalesHistoryPage";
import SettingsPage from "./pages/SettingsPage";
import CustomersPage from "./pages/CustomersPage";
import CreditSettlementsPage from "./pages/CreditSettlementsPage";
import ExpensesPage from "./pages/ExpensesPage";
import ShiftReportsPage from "./pages/ShiftReportsPage";
import { AppIcon } from "./components/AppIcon";

type BackofficePage =
  | "dashboard"
  | "sales"
  | "products"
  | "inventory"
  | "devices"
  | "employees"
  | "reports"
  | "customers"
  | "credit-settlements"
  | "expenses"
  | "shift-reports"
  | "settings";

function initialBackofficePage(): BackofficePage {
  const requested = new URLSearchParams(window.location.search).get("page");
  return (["dashboard", "sales", "products", "inventory", "devices", "employees", "reports", "customers", "credit-settlements", "expenses", "shift-reports", "settings"] as BackofficePage[])
    .includes(requested as BackofficePage) ? requested as BackofficePage : "dashboard";
}

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
    useState<DashboardPhase3Summary | null>(null);
  const [dashboardShops, setDashboardShops] = useState<DashboardPhase3Summary["shops"]>([]);
  const [granularity, setGranularity] = useState<"day" | "week" | "month">("day");
  const [page, setPage] = useState<BackofficePage>(initialBackofficePage);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const dashboardRequest = useRef(0);
  const drilldownRequestId = useRef(0);
  const [rangeKey, setRangeKey] =
    useState<DashboardRangeKey>("today");
  const [selectedShopId, setSelectedShopId] = useState("");
  const [customDateFrom, setCustomDateFrom] = useState(
    localDateValue(new Date()),
  );
  const [customDateTo, setCustomDateTo] = useState(
    localDateValue(new Date()),
  );
  const [drilldownRequest, setDrilldownRequest] =
    useState<DashboardDrilldownRequest | null>(null);
  const [drilldownData, setDrilldownData] =
    useState<DashboardDrilldown | null>(null);
  const [drilldownLoading, setDrilldownLoading] = useState(false);
  const [drilldownError, setDrilldownError] = useState("");

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
        const thisMonthStart = localDateValue(
          new Date(new Date().getFullYear(), new Date().getMonth(), 1),
        );
        const apiRangeKey = rangeKey === "this_month" ? "custom" : rangeKey;
        const apiDateFrom = rangeKey === "this_month" ? thisMonthStart : customDateFrom;
        const apiDateTo = rangeKey === "this_month" ? localDateValue(new Date()) : customDateTo;

        const response = await api.get(
          `/dashboard/analytics-v3/${id}`,
          {
            params: {
              range_key: apiRangeKey,
              granularity,
              shop_id: selectedShopId || undefined,
              date_from:
                apiRangeKey === "custom"
                  ? apiDateFrom
                  : undefined,
              date_to:
                apiRangeKey === "custom"
                  ? apiDateTo
                  : undefined,
            },
          },
        );

        if (requestId !== dashboardRequest.current) return;
        const financialResponse = await api.get(
          `/reports/financial-summary/${id}`,
          {
            params: {
              date_from: response.data.date_from,
              date_to: response.data.date_to,
              shop_id: selectedShopId || undefined,
            },
          },
        );

        if (requestId !== dashboardRequest.current) return;
        setDashboardSummary({
          ...response.data,
          financial_summary: financialResponse.data,
        });
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
    [rangeKey, granularity, selectedShopId, customDateFrom, customDateTo],
  );

  const dashboardParams = useCallback(() => {
    const thisMonthStart = localDateValue(
      new Date(new Date().getFullYear(), new Date().getMonth(), 1),
    );
    const apiRangeKey = rangeKey === "this_month" ? "custom" : rangeKey;
    return {
      range_key: apiRangeKey,
      granularity,
      shop_id: selectedShopId || undefined,
      date_from: apiRangeKey === "custom"
        ? (rangeKey === "this_month" ? thisMonthStart : customDateFrom)
        : undefined,
      date_to: apiRangeKey === "custom"
        ? (rangeKey === "this_month" ? localDateValue(new Date()) : customDateTo)
        : undefined,
    };
  }, [rangeKey, granularity, selectedShopId, customDateFrom, customDateTo]);

  const drilldownParams = useCallback((request: DashboardDrilldownRequest) => ({
    ...dashboardParams(),
    ...(request.dateFrom && request.dateTo
      ? {
          range_key: "custom",
          date_from: request.dateFrom,
          date_to: request.dateTo,
        }
      : {}),
    metric: request.metric,
    dimension: request.dimension,
    dimension_key: request.dimensionKey,
  }), [dashboardParams]);

  async function readApiError(error: any, fallback: string) {
    const responseData = error?.response?.data;
    if (responseData instanceof Blob) {
      try {
        const parsed = JSON.parse(await responseData.text());
        return parsed?.detail || fallback;
      } catch {
        return fallback;
      }
    }
    return responseData?.detail || fallback;
  }

  async function loadDashboardDrilldown(
    request: DashboardDrilldownRequest,
    offset = 0,
  ) {
    const requestId = ++drilldownRequestId.current;
    setDrilldownLoading(true);
    setDrilldownError("");
    try {
      const response = await api.get(
        `/dashboard/analytics-v3/${companyId}/sales`,
        { params: { ...drilldownParams(request), limit: 25, offset } },
      );
      if (requestId === drilldownRequestId.current) {
        setDrilldownData(response.data);
      }
    } catch (error: any) {
      if (requestId === drilldownRequestId.current) {
        setDrilldownData(null);
        setDrilldownError(
          error?.response?.status === 403
            ? "You do not have reports permission for these contributing sales."
            : await readApiError(error, "Failed to load contributing sales"),
        );
      }
    } finally {
      if (requestId === drilldownRequestId.current) {
        setDrilldownLoading(false);
      }
    }
  }

  function openDashboardDrilldown(request: DashboardDrilldownRequest) {
    setDrilldownRequest(request);
    setDrilldownData(null);
    void loadDashboardDrilldown(request);
  }

  function closeDashboardDrilldown() {
    drilldownRequestId.current += 1;
    setDrilldownRequest(null);
    setDrilldownData(null);
    setDrilldownError("");
    setDrilldownLoading(false);
  }

  async function exportDashboardDrilldown() {
    if (!drilldownRequest) return;
    try {
      setDrilldownError("");
      const response = await api.get(
        `/dashboard/analytics-v3/${companyId}/sales.csv`,
        {
          params: drilldownParams(drilldownRequest),
          responseType: "blob",
        },
      );
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = "dashboard-contributing-sales.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error: any) {
      setDrilldownError(
        error?.response?.status === 403
          ? "You do not have reports permission to export these sales."
          : await readApiError(error, "Failed to export contributing sales"),
      );
    }
  }

  async function exportDashboard(section: ExportSection) {
    try {
      setMessage("");
      const response = await api.get(`/dashboard/analytics-v3/${companyId}/export.csv`, {
        params: { ...dashboardParams(), section }, responseType: "blob",
      });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `dashboard-${section}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error: any) {
      setMessage(error.response?.data?.detail || "Failed to export dashboard CSV");
    }
  }

  const loadBackofficeData = useCallback(
    async (id: string) => {
      if (!id) {
        return;
      }

      try {
        setLoading(true);
        setMessage("");

        await Promise.all([
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
    [loadDashboardSummary],
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
    closeDashboardDrilldown();
  }

  function navigateTo(nextPage: typeof page) {
    setPage(nextPage);
    const url = new URL(window.location.href);
    url.searchParams.set("page", nextPage);
    window.history.replaceState(null, "", url);
    setMobileMenuOpen(false);
    closeDashboardDrilldown();
  }

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
            <AppIcon name="menu" /> Menu
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
            <AppIcon name="dashboard" /> <span>Dashboard</span>
          </button>

          <span className="nav-section-label">Sales management</span>

          <button
            className={page === "sales" ? "active" : ""}
            onClick={() => navigateTo("sales")}
          >
            <AppIcon name="sales" /> <span>Sales History</span>
          </button>
          <button
            className={page === "shift-reports" ? "active" : ""}
            onClick={() => navigateTo("shift-reports")}
          >
            <AppIcon name="shifts" /> <span>Cashier Shifts</span>
          </button>
          <button
            className={`${page === "customers" ? "active" : ""} customers-nav-button`.trim()}
            onClick={() => navigateTo("customers")}
          >
            <AppIcon name="customers" /> <span>Customer Accounts</span>
          </button>
          <button
            className={`${page === "credit-settlements" ? "active" : ""} credit-settlements-nav-button`.trim()}
            onClick={() => navigateTo("credit-settlements")}
          >
            <AppIcon name="credit" /> <span>Credit Management</span>
          </button>
          <button
            className={`${page === "expenses" ? "active" : ""} expenses-nav-button`.trim()}
            onClick={() => navigateTo("expenses")}
          >
            <AppIcon name="expenses" /> <span>Expenses</span>
          </button>

          <span className="nav-section-label">Catalogue & operations</span>
          <button
            className={page === "products" ? "active" : ""}
            onClick={() => navigateTo("products")}
          >
            <AppIcon name="products" /> <span>Products</span>
          </button>
          <button
            className={page === "inventory" ? "active" : ""}
            onClick={() => navigateTo("inventory")}
          >
            <AppIcon name="inventory" /> <span>Inventory</span>
          </button>
          <button
            className={page === "reports" ? "active" : ""}
            onClick={() => navigateTo("reports")}
          >
            <AppIcon name="reports" /> <span>Reports</span>
          </button>
          <button
            className={page === "devices" ? "active" : ""}
            onClick={() => navigateTo("devices")}
          >
            <AppIcon name="devices" /> <span>Shops & Devices</span>
          </button>

          <span className="nav-section-label">People & settings</span>
          <button
            className={page === "employees" ? "active" : ""}
            onClick={() => navigateTo("employees")}
          >
            <AppIcon name="employees" /> <span>Employees</span>
          </button>
          <button
            className={page === "settings" ? "active" : ""}
            onClick={() => navigateTo("settings")}
          >
            <AppIcon name="settings" /> <span>Settings</span>
          </button>
          <button
            className="logout-nav-button"
            type="button"
            onClick={logout}
          >
            <AppIcon name="logout" /> <span>Log out</span>
          </button>
        </nav>

        <button className="logout-button" onClick={logout}>
          <AppIcon name="logout" /> <span>Log out</span>
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
                          : page === "customers"
                            ? "Customer Accounts & Statements"
                            : page === "credit-settlements"
                              ? "Outstanding Credit & Settlements"
                              : page === "expenses"
                                ? "Expense Reports & Categories"
                                : page === "shift-reports"
                                  ? "Cashier Shift Reports"
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
            <AppIcon name="refresh" />
            {loading || dashboardLoading ? "Loading..." : "Refresh"}
          </button>
        </header>

        {page === "dashboard" && (
          <DashboardPanel
            summary={dashboardSummary}
            shops={dashboardShops}
            rangeKey={rangeKey}
            granularity={granularity}
            selectedShopId={selectedShopId}
            customDateFrom={customDateFrom}
            customDateTo={customDateTo}
            onRangeChange={(value) => { closeDashboardDrilldown(); setRangeKey(value); }}
            onGranularityChange={(value) => { closeDashboardDrilldown(); setGranularity(value); }}
            onShopChange={(value) => { closeDashboardDrilldown(); setSelectedShopId(value); }}
            onDateFromChange={(value) => { closeDashboardDrilldown(); setCustomDateFrom(value); }}
            onDateToChange={(value) => { closeDashboardDrilldown(); setCustomDateTo(value); }}
            onExport={(section) => void exportDashboard(section)}
            onOpenDrilldown={openDashboardDrilldown}
            onNavigateFinancial={navigateTo}
          />
        )}

        {page === "dashboard" && drilldownRequest && (
          <DashboardDrilldownDialog
            request={drilldownRequest}
            data={drilldownData}
            loading={drilldownLoading}
            error={drilldownError}
            currencySymbol={dashboardSummary?.currency_symbol || "$"}
            decimalPlaces={dashboardSummary?.decimal_places ?? 2}
            reportingTimezone={dashboardSummary?.reporting_timezone || "Africa/Harare"}
            onClose={closeDashboardDrilldown}
            onPage={(offset) => void loadDashboardDrilldown(drilldownRequest, offset)}
            onExport={() => void exportDashboardDrilldown()}
          />
        )}

        {page === "sales" && (
          <SalesHistoryPage companyId={companyId} />
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

        {page === "customers" && (
          <CustomersPage companyId={companyId} />
        )}

        {page === "credit-settlements" && (
          <CreditSettlementsPage companyId={companyId} />
        )}

        {page === "expenses" && (
          <ExpensesPage companyId={companyId} />
        )}

        {page === "shift-reports" && (
          <ShiftReportsPage companyId={companyId} />
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

export default App;
