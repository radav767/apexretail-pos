import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import "./employees.css";

type PermissionKey =
  | "sales"
  | "discounts"
  | "refunds"
  | "manage_inventory"
  | "manage_products"
  | "reports"
  | "employees"
  | "settings"
  | "manage_devices";

type Employee = {
  id: string;
  company_id: string;
  shop_id: string;
  branch_id: string;
  shop_name: string;
  branch_name: string;
  name: string;
  email: string | null;
  phone: string | null;
  role: "owner" | "manager" | "cashier";
  permissions: Record<PermissionKey, boolean>;
  active: boolean;
};

type Branch = {
  id: string;
  shop_id: string;
  shop_name: string;
  name: string;
};

const permissionLabels: Record<PermissionKey, string> = {
  sales: "Make sales",
  discounts: "Apply discounts",
  refunds: "Process refunds",
  manage_inventory: "Manage inventory",
  manage_products: "Manage products",
  reports: "View reports",
  employees: "Manage employees",
  settings: "Change settings",
  manage_devices: "Manage POS devices",
};

const rolePermissions: Record<
  Employee["role"],
  Record<PermissionKey, boolean>
> = {
  cashier: {
    sales: true,
    discounts: false,
    refunds: false,
    manage_inventory: false,
    manage_products: false,
    reports: false,
    employees: false,
    settings: false,
    manage_devices: false,
  },
  manager: {
    sales: true,
    discounts: true,
    refunds: true,
    manage_inventory: true,
    manage_products: true,
    reports: true,
    employees: true,
    settings: false,
    manage_devices: false,
  },
  owner: {
    sales: true,
    discounts: true,
    refunds: true,
    manage_inventory: true,
    manage_products: true,
    reports: true,
    employees: true,
    settings: true,
    manage_devices: true,
  },
};

const emptyForm = {
  name: "",
  email: "",
  phone: "",
  pin: "",
  role: "cashier" as Employee["role"],
  branch_id: "",
  active: true,
  permissions: { ...rolePermissions.cashier },
};

export default function EmployeesPage({
  companyId,
}: {
  companyId: string;
}) {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const activeEmployees = useMemo(
    () => employees.filter((employee) => employee.active),
    [employees],
  );

  async function loadData() {
    if (!companyId) return;

    try {
      setLoading(true);
      setMessage("");

      const [employeeResponse, branchResponse] =
        await Promise.all([
          api.get(`/employees/${companyId}`),
          api.get(`/inventory/branches/${companyId}`),
        ]);

      const loadedEmployees: Employee[] =
        employeeResponse.data;

      const loadedBranches: Branch[] =
        branchResponse.data;

      setEmployees(loadedEmployees);
      setBranches(loadedBranches);

      setForm((current) => ({
        ...current,
        branch_id:
          current.branch_id ||
          loadedBranches[0]?.id ||
          "",
      }));
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to load employees",
      );
    } finally {
      setLoading(false);
    }
  }

  function resetForm() {
    setEditingId("");

    setForm({
      ...emptyForm,
      permissions: {
        ...rolePermissions.cashier,
      },
      branch_id: branches[0]?.id || "",
    });
  }

  function changeRole(role: Employee["role"]) {
    setForm((current) => ({
      ...current,
      role,
      permissions: {
        ...rolePermissions[role],
      },
    }));
  }

  function togglePermission(key: PermissionKey) {
    setForm((current) => ({
      ...current,
      permissions: {
        ...current.permissions,
        [key]: !current.permissions[key],
      },
    }));
  }

  function editEmployee(employee: Employee) {
    setEditingId(employee.id);

    setForm({
      name: employee.name,
      email: employee.email || "",
      phone: employee.phone || "",
      pin: "",
      role: employee.role,
      branch_id: employee.branch_id,
      active: employee.active,
      permissions: {
        ...rolePermissions[employee.role],
        ...employee.permissions,
      },
    });

    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  }

  async function saveEmployee() {
    const branch = branches.find(
      (item) => item.id === form.branch_id,
    );

    if (!form.name.trim()) {
      setMessage("Employee name is required");
      return;
    }

    if (!branch) {
      setMessage("Select a valid branch");
      return;
    }

    if (!editingId && !/^\d{4}$/.test(form.pin)) {
      setMessage(
        "Enter a unique four-digit employee PIN",
      );
      return;
    }

    if (
      editingId &&
      form.pin &&
      !/^\d{4}$/.test(form.pin)
    ) {
      setMessage("The PIN must contain four digits");
      return;
    }

    const payload: Record<string, unknown> = {
      shop_id: branch.shop_id,
      branch_id: branch.id,
      name: form.name.trim(),
      email: form.email.trim() || null,
      phone: form.phone.trim() || null,
      role: form.role,
      permissions: form.permissions,
      active: form.active,
    };

    if (!editingId) {
      payload.company_id = companyId;
      payload.pin = form.pin;
    } else if (form.pin) {
      payload.pin = form.pin;
    }

    try {
      setSaving(true);
      setMessage("");

      if (editingId) {
        await api.patch(
          `/employees/${companyId}/${editingId}`,
          payload,
        );

        setMessage("Employee updated successfully");
      } else {
        await api.post("/employees", payload);
        setMessage("Employee created successfully");
      }

      resetForm();
      await loadData();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to save employee",
      );
    } finally {
      setSaving(false);
    }
  }

  async function changeEmployeeStatus(
    employee: Employee,
  ) {
    try {
      setMessage("");

      await api.patch(
        `/employees/${companyId}/${employee.id}`,
        {
          active: !employee.active,
        },
      );

      setMessage(
        employee.active
          ? `${employee.name} deactivated`
          : `${employee.name} activated`,
      );

      await loadData();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to change employee status",
      );
    }
  }

  async function deleteEmployee(employee: Employee) {
    const confirmed = window.confirm(
      `Delete ${employee.name}?`,
    );

    if (!confirmed) return;

    try {
      setMessage("");

      await api.delete(
        `/employees/${companyId}/${employee.id}`,
      );

      setMessage("Employee deleted successfully");

      if (editingId === employee.id) {
        resetForm();
      }

      await loadData();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to delete employee",
      );
    }
  }

  useEffect(() => {
    void loadData();
  }, [companyId]);

  return (
    <div className="employees-page">
      <section className="employee-summary-grid">
        <article>
          <span>Total employees</span>
          <strong>{employees.length}</strong>
          <small>Registered staff members</small>
        </article>

        <article>
          <span>Active employees</span>
          <strong>{activeEmployees.length}</strong>
          <small>Allowed to access the POS</small>
        </article>

        <article>
          <span>Cashiers</span>
          <strong>
            {
              employees.filter(
                (employee) =>
                  employee.role === "cashier",
              ).length
            }
          </strong>
          <small>Sales-only employees</small>
        </article>

        <article>
          <span>Managers</span>
          <strong>
            {
              employees.filter(
                (employee) =>
                  employee.role === "manager",
              ).length
            }
          </strong>
          <small>Management access</small>
        </article>
      </section>

      <section className="employee-editor">
        <div className="employee-section-header">
          <div>
            <h2>
              {editingId
                ? "Edit Employee"
                : "Add Employee"}
            </h2>
            <p>
              Employees use their four-digit PIN to enter the
              POS.
            </p>
          </div>

          {editingId && (
            <button
              type="button"
              className="employee-secondary-button"
              onClick={resetForm}
            >
              Cancel Editing
            </button>
          )}
        </div>

        <div className="employee-form-grid">
          <label>
            Employee name
            <input
              value={form.name}
              placeholder="Example: John Cashier"
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  name: event.target.value,
                }))
              }
            />
          </label>

          <label>
            Email
            <input
              type="email"
              value={form.email}
              placeholder="Optional"
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  email: event.target.value,
                }))
              }
            />
          </label>

          <label>
            Phone
            <input
              value={form.phone}
              placeholder="Optional"
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  phone: event.target.value,
                }))
              }
            />
          </label>

          <label>
            Four-digit PIN
            <input
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={form.pin}
              placeholder={
                editingId
                  ? "Leave blank to keep current PIN"
                  : "Enter 4 digits"
              }
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  pin: event.target.value
                    .replace(/\D/g, "")
                    .slice(0, 4),
                }))
              }
            />
          </label>

          <label>
            Role
            <select
              value={form.role}
              onChange={(event) =>
                changeRole(
                  event.target.value as Employee["role"],
                )
              }
            >
              <option value="cashier">Cashier</option>
              <option value="manager">Manager</option>
              <option value="owner">Owner</option>
            </select>
          </label>

          <label>
            Shop and branch
            <select
              value={form.branch_id}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  branch_id: event.target.value,
                }))
              }
            >
              <option value="">Select branch</option>

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
        </div>

        <div className="employee-permissions">
          <h3>Permissions</h3>

          <div className="permission-grid">
            {(
              Object.keys(
                permissionLabels,
              ) as PermissionKey[]
            ).map((key) => (
              <label key={key}>
                <input
                  type="checkbox"
                  checked={form.permissions[key]}
                  onChange={() =>
                    togglePermission(key)
                  }
                />

                <span>{permissionLabels[key]}</span>
              </label>
            ))}
          </div>
        </div>

        <button
          type="button"
          className="employee-primary-button"
          onClick={saveEmployee}
          disabled={saving}
        >
          {saving
            ? "Saving..."
            : editingId
              ? "Save Changes"
              : "Add Employee"}
        </button>
      </section>

      <section className="employee-list-panel">
        <div className="employee-section-header">
          <div>
            <h2>Employee List</h2>
            <p>
              Manage POS access, roles, branches and employee
              status.
            </p>
          </div>

          <button
            type="button"
            className="employee-secondary-button"
            onClick={loadData}
            disabled={loading}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        <div className="employee-table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Employee</th>
                <th>Role</th>
                <th>Location</th>
                <th>Permissions</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {employees.map((employee) => {
                const permissionCount =
                  Object.values(
                    employee.permissions || {},
                  ).filter(Boolean).length;

                return (
                  <tr key={employee.id}>
                    <td>
                      <strong>{employee.name}</strong>
                      <small>
                        {employee.email ||
                          employee.phone ||
                          "No contact details"}
                      </small>
                    </td>

                    <td>
                      <span className="employee-role">
                        {employee.role}
                      </span>
                    </td>

                    <td>
                      <strong>
                        {employee.branch_name}
                      </strong>
                      <small>{employee.shop_name}</small>
                    </td>

                    <td>
                      {permissionCount} permission(s)
                    </td>

                    <td>
                      <span
                        className={
                          employee.active
                            ? "employee-active"
                            : "employee-inactive"
                        }
                      >
                        {employee.active
                          ? "Active"
                          : "Inactive"}
                      </span>
                    </td>

                    <td>
                      <div className="employee-actions">
                        <button
                          type="button"
                          onClick={() =>
                            editEmployee(employee)
                          }
                        >
                          Edit
                        </button>

                        <button
                          type="button"
                          onClick={() =>
                            changeEmployeeStatus(employee)
                          }
                          disabled={
                            employee.role === "owner"
                          }
                        >
                          {employee.active
                            ? "Deactivate"
                            : "Activate"}
                        </button>

                        <button
                          type="button"
                          className="employee-delete-button"
                          onClick={() =>
                            deleteEmployee(employee)
                          }
                          disabled={
                            employee.role === "owner"
                          }
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {!employees.length && !loading && (
                <tr>
                  <td
                    colSpan={6}
                    className="employee-empty"
                  >
                    No employees found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <p className="employee-message">{message}</p>
    </div>
  );
}
