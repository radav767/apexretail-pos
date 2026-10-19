import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { AppIcon, type AppIconName } from "../components/AppIcon";
import "./employees.css";

type View = "home" | "employees" | "roles" | "permissions" | "activity" | "assignments";
type Role = { id: string | null; name: string; description?: string | null; permissions: Record<string, boolean>; system: boolean; active: boolean };
type Employee = { id: string; shop_id: string; branch_id: string; shop_name: string; branch_name: string; name: string; email?: string | null; phone?: string | null; role: string; role_id?: string | null; role_name?: string | null; permissions: Record<string, boolean>; active: boolean; device_restricted?: boolean; device_ids?: string[] };
type Branch = { id: string; shop_id: string; shop_name: string; name: string };
type Device = { id: string; name?: string; friendly_name?: string | null; pos_number?: number | null };
type Activity = { id: string; actor_name?: string | null; action: string; reason?: string | null; created_at: string };
type Groups = Record<string, Record<string, string>>;

const FEATURES: Array<[View, string, string]> = [
  ["employees", "Employees", "Profiles, PINs and status"], ["roles", "Roles", "Built-in and custom roles"],
  ["permissions", "Permissions", "Granular access controls"], ["activity", "Activity Logs", "Protected accountability history"],
  ["assignments", "Branch Assignments", "Staff locations and devices"],
];
const emptyEmployee = { name: "", email: "", phone: "", pin: "", role: "cashier", role_id: "", branch_id: "", active: true, permissions: {} as Record<string, boolean>, device_restricted: false, device_ids: [] as string[] };
const emptyRole = { name: "", description: "", permissions: {} as Record<string, boolean> };
const title = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const featureIcons: Record<View, AppIconName> = { home: "dashboard", employees: "employees", roles: "settings", permissions: "devices", activity: "shifts", assignments: "inventory" };
function initialView(): View {
  const requested = new URLSearchParams(location.search).get("employees_view");
  return FEATURES.some(([key]) => key === requested) ? requested as View : "home";
}

export default function EmployeesPage({ companyId }: { companyId: string }) {
  const [view, setView] = useState<View>(initialView);
  const [employees, setEmployees] = useState<Employee[]>([]), [roles, setRoles] = useState<Role[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]), [devices, setDevices] = useState<Device[]>([]);
  const [groups, setGroups] = useState<Groups>({}), [activity, setActivity] = useState<Activity[]>([]);
  const [employee, setEmployee] = useState(emptyEmployee), [role, setRole] = useState(emptyRole);
  const [editingEmployee, setEditingEmployee] = useState(""), [editingRole, setEditingRole] = useState("");
  const [search, setSearch] = useState(""), [message, setMessage] = useState(""), [loading, setLoading] = useState(false);
  const [activityEmployee, setActivityEmployee] = useState("");

  const load = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    try {
      const [e, r, p, b, d] = await Promise.all([
        api.get(`/employees/${companyId}`), api.get(`/employees/roles/${companyId}`),
        api.get("/employees/permissions/catalog"), api.get(`/inventory/branches/${companyId}`), api.get(`/employees/devices/${companyId}`),
      ]);
      setEmployees(e.data); setRoles(r.data); setGroups(p.data); setBranches(b.data);
      setDevices(Array.isArray(d.data) ? d.data : d.data?.items || []);
      setEmployee((current) => ({ ...current, branch_id: current.branch_id || b.data[0]?.id || "" }));
    } catch (error: any) { setMessage(error.response?.data?.detail || "Employee administration could not be loaded."); }
    finally { setLoading(false); }
  }, [companyId]);
  const loadActivity = useCallback(async () => { try { setActivity((await api.get(`/employees/activity/${companyId}`, { params: { limit: 200, employee_id: activityEmployee || undefined } })).data); } catch (error: any) { setMessage(error.response?.data?.detail || "Activity could not be loaded."); } }, [companyId, activityEmployee]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (view === "activity") void loadActivity(); }, [view, loadActivity]);
  useEffect(() => {
    const restore = () => setView(initialView());
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  const filtered = useMemo(() => employees.filter((item) => `${item.name} ${item.email || ""} ${item.role_name || item.role} ${item.branch_name}`.toLowerCase().includes(search.toLowerCase())), [employees, search]);
  const permissionKeys = Object.values(groups).flatMap(Object.keys);
  function selectView(next: View) { const url = new URL(location.href); if (next === "home") url.searchParams.delete("employees_view"); else url.searchParams.set("employees_view", next); history.pushState({ employeeView: next }, "", url); setView(next); setMessage(""); }
  function resetEmployee() { setEditingEmployee(""); setEmployee({ ...emptyEmployee, branch_id: branches[0]?.id || "" }); }
  function edit(item: Employee) { setEditingEmployee(item.id); setEmployee({ name: item.name, email: item.email || "", phone: item.phone || "", pin: "", role: item.role, role_id: item.role_id || "", branch_id: item.branch_id, active: item.active, permissions: { ...item.permissions }, device_restricted: Boolean(item.device_restricted), device_ids: item.device_ids || [] }); setView("employees"); }
  function chooseRole(value: string) { const selected = roles.find((item) => (item.id || `system:${item.name}`) === value); if (selected) setEmployee((current) => ({ ...current, role: selected.name, role_id: selected.id || "", permissions: { ...selected.permissions } })); }

  async function saveEmployee() {
    const branch = branches.find((item) => item.id === employee.branch_id);
    if (!branch || !employee.name.trim()) return setMessage("Employee name and branch are required.");
    if ((!editingEmployee || employee.pin) && !/^\d{4}$/.test(employee.pin)) return setMessage("Enter a unique four-digit PIN.");
    const payload: Record<string, unknown> = { shop_id: branch.shop_id, branch_id: branch.id, name: employee.name.trim(), email: employee.email.trim() || null, phone: employee.phone.trim() || null, role: employee.role, role_id: employee.role_id || null, active: employee.active, permissions: employee.permissions, device_restricted: employee.device_restricted, device_ids: employee.device_ids };
    if (!editingEmployee) { payload.company_id = companyId; payload.pin = employee.pin; } else if (employee.pin) payload.pin = employee.pin;
    try { if (editingEmployee) await api.patch(`/employees/${companyId}/${editingEmployee}`, payload); else await api.post("/employees", payload); setMessage(editingEmployee ? "Employee updated." : "Employee added."); resetEmployee(); await load(); }
    catch (error: any) { setMessage(error.response?.data?.detail || "Employee could not be saved."); }
  }
  async function toggle(item: Employee) { try { await api.patch(`/employees/${companyId}/${item.id}`, { active: !item.active }); setMessage(item.active ? "Employee deactivated and sessions revoked." : "Employee activated."); await load(); } catch (error: any) { setMessage(error.response?.data?.detail || "Status could not be changed."); } }
  async function saveRole() { if (!role.name.trim()) return setMessage("Role name is required."); const payload = { company_id: companyId, name: role.name.trim(), description: role.description.trim() || null, permissions: role.permissions }; try { if (editingRole) await api.patch(`/employees/roles/${companyId}/${editingRole}`, payload); else await api.post("/employees/roles", payload); setMessage(editingRole ? "Role updated." : "Custom role created."); setEditingRole(""); setRole(emptyRole); await load(); } catch (error: any) { setMessage(error.response?.data?.detail || "Role could not be saved."); } }

  const permissionEditor = (values: Record<string, boolean>, update: (value: Record<string, boolean>) => void) => <div className="phase7b-permission-groups">{Object.entries(groups).map(([group, entries]) => <section key={group}><h4>{title(group)}</h4><div>{Object.entries(entries).map(([key, label]) => <label key={key}><input type="checkbox" checked={Boolean(values[key])} onChange={() => update({ ...values, [key]: !values[key], ...(key === "expenses_manage" ? { expenses_create: !values[key] } : {}) })}/><span>{label}</span></label>)}</div></section>)}</div>;

  return <div className="employees-page phase7b-employees">
    <header className="phase7b-header"><div>{view !== "home" && <button onClick={() => selectView("home")}>← Back</button>}<span>People & access</span><h2>{view === "home" ? "Employees & Permissions" : FEATURES.find(([key]) => key === view)?.[1]}</h2></div><div><b>{employees.filter((item) => item.active).length}</b> active · <b>{roles.length}</b> roles</div></header>
    {message && <p className="employee-message">{message}</p>}
    {view === "home" && <><section className="employee-summary-grid"><article><span>Total employees</span><strong>{employees.length}</strong></article><article><span>Active</span><strong>{employees.filter((item) => item.active).length}</strong></article><article><span>Custom roles</span><strong>{roles.filter((item) => !item.system).length}</strong></article><article><span>Device restricted</span><strong>{employees.filter((item) => item.device_restricted).length}</strong></article></section><section className="phase7b-feature-grid">{FEATURES.map(([key, label, detail]) => <button key={key} onClick={() => selectView(key)}><i aria-hidden="true"><AppIcon name={featureIcons[key]} /></i><strong>{label}</strong><small>{detail}</small><b>→</b></button>)}</section></>}

    {view === "employees" && <div className="phase7b-workspace"><section className="employee-editor"><div className="employee-section-header"><h3>{editingEmployee ? "Edit employee" : "Add employee"}</h3>{editingEmployee && <button onClick={resetEmployee}>Cancel</button>}</div><div className="employee-form-grid"><label>Name<input value={employee.name} onChange={(e) => setEmployee({ ...employee, name: e.target.value })}/></label><label>Email<input type="email" value={employee.email} onChange={(e) => setEmployee({ ...employee, email: e.target.value })}/></label><label>Phone<input value={employee.phone} onChange={(e) => setEmployee({ ...employee, phone: e.target.value })}/></label><label>PIN<input type="password" inputMode="numeric" maxLength={4} placeholder={editingEmployee ? "Keep current PIN" : "4 digits"} value={employee.pin} onChange={(e) => setEmployee({ ...employee, pin: e.target.value.replace(/\D/g, "").slice(0, 4) })}/></label><label>Role<select value={employee.role_id || `system:${employee.role}`} onChange={(e) => chooseRole(e.target.value)}>{roles.map((item) => <option key={item.id || item.name} value={item.id || `system:${item.name}`}>{title(item.name)}</option>)}</select></label><label>Branch<select value={employee.branch_id} onChange={(e) => setEmployee({ ...employee, branch_id: e.target.value })}>{branches.map((item) => <option key={item.id} value={item.id}>{item.shop_name} — {item.name}</option>)}</select></label></div><label className="phase7b-switch"><input type="checkbox" checked={employee.device_restricted} onChange={(e) => setEmployee({ ...employee, device_restricted: e.target.checked })}/>Restrict to selected devices</label>{employee.device_restricted && <div className="phase7b-devices">{devices.map((item) => <label key={item.id}><input type="checkbox" checked={employee.device_ids.includes(item.id)} onChange={() => setEmployee({ ...employee, device_ids: employee.device_ids.includes(item.id) ? employee.device_ids.filter((id) => id !== item.id) : [...employee.device_ids, item.id] })}/>{item.friendly_name || item.name || `POS ${item.pos_number || ""}`}</label>)}</div>}<details><summary>Permission overrides</summary>{permissionEditor(employee.permissions, (permissions) => setEmployee({ ...employee, permissions }))}</details><button className="employee-primary-button" onClick={() => void saveEmployee()}>{editingEmployee ? "Save changes" : "Add employee"}</button></section><section className="employee-list-panel"><div className="phase7b-tools"><input type="search" placeholder="Search employees" value={search} onChange={(e) => setSearch(e.target.value)}/><button onClick={() => void load()}>{loading ? "Loading…" : "Refresh"}</button></div><div className="employee-table-wrapper"><table><thead><tr><th>Employee</th><th>Role</th><th>Branch</th><th>Status</th><th>Actions</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.email || item.phone || "No contact details"}</small></td><td>{title(item.role_name || item.role)}</td><td>{item.shop_name} · {item.branch_name}</td><td><span className={item.active ? "employee-active" : "employee-inactive"}>{item.active ? "Active" : "Inactive"}</span></td><td><div className="employee-actions"><button onClick={() => edit(item)}>Edit</button>{item.role !== "owner" && <button onClick={() => void toggle(item)}>{item.active ? "Deactivate" : "Activate"}</button>}</div></td></tr>)}</tbody></table></div></section></div>}

    {view === "roles" && <div className="phase7b-workspace"><section className="employee-editor"><h3>{editingRole ? "Edit custom role" : "Create custom role"}</h3><div className="employee-form-grid"><label>Role name<input value={role.name} onChange={(e) => setRole({ ...role, name: e.target.value })}/></label><label>Description<input value={role.description} onChange={(e) => setRole({ ...role, description: e.target.value })}/></label></div>{permissionEditor(role.permissions, (permissions) => setRole({ ...role, permissions }))}<button className="employee-primary-button" onClick={() => void saveRole()}>{editingRole ? "Save role" : "Create role"}</button></section><section className="phase7b-role-grid">{roles.map((item) => <article key={item.id || item.name}><span>{item.system ? "Built-in" : "Custom"}</span><h3>{title(item.name)}</h3><p>{item.description || "Business-defined access"}</p><strong>{permissionKeys.filter((key) => item.permissions[key]).length} permissions</strong>{!item.system && <button onClick={() => { setEditingRole(item.id || ""); setRole({ name: item.name, description: item.description || "", permissions: { ...item.permissions } }); }}>Edit role</button>}</article>)}</section></div>}

    {view === "permissions" && <section className="employee-list-panel phase7b-matrix"><table><thead><tr><th>Permission</th>{roles.map((item) => <th key={item.id || item.name}>{title(item.name)}</th>)}</tr></thead><tbody>{Object.entries(groups).flatMap(([group, entries]) => [<tr className="phase7b-group" key={group}><td colSpan={roles.length + 1}>{title(group)}</td></tr>, ...Object.entries(entries).map(([key, label]) => <tr key={key}><td>{label}</td>{roles.map((item) => <td key={item.id || item.name}>{item.permissions[key] ? "✓" : "—"}</td>)}</tr>)])}</tbody></table></section>}
    {view === "activity" && <section className="employee-list-panel"><div className="phase7b-tools"><select aria-label="Employee activity filter" value={activityEmployee} onChange={(event) => setActivityEmployee(event.target.value)}><option value="">All employee activity</option>{employees.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button onClick={() => void loadActivity()}>Refresh</button></div><div className="employee-table-wrapper"><table><thead><tr><th>Date & time</th><th>Employee / user</th><th>Action</th><th>Reason</th></tr></thead><tbody>{activity.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.actor_name || "System"}</td><td>{title(item.action)}</td><td>{item.reason || "—"}</td></tr>)}</tbody></table></div></section>}
    {view === "assignments" && <section className="phase7b-branch-grid">{branches.map((branch) => <article key={branch.id}><span>{branch.shop_name}</span><h3>{branch.name}</h3><strong>{employees.filter((item) => item.branch_id === branch.id).length} employees</strong>{employees.filter((item) => item.branch_id === branch.id).map((item) => <button key={item.id} onClick={() => edit(item)}>{item.name}<small>{title(item.role_name || item.role)}</small></button>)}</article>)}</section>}
  </div>;
}
