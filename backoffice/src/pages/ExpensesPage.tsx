import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import { categoryBreakdown, expenseAmountError, expenseSummary } from "./expenseLogic";
import type { ExpenseLogicRow } from "./expenseLogic";
import "./expenses.css";

type Expense = ExpenseLogicRow & {
  id: string;
  shop_id: string;
  currency_code: string;
  idempotency_key: string;
  created_at: string;
};
type ExpenseCategory = { id: string; company_id: string; name: string; description: string | null; active: boolean };
type Branch = { id: string; shop_id: string; shop_name: string; name: string };

const now = new Date();
const today = now.toISOString().slice(0, 10);
const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString().slice(0, 10);

function localDateTimeValue(value = new Date()) {
  return new Date(value.getTime() - value.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function nextDay(date: string) {
  const value = new Date(`${date}T00:00:00`);
  value.setDate(value.getDate() + 1);
  return value.toISOString();
}

function money(value: string | number, currency = "USD") {
  const amount = Number(value || 0);
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount); }
  catch { return `${currency} ${amount.toFixed(2)}`; }
}

function shortId(value: string | null) { return value ? value.slice(0, 8).toUpperCase() : "Unknown"; }
function requestKey() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `expense-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function ExpensesPage({ companyId }: { companyId: string }) {
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [categories, setCategories] = useState<ExpenseCategory[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [dateFrom, setDateFrom] = useState(monthStart);
  const [dateTo, setDateTo] = useState(today);
  const [branchId, setBranchId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [expenseOpen, setExpenseOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [amountValue, setAmountValue] = useState("");
  const [expenseCategoryId, setExpenseCategoryId] = useState("");
  const [expenseBranchId, setExpenseBranchId] = useState("");
  const [occurredAt, setOccurredAt] = useState(localDateTimeValue());
  const [expenseMethod, setExpenseMethod] = useState<"cash" | "card" | "mobile">("cash");
  const [reference, setReference] = useState("");
  const [description, setDescription] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [categoryDescription, setCategoryDescription] = useState("");
  const [editingCategoryId, setEditingCategoryId] = useState("");
  const [categorySaving, setCategorySaving] = useState(false);

  const loadCategoriesAndBranches = useCallback(async () => {
    if (!companyId) return;
    const [categoryResponse, branchResponse] = await Promise.all([
      api.get(`/expenses/categories/${companyId}`),
      api.get(`/inventory/branches/${companyId}`),
    ]);
    setCategories(categoryResponse.data);
    setBranches(branchResponse.data);
    setExpenseCategoryId((current) => current || categoryResponse.data.find((item: ExpenseCategory) => item.active)?.id || "");
    setExpenseBranchId((current) => current || branchResponse.data[0]?.id || "");
  }, [companyId]);

  const loadExpenses = useCallback(async (preserveMessage = false) => {
    if (!companyId) return;
    setLoading(true);
    if (!preserveMessage) setMessage("");
    try {
      const params: Record<string, string | number | undefined> = {
        start_at: dateFrom ? new Date(`${dateFrom}T00:00:00`).toISOString() : undefined,
        end_at: dateTo ? nextDay(dateTo) : undefined,
        branch_id: branchId || undefined,
        category_id: categoryId || undefined,
        payment_method: paymentMethod || undefined,
        search: appliedSearch || undefined,
        limit: 500,
      };
      if (userFilter.startsWith("employee:")) params.employee_id = userFilter.slice(9);
      if (userFilter.startsWith("user:")) params.actor_user_id = userFilter.slice(5);
      const response = await api.get(`/expenses/${companyId}`, { params });
      setExpenses(response.data);
    } catch (error: any) {
      setExpenses([]);
      setMessage(error.response?.status === 403 ? "You do not have permission to view expense history." : error.response?.data?.detail || "Failed to load expenses.");
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, branchId, categoryId, companyId, dateFrom, dateTo, paymentMethod, userFilter]);

  useEffect(() => {
    void loadCategoriesAndBranches().catch((error: any) => setMessage(error.response?.data?.detail || "Failed to load expense categories and branches."));
  }, [loadCategoriesAndBranches]);
  useEffect(() => { void loadExpenses(); }, [loadExpenses]);

  const summary = useMemo(() => expenseSummary(expenses), [expenses]);
  const breakdown = useMemo(() => categoryBreakdown(expenses), [expenses]);
  const currency = expenses[0]?.currency_code || "USD";
  const userOptions = useMemo(() => {
    const options = new Map<string, string>();
    expenses.forEach((expense) => {
      if (expense.employee_id) options.set(`employee:${expense.employee_id}`, `Employee ${shortId(expense.employee_id)}`);
      else if (expense.actor_user_id) options.set(`user:${expense.actor_user_id}`, `Backoffice ${shortId(expense.actor_user_id)}`);
    });
    return [...options.entries()];
  }, [expenses]);

  function openExpense() {
    setAmountValue("");
    setExpenseCategoryId(categories.find((item) => item.active)?.id || "");
    setExpenseBranchId(branches[0]?.id || "");
    setOccurredAt(localDateTimeValue());
    setExpenseMethod("cash");
    setReference("");
    setDescription("");
    setMessage("");
    setExpenseOpen(true);
  }

  async function saveExpense(event: FormEvent) {
    event.preventDefault();
    const amountError = expenseAmountError(amountValue);
    if (amountError) { setMessage(amountError); return; }
    if (!expenseCategoryId) { setMessage("Select an active expense category."); return; }
    if (!expenseBranchId) { setMessage("Select a permitted branch."); return; }
    if (!description.trim()) { setMessage("Enter an expense description or note."); return; }
    setSaving(true);
    setMessage("");
    try {
      await api.post("/expenses", {
        company_id: companyId,
        category_id: expenseCategoryId,
        branch_id: expenseBranchId,
        amount: Number(amountValue),
        occurred_at: new Date(occurredAt).toISOString(),
        payment_method: expenseMethod,
        reference: reference.trim() || null,
        description: description.trim(),
        idempotency_key: requestKey(),
      });
      setExpenseOpen(false);
      setMessage(`Expense posted. ${expenseMethod === "cash" ? "Expected cash-on-hand and " : ""}Net profit have been updated.`);
      await loadExpenses(true);
    } catch (error: any) {
      setMessage(!error.response ? "An online connection is required to post this expense." : error.response?.data?.detail || "Failed to post expense.");
    } finally { setSaving(false); }
  }

  function editCategory(category: ExpenseCategory) {
    setEditingCategoryId(category.id);
    setCategoryName(category.name);
    setCategoryDescription(category.description || "");
  }

  function resetCategoryForm() {
    setEditingCategoryId("");
    setCategoryName("");
    setCategoryDescription("");
  }

  async function saveCategory(event: FormEvent) {
    event.preventDefault();
    if (!categoryName.trim()) { setMessage("Category name is required."); return; }
    setCategorySaving(true);
    setMessage("");
    try {
      if (editingCategoryId) await api.patch(`/expenses/categories/${companyId}/${editingCategoryId}`, { name: categoryName.trim(), description: categoryDescription.trim() || null });
      else await api.post("/expenses/categories", { company_id: companyId, name: categoryName.trim(), description: categoryDescription.trim() || null });
      setMessage(editingCategoryId ? "Expense category updated." : "Expense category created.");
      resetCategoryForm();
      await loadCategoriesAndBranches();
    } catch (error: any) {
      setMessage(error.response?.data?.detail || "Failed to save expense category.");
    } finally { setCategorySaving(false); }
  }

  async function toggleCategory(category: ExpenseCategory) {
    setMessage("");
    try {
      await api.patch(`/expenses/categories/${companyId}/${category.id}`, { active: !category.active });
      setMessage(`${category.name} is now ${category.active ? "inactive" : "active"}.`);
      await loadCategoriesAndBranches();
    } catch (error: any) { setMessage(error.response?.data?.detail || "Failed to change category status."); }
  }

  async function deleteCategory(category: ExpenseCategory) {
    if (!window.confirm(`Delete unused category ${category.name}? Categories referenced by posted expenses cannot be deleted.`)) return;
    setMessage("");
    try {
      await api.delete(`/expenses/categories/${companyId}/${category.id}`);
      setMessage(`${category.name} deleted.`);
      if (editingCategoryId === category.id) resetCategoryForm();
      await loadCategoriesAndBranches();
    } catch (error: any) { setMessage(error.response?.data?.detail || "Category could not be deleted. Deactivate categories already used by posted expenses."); }
  }

  function branchName(id: string) {
    const branch = branches.find((item) => item.id === id);
    return branch ? `${branch.shop_name} — ${branch.name}` : `Branch ${shortId(id)}`;
  }

  return <div className="expenses-page">
    <section className="expense-summary-grid" aria-label="Expense summary">
      <article><span>Total expenses</span><strong>{money(summary.total, currency)}</strong><small>Selected filters and period</small></article>
      <article><span>Cash expenses</span><strong>{money(summary.cash, currency)}</strong><small>Reduces expected cash-on-hand</small></article>
      <article><span>Card expenses</span><strong>{money(summary.card, currency)}</strong><small>Classified as card payments</small></article>
      <article><span>Mobile / transfer</span><strong>{money(summary.mobile, currency)}</strong><small>Classified as mobile payments</small></article>
    </section>

    <section className="expense-filter-panel">
      <div className="expense-section-header"><div><h2>Expense history</h2><p>Posted expenses are immutable, reduce net profit, and never count as sales revenue.</p></div><button type="button" className="primary-button expense-add-button" onClick={openExpense}>Add Expense</button></div>
      <form className="expense-filters" onSubmit={(event) => { event.preventDefault(); const value = search.trim(); if (value === appliedSearch) void loadExpenses(); else setAppliedSearch(value); }}>
        <label>Date from<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
        <label>Date to<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
        <label>Branch<select value={branchId} onChange={(event) => setBranchId(event.target.value)}><option value="">All permitted branches</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.shop_name} — {branch.name}</option>)}</select></label>
        <label>Category<select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}><option value="">All categories</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}{category.active ? "" : " (inactive)"}</option>)}</select></label>
        <label>Payment method<select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}><option value="">All methods</option><option value="cash">Cash</option><option value="card">Card</option><option value="mobile">Mobile / Transfer</option></select></label>
        <label>User / actor<select value={userFilter} onChange={(event) => setUserFilter(event.target.value)}><option value="">All users</option>{userOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="expense-search-field">Search reference or note<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Reference or description" /></label>
        <button type="submit" disabled={loading}>{loading ? "Filtering…" : "Apply filters"}</button>
      </form>
      {message && <p className="expense-message" role="status">{message}</p>}
    </section>

    <section className="expense-history-panel">
      <div className="expense-table-wrapper"><table className="expense-responsive-table"><thead><tr><th>Date/time</th><th>Category</th><th>Description/reference</th><th>Amount</th><th>Payment</th><th>Branch</th><th>User</th><th>Status</th></tr></thead><tbody>
        {!loading && expenses.length === 0 && <tr><td colSpan={8} className="expense-empty">No expenses match these filters.</td></tr>}
        {expenses.map((expense) => <tr key={expense.id}>
          <td data-label="Date/time">{new Date(expense.occurred_at).toLocaleString()}</td>
          <td data-label="Category"><strong>{expense.category_name || "Uncategorised"}</strong></td>
          <td data-label="Description / reference"><strong>{expense.description}</strong><small>{expense.reference || "No reference"}</small></td>
          <td data-label="Amount"><strong>{money(expense.amount, expense.currency_code)}</strong></td>
          <td data-label="Payment"><span className={`expense-method expense-method-${expense.payment_method}`}>{expense.payment_method === "mobile" ? "Mobile / Transfer" : expense.payment_method[0].toUpperCase() + expense.payment_method.slice(1)}</span></td>
          <td data-label="Branch">{branchName(expense.branch_id)}</td>
          <td data-label="User">{expense.employee_id ? `Employee ${shortId(expense.employee_id)}` : `Backoffice ${shortId(expense.actor_user_id)}`}</td>
          <td data-label="Status"><span className="expense-posted">Posted</span></td>
        </tr>)}
      </tbody></table></div>
    </section>

    <section className="expense-bottom-grid">
      <article className="expense-category-breakdown"><div className="expense-section-header"><div><h2>Category breakdown</h2><p>Expense totals for the selected filters.</p></div></div>{breakdown.length ? <div className="expense-breakdown-list">{breakdown.map((item) => <div key={item.categoryId}><span>{item.name}</span><strong>{money(item.amount, currency)}</strong></div>)}</div> : <p className="expense-empty-state">No category totals for this period.</p>}</article>
      <article className="expense-category-manager"><div className="expense-section-header"><div><h2>Expense categories</h2><p>Inactive categories remain available in historical reports.</p></div></div>
        <form className="expense-category-form" onSubmit={(event) => void saveCategory(event)}><label>Category name<input maxLength={120} value={categoryName} onChange={(event) => setCategoryName(event.target.value)} /></label><label>Description<input maxLength={1000} value={categoryDescription} onChange={(event) => setCategoryDescription(event.target.value)} /></label><div className="expense-category-form-actions">{editingCategoryId && <button type="button" onClick={resetCategoryForm}>Cancel</button>}<button type="submit" className="primary-button" disabled={categorySaving}>{categorySaving ? "Saving…" : editingCategoryId ? "Save Category" : "Create Category"}</button></div></form>
        <div className="expense-category-list">{categories.map((category) => <div key={category.id}><div><strong>{category.name}</strong><small>{category.description || "No description"}</small><span className={category.active ? "expense-category-active" : "expense-category-inactive"}>{category.active ? "Active" : "Inactive"}</span></div><div className="expense-category-actions"><button type="button" onClick={() => editCategory(category)}>Edit</button><button type="button" onClick={() => void toggleCategory(category)}>{category.active ? "Deactivate" : "Activate"}</button><button type="button" className="expense-delete-button" onClick={() => void deleteCategory(category)}>Delete</button></div></div>)}</div>
      </article>
    </section>

    {expenseOpen && <div className="expense-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setExpenseOpen(false); }}><section className="expense-dialog" role="dialog" aria-modal="true" aria-labelledby="expense-dialog-title">
      <div className="expense-section-header"><div><h2 id="expense-dialog-title">Add Expense</h2><p>Posting creates an immutable financial transaction.</p></div><button type="button" onClick={() => setExpenseOpen(false)} disabled={saving}>Close</button></div>
      <form onSubmit={(event) => void saveExpense(event)}><div className="expense-form-grid">
        <label>Amount<input type="number" inputMode="decimal" min="0.01" step="0.01" value={amountValue} onChange={(event) => setAmountValue(event.target.value)} required /></label>
        <label>Category<select value={expenseCategoryId} onChange={(event) => setExpenseCategoryId(event.target.value)} required><option value="">Select active category</option>{categories.filter((category) => category.active).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
        <label>Branch<select value={expenseBranchId} onChange={(event) => setExpenseBranchId(event.target.value)} required><option value="">Select permitted branch</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.shop_name} — {branch.name}</option>)}</select></label>
        <label>Date and time<input type="datetime-local" value={occurredAt} onChange={(event) => setOccurredAt(event.target.value)} required /></label>
        <label>Payment method<select value={expenseMethod} onChange={(event) => setExpenseMethod(event.target.value as typeof expenseMethod)}><option value="cash">Cash</option><option value="card">Card</option><option value="mobile">Mobile / Transfer</option></select></label>
        <label>Reference<input maxLength={160} value={reference} onChange={(event) => setReference(event.target.value)} placeholder="Optional receipt or transaction reference" /></label>
        <label className="expense-description-field">Description / note<textarea maxLength={1000} value={description} onChange={(event) => setDescription(event.target.value)} required /></label>
      </div>
      {expenseAmountError(amountValue) && amountValue !== "" && <p className="expense-validation" role="alert">{expenseAmountError(amountValue)}</p>}
      <div className="expense-treatment-note"><strong>Financial treatment</strong><span>This expense reduces net profit by its gross amount and is not sales revenue.{expenseMethod === "cash" ? " Cash also reduces expected cash-on-hand." : ` It remains classified as ${expenseMethod === "mobile" ? "mobile / transfer" : expenseMethod}.`}</span></div>
      <button type="submit" className="primary-button expense-save-button" disabled={saving || Boolean(expenseAmountError(amountValue))}>{saving ? "Posting…" : "Post Expense"}</button>
      </form>
    </section></div>}
  </div>;
}
