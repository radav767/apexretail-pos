import { createRoot } from "react-dom/client";
import "../src/App.css";
import "../src/theme.css";
import "../src/ui-system.css";
import "../src/premium-theme.css";
import EmployeesPage from "../src/pages/EmployeesPage";
import { AppIcon } from "../src/components/AppIcon";
import { api } from "../src/api/client";

const groups = {
  sales: { sales_process: "Process sales", sales_discount: "Apply discounts", sales_price_override: "Override prices", sales_refund: "Refund transactions", sales_receipt_reprint: "Reprint receipts", sales_history_view: "View sales history" },
  products: { products_add: "Add products", products_edit: "Edit products", products_delete: "Delete products", categories_manage: "Manage categories", variants_manage: "Manage variants", composites_manage: "Manage composite products", product_costs_view: "View product costs" },
  inventory: { inventory_receive: "Receive stock", inventory_adjust: "Adjust stock", inventory_transfer: "Transfer stock", inventory_count: "Perform stock counts", inventory_valuation_view: "View inventory valuation" },
  financial: { revenue_view: "View revenue", profits_view: "View profits", expenses_manage: "Manage expenses", shifts_open: "Open shifts", shifts_close: "Close shifts", z_reports_view: "View Z Reports", cash_movements_manage: "Manage cash movements" },
  management: { employees_manage: "Manage employees", roles_manage: "Manage roles", branches_manage: "Manage branches", devices_manage: "Manage devices", printers_manage: "Manage printers", business_settings_manage: "Change business settings", audit_logs_view: "View activity logs", approve_restricted_actions: "Approve restricted actions" },
};
const all = Object.fromEntries(Object.values(groups).flatMap(Object.keys).map((key) => [key, true]));
const roles = [
  { id: null, name: "owner", system: true, active: true, description: "Business-wide administration", permissions: all },
  { id: null, name: "supervisor", system: true, active: true, description: "Operations and approvals", permissions: { sales_process: true, sales_discount: true, sales_refund: true, inventory_adjust: true, approve_restricted_actions: true, shifts_close: true, revenue_view: true } },
  { id: null, name: "cashier", system: true, active: true, description: "Sales and own cashier shifts", permissions: { sales_process: true, sales_receipt_reprint: true, sales_history_view: true, shifts_open: true, shifts_close: true } },
  { id: "role-receiving", name: "Receiving specialist", system: false, active: true, description: "Goods receiving and stock counts", permissions: { inventory_receive: true, inventory_count: true } },
];
const branches = [{ id: "branch-main", shop_id: "shop-central", shop_name: "Central Store", name: "Main Floor" }, { id: "branch-wholesale", shop_id: "shop-central", shop_name: "Central Store", name: "Wholesale" }];
let employees = [
  { id: "employee-a", name: "Alex Morgan", email: "alex@example.test", role: "owner", permissions: all, active: true, device_restricted: false, device_ids: [], ...branches[0], id_unused: undefined },
  { id: "employee-b", name: "Sarah Chen", email: "sarah@example.test", role: "supervisor", permissions: roles[1].permissions, active: true, device_restricted: false, device_ids: [], ...branches[0] },
  { id: "employee-c", name: "Jamie Patel", email: "jamie@example.test", role: "cashier", permissions: roles[2].permissions, active: true, device_restricted: true, device_ids: ["register-one"], ...branches[0] },
].map((item, index) => ({ ...item, id: `employee-${index}`, name: ["Alex Morgan", "Sarah Chen", "Jamie Patel"][index], shop_id: "shop-central", branch_id: "branch-main", shop_name: "Central Store", branch_name: "Main Floor" }));

api.defaults.adapter = async (config) => {
  const url = config.url || "";
  let data: unknown;
  if (url.includes("permissions/catalog")) data = groups;
  else if (url.includes("/employees/roles/")) data = roles;
  else if (url.includes("/employees/activity/")) data = [
    { id: "audit-a", actor_name: "Sarah Chen", action: "manager_authorization_used", reason: "Authorized customer return", created_at: "2026-10-19T10:24:00Z" },
    { id: "audit-b", actor_name: "Jamie Patel", action: "employee_login", reason: null, created_at: "2026-10-19T09:02:00Z" },
    { id: "audit-c", actor_name: "Alex Morgan", action: "role_updated", reason: "Receiving specialist access updated", created_at: "2026-10-19T08:45:00Z" },
  ];
  else if (url.includes("/inventory/branches/")) data = branches;
  else if (url.includes("/devices/")) data = [{ id: "register-one", friendly_name: "Checkout 01", pos_number: 1 }, { id: "register-two", friendly_name: "Checkout 02", pos_number: 2 }];
  else if (config.method === "patch" && url.includes("/employees/")) {
    const patch = JSON.parse(config.data);
    employees = employees.map((item) => url.endsWith(item.id) ? { ...item, ...patch } : item);
    data = employees;
  } else if (url.includes("/employees/")) data = employees;
  else throw new Error(`Unmocked preview request: ${url}`);
  return { data, status: 200, statusText: "OK", headers: {}, config };
};

createRoot(document.getElementById("root")!).render(
  <div className="backoffice-shell"><aside className="sidebar"><div className="sidebar-header"><div className="sidebar-brand"><div className="logo-mark small">A</div><div><strong>ApexRetail</strong><span>Backoffice · synthetic preview</span></div></div></div><nav><button><AppIcon name="dashboard"/>Dashboard</button><button><AppIcon name="products"/>Products</button><button><AppIcon name="inventory"/>Inventory</button><button className="active"><AppIcon name="employees"/>Employees</button><button><AppIcon name="reports"/>Reports</button></nav></aside><main className="content"><header className="topbar"><div><h1>Team management</h1><p>Central Store · Synthetic preview data</p></div><button className="refresh-button">Owner</button></header><EmployeesPage companyId="fixture-company"/></main></div>,
);
