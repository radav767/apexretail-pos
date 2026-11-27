import TipsSettingsPanel from './pages/TipsSettingsPanel';
import SalesReportsHub from "../../pos-web/src/navigation/SalesReportsHub";
import { readAuthEntry } from './api/authEntry';
import { clearBusinessContext, installBusinessContext, contextGeneration } from './api/businessSession';
import { refreshBusinessSession, beginBusinessLogin } from './api/client';
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import "./App.css";
import {
  type DashboardDrilldown,
  type DashboardDrilldownRequest,
  type DashboardPhase3Summary,
  type DashboardRangeKey,
} from "./dashboard";
import { DashboardPanel, type DashboardFeature, type ExportSection } from "./DashboardPanel";
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
import BusinessOperations from "../../pos-web/src/business/BusinessOperations";

type BackofficePage =
  | "tip-operations"
  | "sales-reports-hub"
  | "business-operations"
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
  return (["tip-operations","sales-reports-hub","dashboard", "sales", "products", "inventory", "devices", "employees", "reports", "customers", "credit-settlements", "expenses", "shift-reports", "settings", "business-operations"] as BackofficePage[])
    .includes(requested as BackofficePage) ? requested as BackofficePage : "dashboard";
}

function initialDashboardFeature(): DashboardFeature {
  const requested = new URLSearchParams(window.location.search).get("feature");
  return (["sales-analytics", "payment-methods", "top-products"] as DashboardFeature[])
    .includes(requested as DashboardFeature) ? requested as DashboardFeature : "home";
}

function localDateValue(date: Date): string {
  const adjusted = new Date(
    date.getTime() - date.getTimezoneOffset() * 60_000,
  );

  return adjusted.toISOString().slice(0, 10);
}

const initialAuthEntry = readAuthEntry(window.location, window.history);

function App() {
  const [authEntry, setAuthEntry] = useState(initialAuthEntry);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [authMode, setAuthMode] = useState<'login' | 'forgot' | 'reset' | 'handoff'>(authEntry.handoff !== null ? 'handoff' : authEntry.reset !== null ? 'reset' : 'login');
  const [recoveryAvailable, setRecoveryAvailable] = useState(false);
  useEffect(() => {
    let active = true;
    api.get('/auth/capabilities').then(({ data }) => {
      if (active) setRecoveryAvailable(data.password_recovery === 'test_sink');
    }).catch(() => { if (active) setRecoveryAvailable(false); });
    return () => { active = false; };
  }, []);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const handoffReceiver = useRef(crypto.randomUUID());
  const [handoffIdentity, setHandoffIdentity] = useState<{ email: string; company_id: string; branch_id: string; role: string; company_name: string; branch_name: string } | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [loggedIn, setLoggedIn] = useState(
    false,
  );
  const [companyId, setCompanyId] = useState(
    "",
  );
  const [dashboardSummary, setDashboardSummary] =
    useState<DashboardPhase3Summary | null>(null);
  const [dashboardShops, setDashboardShops] = useState<DashboardPhase3Summary["shops"]>([]);
  const [granularity, setGranularity] = useState<"day" | "week" | "month">("day");
  const [page, setPage] = useState<BackofficePage>(initialBackofficePage);
  const [dashboardFeature, setDashboardFeature] = useState<DashboardFeature>(initialDashboardFeature);
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

  useEffect(() => {
    const update = () => {
      dashboardRequest.current += 1;
      setCompanyId(sessionStorage.getItem('backoffice_company_id') || '');
      setLoggedIn(Boolean(sessionStorage.getItem('backoffice_token')));
      setDashboardSummary(null); setDashboardShops([]); setDrilldownData(null);
    };
    window.addEventListener('business-context-changed', update);
    const receiveEntry = () => {
      const entry = readAuthEntry(window.location, window.history);
      if (entry.reset === null && entry.handoff === null) return;
      clearBusinessContext(); setHandoffIdentity(null); setMessage('');
      setAuthMode(entry.handoff !== null ? 'handoff' : 'reset'); setAuthEntry(entry);
    };
    window.addEventListener('hashchange', receiveEntry);
    return () => { window.removeEventListener('business-context-changed', update); window.removeEventListener('hashchange', receiveEntry); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (authEntry.reset !== null || authEntry.handoff !== null) {
      void beginBusinessLogin().then(async epoch => {
        if (cancelled || epoch !== contextGeneration()) return;
        if (authEntry.handoff !== null) {
          const { data } = await api.post('/auth/handoff/inspect', { code: authEntry.handoff, receiver: handoffReceiver.current });
          if (!cancelled && epoch === contextGeneration()) setHandoffIdentity(data);
        }
      }).catch(() => { if (!cancelled) setMessage('This entry link is invalid or expired, or the server is unavailable. Return to POS or request a new recovery link.'); });
    } else void refreshBusinessSession();
    return () => { cancelled = true; };
  }, [authEntry]);

  async function acceptHandoff() {
    if (!handoffIdentity) return;
    setLoading(true); setMessage('');
    const epoch = contextGeneration();
    try {
      const { data } = await api.post('/auth/handoff/consume', { code: authEntry.handoff, receiver: handoffReceiver.current,
        company_id: handoffIdentity.company_id, branch_id: handoffIdentity.branch_id, role: handoffIdentity.role });
      if (!installBusinessContext(data, epoch)) return;
      setHandoffIdentity(null); setPassword('');
    } catch { clearBusinessContext(); setHandoffIdentity(null); setMessage('Handoff expired or was already used. Return to POS and open Backoffice again.'); }
    finally { setLoading(false); }
  }

  async function recoverPassword() {
    setLoading(true); setMessage('');
    try {
      if (authMode === 'forgot') {
        if (!recoveryAvailable) { setMessage('Email recovery is unavailable on this release. Contact your business administrator.'); return; }
        const { data } = await api.post('/auth/forgot-password', { email });
        setMessage(data.message);
      } else {
        const { data } = await api.post('/auth/reset-password', { token: authEntry.reset, password: newPassword, confirm_password: confirmPassword });
        clearBusinessContext(); setPassword(''); setNewPassword(''); setConfirmPassword(''); setRememberMe(false);
        setAuthMode('login'); setMessage(data.message);
      }
    } catch { setMessage(authMode === 'forgot' ? 'Recovery request failed. Try again when connected.' : 'Recovery link is invalid or expired, or passwords do not meet the requirements.'); }
    finally { setLoading(false); }
  }

  async function login() {
    try {
      setLoading(true);
      setMessage("");

      const epoch = await beginBusinessLogin();
      const response = await api.post("/auth/login", { email, password, client: 'backoffice', remember_me: rememberMe });
      if (!installBusinessContext(response.data, epoch)) return;
      setPassword('');

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

  async function logout() {
    try {
      await api.post('/auth/logout', {}, { headers: { Authorization: `Bearer ${sessionStorage.getItem('backoffice_token') || ''}` } });
    } catch {
      try { await api.post('/auth/logout-browser'); }
      catch { setMessage('Server logout failed. Reconnect and retry to revoke this session.'); return; }
    }
    clearBusinessContext();

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
    setDashboardFeature("home");
    const url = new URL(window.location.href);
    url.searchParams.set("page", nextPage);
    url.searchParams.delete("feature");
    window.history.pushState(null, "", url);
    setMobileMenuOpen(false);
    closeDashboardDrilldown();
  }

  function navigateDashboardFeature(nextFeature: DashboardFeature) {
    setPage("dashboard");
    setDashboardFeature(nextFeature);
    const url = new URL(window.location.href);
    url.searchParams.set("page", "dashboard");
    if (nextFeature === "home") url.searchParams.delete("feature");
    else url.searchParams.set("feature", nextFeature);
    window.history.pushState(null, "", url);
    closeDashboardDrilldown();
  }

  useEffect(() => {
    const syncLocation = () => {
      setPage(initialBackofficePage());
      setDashboardFeature(initialDashboardFeature());
      setMobileMenuOpen(false);
      closeDashboardDrilldown();
    };
    window.addEventListener("popstate", syncLocation);
    return () => window.removeEventListener("popstate", syncLocation);
  }, []);

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

          {authMode === 'login' ? <>
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

          <label><input type="checkbox" checked={rememberMe} onChange={event => setRememberMe(event.target.checked)} /> Remember Me (30 days)</label>
          <button
            className="primary-button"
            onClick={login}
            disabled={loading}
          >
            {loading ? "Signing in..." : "Login"}
          </button>

          {recoveryAvailable
            ? <button onClick={() => { setAuthMode('forgot'); setMessage(''); }}>Forgot password? (test email sink)</button>
            : <p>Email password recovery is unavailable. Contact your business administrator.</p>}
          </> : authMode === 'handoff' ? <>
            <h2>Confirm your Backoffice account</h2>
            {handoffIdentity ? <>
              <p>Continue as {handoffIdentity.email} ({handoffIdentity.role}) for {handoffIdentity.company_name}, {handoffIdentity.branch_name}.</p>
              <button className="primary-button" disabled={loading} onClick={acceptHandoff}>{loading ? 'Opening...' : 'Continue with this account'}</button>
            </> : <p>Return to POS if this link has expired.</p>}
            <button onClick={() => { clearBusinessContext(); setHandoffIdentity(null); setAuthMode('login'); }}>Use password login instead</button>
          </> : <>
            <h2>{authMode === 'forgot' ? 'Recover your account' : 'Choose a new password'}</h2>
            {authMode === 'forgot' ? <label>Email<input type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} /></label> : <>
              <label>New password (12 characters minimum)<input type="password" autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} /></label>
              <label>Confirm password<input type="password" autoComplete="new-password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} /></label>
            </>}
            <button className="primary-button" disabled={loading} onClick={recoverPassword}>{loading ? 'Please wait...' : authMode === 'forgot' ? 'Request recovery' : 'Reset password'}</button>
            <button onClick={() => { setAuthMode('login'); setMessage(''); }}>Back to login</button>
          </>}
          <p className="error-message">{message}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`backoffice-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
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
            className="sidebar-collapse-toggle"
            type="button"
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!sidebarCollapsed}
            aria-controls="backoffice-navigation"
            onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
          >
            <AppIcon name="menu" />
          </button>

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

          <span className="nav-section-label">Sales &amp; Reports</span>
          <button className={page==="sales-reports-hub"?"active":""} onClick={()=>navigateTo("sales-reports-hub")}><AppIcon name="reports"/><span>Sales &amp; Reports</span></button>

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

          <button
            className={page === "reports" ? "active" : ""}
            onClick={() => navigateTo("reports")}
          >
            <AppIcon name="reports" /> <span>Reports</span>
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
          <button className={page === "business-operations" ? "active" : ""} onClick={() => navigateTo("business-operations")}><AppIcon name="dashboard"/><span>Business Operations</span></button>
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
              {page === "sales-reports-hub" ? "Sales & Reports" : page === "dashboard"
                ? dashboardFeature === "sales-analytics"
                  ? "Sales Analytics"
                  : dashboardFeature === "payment-methods"
                    ? "Payment Methods"
                    : dashboardFeature === "top-products"
                      ? "Top Products"
                      : "Business Dashboard"
                : page === "sales"
                  ? "Sales History"
                  : page === "products"
                    ? "Products & Categories"
                    : page === "inventory"
                      ? "Inventory Management"
                      : page === "employees"
                        ? "Employees & Permissions"
                        : page === "tip-operations"
                          ? "Tip operations & recovery"
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
            feature={dashboardFeature}
            onFeatureChange={navigateDashboardFeature}
            onNavigatePage={navigateTo}
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

        {page === "tip-operations" && <TipsSettingsPanel key={companyId} companyId={companyId} mode="operations"/>}
        {page === "sales-reports-hub" && <SalesReportsHub backoffice companyId={companyId} client={api} onSelect={item=>navigateTo(item.page as BackofficePage)}/>}

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
            onOpenWorkspace={target=>{navigateTo(target.page);const url=new URL(location.href);if(target.feature)url.searchParams.set('feature',target.feature);if(target.businessView)url.searchParams.set('business_view',target.businessView);if(target.inventoryTab)url.searchParams.set('inventory_tab',target.inventoryTab);if(target.workflowTab)url.searchParams.set('workflow_tab',target.workflowTab);history.replaceState(null,'',url);window.dispatchEvent(new PopStateEvent('popstate'))}}
          />
        )}

        {page === "business-operations" && <BusinessOperations companyId={companyId} api={api} />}

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
