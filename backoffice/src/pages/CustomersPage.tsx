import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import "./customers.css";

type Customer = {
  id: string;
  company_id: string;
  customer_code: string;
  name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  credit_enabled: boolean;
  unlimited_credit: boolean;
  credit_limit: string | number | null;
  credit_terms_days: number;
  active: boolean;
  outstanding_balance: string | number;
  available_credit: string | number | null;
};

type CustomerTransaction = {
  transaction_type: "credit_sale" | "settlement";
  transaction_id: string;
  sale_id: string | null;
  receipt_number: string | null;
  amount: string | number;
  payment_method: string | null;
  branch_id: string;
  occurred_at: string;
  due_date: string | null;
  reference: string | null;
};

type Receivable = {
  id: string;
  sale_id: string;
  branch_id: string;
  currency_code: string;
  original_amount: string | number;
  amount_settled: string | number;
  outstanding_balance: string | number;
  due_date: string;
  status: string;
  created_at: string;
  sale_receipt_number: string | null;
};

type Settlement = {
  id: string;
  receivable_id: string;
  branch_id: string;
  amount: string | number;
  payment_method: string;
  reference: string | null;
  note: string | null;
  received_at: string;
  receipt_number: string;
};

type CustomerForm = {
  name: string;
  customerCode: string;
  phone: string;
  email: string;
  address: string;
  active: boolean;
  creditEnabled: boolean;
  unlimitedCredit: boolean;
  creditLimit: string;
  creditTermsDays: string;
};

const emptyForm: CustomerForm = {
  name: "",
  customerCode: "",
  phone: "",
  email: "",
  address: "",
  active: true,
  creditEnabled: false,
  unlimitedCredit: false,
  creditLimit: "",
  creditTermsDays: "0",
};

function amount(value: string | number | null | undefined, currency?: string) {
  const number = Number(value || 0);
  if (!currency) return number.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(number);
  } catch {
    return `${currency} ${number.toFixed(2)}`;
  }
}

function dateTime(value: string) {
  return new Date(value).toLocaleString();
}

function titleCase(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function CustomersPage({ companyId }: { companyId: string }) {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [form, setForm] = useState<CustomerForm>(emptyForm);
  const [selected, setSelected] = useState<Customer | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [transactions, setTransactions] = useState<CustomerTransaction[]>([]);
  const [receivables, setReceivables] = useState<Receivable[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [settlementsRestricted, setSettlementsRestricted] = useState(false);
  const [detailTab, setDetailTab] = useState<"history" | "receivables" | "settlements">("history");

  const loadCustomers = useCallback(async (clearMessage = true) => {
    if (!companyId) return;
    setLoading(true);
    if (clearMessage) setMessage("");
    try {
      const response = await api.get(`/customers/${companyId}`, {
        params: {
          search: appliedSearch || undefined,
          active: activeFilter === "all" ? undefined : activeFilter === "active",
          limit: 500,
        },
      });
      setCustomers(response.data);
    } catch (error: any) {
      setCustomers([]);
      setMessage(error.response?.status === 403
        ? "You do not have permission to view customers."
        : error.response?.data?.detail || "Failed to load customers.");
    } finally {
      setLoading(false);
    }
  }, [activeFilter, appliedSearch, companyId]);

  useEffect(() => { void loadCustomers(); }, [loadCustomers]);

  const summary = useMemo(() => ({
    total: customers.length,
    active: customers.filter((customer) => customer.active).length,
    credit: customers.filter((customer) => customer.credit_enabled).length,
    outstanding: customers.reduce((total, customer) => total + Number(customer.outstanding_balance || 0), 0),
  }), [customers]);

  function openEdit(customer: Customer) {
    setEditingId(customer.id);
    setForm({
      name: customer.name,
      customerCode: customer.customer_code,
      phone: customer.phone || "",
      email: customer.email || "",
      address: customer.address || "",
      active: customer.active,
      creditEnabled: customer.credit_enabled,
      unlimitedCredit: customer.unlimited_credit,
      creditLimit: customer.credit_limit === null ? "" : String(customer.credit_limit),
      creditTermsDays: String(customer.credit_terms_days),
    });
    setEditorOpen(true);
    setMessage("");
  }

  function closeEditor() {
    if (saving) return;
    setEditorOpen(false);
    setEditingId("");
    setForm(emptyForm);
  }

  async function saveCustomer(event: FormEvent) {
    event.preventDefault();
    if (!form.name.trim() || !form.customerCode.trim()) {
      setMessage("Customer name and customer code are required.");
      return;
    }
    if (form.creditEnabled && !form.unlimitedCredit && (form.creditLimit === "" || Number(form.creditLimit) < 0)) {
      setMessage("Enter a valid monetary credit limit or choose unlimited credit.");
      return;
    }
    const terms = Number(form.creditTermsDays);
    if (!Number.isInteger(terms) || terms < 0 || terms > 3650) {
      setMessage("Credit terms must be between 0 and 3650 days.");
      return;
    }

    const payload = {
      name: form.name.trim(),
      customer_code: form.customerCode.trim(),
      phone: form.phone.trim() || null,
      email: form.email.trim() || null,
      address: form.address.trim() || null,
      active: form.active,
      credit_enabled: form.creditEnabled,
      unlimited_credit: form.creditEnabled && form.unlimitedCredit,
      credit_limit: form.creditEnabled && !form.unlimitedCredit ? Number(form.creditLimit) : null,
      credit_terms_days: terms,
    };

    setSaving(true);
    setMessage("");
    try {
      await api.patch(`/customers/${companyId}/${editingId}`, payload);
      setMessage("Customer configuration updated successfully.");
      setEditorOpen(false);
      setEditingId("");
      setForm(emptyForm);
      await loadCustomers(false);
      if (selected?.id === editingId) await openDetails(editingId);
    } catch (error: any) {
      setMessage(error.response?.status === 403
        ? "You do not have permission to manage customers."
        : error.response?.data?.detail || "Failed to save customer.");
    } finally {
      setSaving(false);
    }
  }

  async function openDetails(customerId: string) {
    setDetailsLoading(true);
    setSettlementsRestricted(false);
    setMessage("");
    setDetailTab("history");
    const [customerResult, historyResult, receivableResult, settlementResult] = await Promise.allSettled([
      api.get(`/customers/${companyId}/${customerId}`),
      api.get(`/customers/${companyId}/${customerId}/transactions`),
      api.get(`/credit/${companyId}/receivables`, { params: { customer_id: customerId, limit: 500 } }),
      api.get(`/credit/${companyId}/settlements`, { params: { customer_id: customerId, limit: 500 } }),
    ]);
    if (customerResult.status === "rejected") {
      setSelected(null);
      setMessage(customerResult.reason?.response?.data?.detail || "Failed to load customer details.");
      setDetailsLoading(false);
      return;
    }
    setSelected(customerResult.value.data);
    setTransactions(historyResult.status === "fulfilled" ? historyResult.value.data : []);
    setReceivables(receivableResult.status === "fulfilled" ? receivableResult.value.data : []);
    setSettlements(settlementResult.status === "fulfilled" ? settlementResult.value.data : []);
    setSettlementsRestricted(settlementResult.status === "rejected" && settlementResult.reason?.response?.status === 403);
    setDetailsLoading(false);
  }

  const detailCurrency = receivables[0]?.currency_code;

  return <div className="customers-page">
    <section className="customer-summary-grid" aria-label="Customer summary">
      <article><span>Customers shown</span><strong>{summary.total}</strong><small>Current search and status filter</small></article>
      <article><span>Active</span><strong>{summary.active}</strong><small>Available for new activity</small></article>
      <article><span>Credit enabled</span><strong>{summary.credit}</strong><small>Explicitly approved for credit</small></article>
      <article><span>Outstanding</span><strong>{amount(summary.outstanding)}</strong><small>Across customers shown</small></article>
    </section>

    <section className="customer-list-panel">
      <div className="customer-section-header">
        <div><h2>Customer report</h2><p>Review customer balances and statements. New customers are created at the POS.</p></div>
      </div>

      <form className="customer-filters" onSubmit={(event) => {
        event.preventDefault();
        const nextSearch = search.trim();
        if (nextSearch === appliedSearch) void loadCustomers();
        else setAppliedSearch(nextSearch);
      }}>
        <label>Search customers<input aria-label="Search customers" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name, phone or customer code" /></label>
        <label>Status<select value={activeFilter} onChange={(event) => setActiveFilter(event.target.value)}><option value="all">All customers</option><option value="active">Active</option><option value="inactive">Inactive</option></select></label>
        <button type="submit" disabled={loading}>{loading ? "Searching…" : "Search"}</button>
      </form>

      {message && <p className="customer-message" role="status">{message}</p>}
      <div className="customer-table-wrapper">
        <table className="customer-table">
          <thead><tr><th>Customer</th><th>Contact</th><th>Credit policy</th><th>Outstanding</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {!loading && customers.length === 0 && <tr><td colSpan={6} className="customer-empty">No customers match these filters.</td></tr>}
            {customers.map((customer) => <tr key={customer.id}>
              <td data-label="Customer"><strong>{customer.name}</strong><small>{customer.customer_code}</small></td>
              <td data-label="Contact"><span>{customer.phone || "No phone"}</span><small>{customer.email || "No email"}</small></td>
              <td data-label="Credit">{customer.credit_enabled ? <><strong>{customer.unlimited_credit ? "Unlimited" : `Limit ${amount(customer.credit_limit)}`}</strong><small>{customer.credit_terms_days} day terms</small></> : <span className="customer-muted">Disabled</span>}</td>
              <td data-label="Outstanding"><strong>{amount(customer.outstanding_balance)}</strong></td>
              <td data-label="Status"><span className={customer.active ? "customer-active" : "customer-inactive"}>{customer.active ? "Active" : "Inactive"}</span></td>
              <td data-label="Actions"><div className="customer-row-actions"><button type="button" onClick={() => void openDetails(customer.id)}>Statement</button><button type="button" onClick={() => openEdit(customer)}>Administrative edit</button></div></td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </section>

    {(selected || detailsLoading) && <section className="customer-details-panel" aria-live="polite">
      {detailsLoading ? <div className="customer-detail-loading">Loading customer account…</div> : selected && <>
        <div className="customer-section-header">
          <div><span className="customer-eyebrow">{selected.customer_code}</span><h2>{selected.name}</h2><p>{[selected.phone, selected.email].filter(Boolean).join(" · ") || "No contact details"}</p></div>
          <div className="customer-detail-actions"><button type="button" onClick={() => openEdit(selected)}>Edit Customer</button><button type="button" aria-label="Close customer details" onClick={() => setSelected(null)}>Close</button></div>
        </div>

        <div className="customer-account-grid">
          <article className="customer-balance-card"><span>Current outstanding</span><strong>{amount(selected.outstanding_balance, detailCurrency)}</strong><small>{receivables.filter((item) => Number(item.outstanding_balance) > 0).length} open receivable(s)</small></article>
          <article><span>Credit access</span><strong>{selected.credit_enabled ? "Enabled" : "Disabled"}</strong><small>{selected.credit_enabled ? selected.unlimited_credit ? "Unlimited credit" : `${amount(selected.credit_limit)} limit · ${amount(selected.available_credit)} available` : "New credit sales are blocked"}</small></article>
          <article><span>Credit terms</span><strong>{selected.credit_terms_days} days</strong><small>{selected.active ? "Customer is active" : "Customer is inactive"}</small></article>
          <article><span>Address</span><strong className="customer-address">{selected.address || "Not provided"}</strong><small>Account contact address</small></article>
        </div>

        <div className="customer-detail-tabs" role="tablist" aria-label="Customer account activity">
          <button type="button" role="tab" aria-selected={detailTab === "history"} className={detailTab === "history" ? "active" : ""} onClick={() => setDetailTab("history")}>History ({transactions.length})</button>
          <button type="button" role="tab" aria-selected={detailTab === "receivables"} className={detailTab === "receivables" ? "active" : ""} onClick={() => setDetailTab("receivables")}>Receivables ({receivables.length})</button>
          <button type="button" role="tab" aria-selected={detailTab === "settlements"} className={detailTab === "settlements" ? "active" : ""} onClick={() => setDetailTab("settlements")}>Settlements ({settlements.length})</button>
        </div>

        <div className="customer-activity-list">
          {detailTab === "history" && (transactions.length ? transactions.map((item) => <article key={`${item.transaction_type}-${item.transaction_id}`}><div><strong>{item.transaction_type === "credit_sale" ? "Credit sale" : "Settlement"}</strong><span>{item.receipt_number || item.reference || "No reference"}</span></div><div><strong className={Number(item.amount) < 0 ? "customer-credit" : ""}>{Number(item.amount) < 0 ? "−" : "+"}{amount(Math.abs(Number(item.amount)), detailCurrency)}</strong><span>{dateTime(item.occurred_at)}</span></div></article>) : <p className="customer-empty-state">No customer transactions yet.</p>)}
          {detailTab === "receivables" && (receivables.length ? receivables.map((item) => <article key={item.id}><div><strong>{item.sale_receipt_number || "Credit sale"}</strong><span>Due {new Date(`${item.due_date}T00:00:00`).toLocaleDateString()} · {titleCase(item.status)}</span></div><div><strong>{amount(item.outstanding_balance, item.currency_code)}</strong><span>{amount(item.amount_settled, item.currency_code)} settled of {amount(item.original_amount, item.currency_code)}</span></div></article>) : <p className="customer-empty-state">No credit receivables yet.</p>)}
          {detailTab === "settlements" && (settlementsRestricted ? <p className="customer-empty-state">You do not have permission to view settlement history.</p> : settlements.length ? settlements.map((item) => <article key={item.id}><div><strong>{item.receipt_number}</strong><span>{titleCase(item.payment_method)} · {item.reference || "No reference"}</span></div><div><strong className="customer-credit">{amount(item.amount, detailCurrency)}</strong><span>{dateTime(item.received_at)}</span></div></article>) : <p className="customer-empty-state">No credit settlements yet.</p>)}
        </div>
      </>}
    </section>}

    {editorOpen && <div className="customer-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeEditor(); }}>
      <section className="customer-dialog" role="dialog" aria-modal="true" aria-labelledby="customer-dialog-title">
        <div className="customer-section-header"><div><h2 id="customer-dialog-title">Customer administrative edit</h2><p>Limited contact, status and credit configuration changes are audited.</p></div><button type="button" onClick={closeEditor}>Close</button></div>
        <form onSubmit={(event) => void saveCustomer(event)}>
          <div className="customer-form-grid">
            <label>Customer name<input required maxLength={160} value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} /></label>
            <label>Customer code<input required maxLength={40} value={form.customerCode} onChange={(event) => setForm((current) => ({ ...current, customerCode: event.target.value.toUpperCase() }))} /></label>
            <label>Phone<input maxLength={60} value={form.phone} onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))} /></label>
            <label>Email<input type="email" maxLength={160} value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} /></label>
            <label className="customer-address-field">Address<textarea maxLength={1000} value={form.address} onChange={(event) => setForm((current) => ({ ...current, address: event.target.value }))} /></label>
          </div>

          <fieldset className="customer-credit-policy"><legend>Credit configuration</legend>
            <label className="customer-toggle"><input type="checkbox" checked={form.creditEnabled} onChange={(event) => setForm((current) => ({ ...current, creditEnabled: event.target.checked, unlimitedCredit: event.target.checked ? current.unlimitedCredit : false, creditLimit: event.target.checked ? current.creditLimit : "" }))} /><span><strong>Enable customer credit</strong><small>Required before this customer can make new credit purchases.</small></span></label>
            <label className="customer-toggle"><input type="checkbox" checked={form.unlimitedCredit} disabled={!form.creditEnabled} onChange={(event) => setForm((current) => ({ ...current, unlimitedCredit: event.target.checked, creditLimit: event.target.checked ? "" : current.creditLimit }))} /><span><strong>Unlimited credit</strong><small>Explicitly allow credit without a monetary limit.</small></span></label>
            <div className="customer-credit-fields">
              <label>Credit limit<input type="number" min="0" step="0.01" required={form.creditEnabled && !form.unlimitedCredit} disabled={!form.creditEnabled || form.unlimitedCredit} value={form.creditLimit} onChange={(event) => setForm((current) => ({ ...current, creditLimit: event.target.value }))} placeholder="0.00" /></label>
              <label>Credit terms / due days<input type="number" min="0" max="3650" step="1" disabled={!form.creditEnabled} value={form.creditTermsDays} onChange={(event) => setForm((current) => ({ ...current, creditTermsDays: event.target.value }))} /></label>
            </div>
            {editingId && selected?.id === editingId && Number(selected.outstanding_balance) > 0 && <p className="customer-policy-note">Changing credit access does not alter the existing outstanding balance of {amount(selected.outstanding_balance)}.</p>}
          </fieldset>

          <label className="customer-toggle customer-active-toggle"><input type="checkbox" checked={form.active} onChange={(event) => setForm((current) => ({ ...current, active: event.target.checked }))} /><span><strong>Active customer</strong><small>Inactive customers remain in history but cannot be used for new credit sales.</small></span></label>
          <button className="primary-button customer-save-button" type="submit" disabled={saving}>{saving ? "Saving…" : "Save Changes"}</button>
        </form>
      </section>
    </div>}
  </div>;
}
