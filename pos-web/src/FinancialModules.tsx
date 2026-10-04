import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, getApiErrorMessage } from "./api/client";
import type { CreditCustomer } from "./creditSale";
import { searchCustomers } from "./customerApi";
import { isDeviceOnline } from "./offline/offlineAuth";
import { sendReceiptToPrinter } from "./printing/printerConfig";
import { encodeBase64 } from "./printing/receiptFormatter";
import type { PrinterConfig } from "./printing/types";
import "./financial-modules.css";

export type FinancialModuleName = "Customers" | "Credit Settlements" | "Expenses";

type Cashier = { id: string; name: string; role: string; permissions?: Record<string, boolean> };
type Transaction = { transaction_type: string; transaction_id: string; sale_id?: string | null; receipt_number?: string | null; amount: string; payment_method?: string | null; occurred_at: string; due_date?: string | null; reference?: string | null; actor_id?: string | null; actor_name?: string | null };
type Receivable = { id: string; customer_id: string; customer_name?: string; customer_code?: string; sale_receipt_number?: string; original_amount: string; amount_settled: string; outstanding_balance: string; due_date: string; status: string; created_at: string };
type Settlement = { id: string; receivable_id: string; customer_id: string; amount: string; payment_method: string; reference?: string | null; note?: string | null; received_at: string; receipt_number: string; outstanding_balance?: string | null; actor_id?: string | null; actor_name?: string | null };
type ExpenseCategory = { id: string; name: string; active: boolean };
type Expense = { id: string; category_name?: string; amount: string; payment_method: string; description: string; reference?: string | null; occurred_at: string; employee_id?: string | null; actor_user_id?: string | null; actor_id?: string | null; actor_name?: string | null };

type Props = { activeModule: FinancialModuleName; companyId: string; branchId: string; cashier: Cashier | null; currencySymbol: string; decimalPlaces: number; printerConfig: PrinterConfig; onBackToSales: () => void };

const blankCustomer = { customer_code: "", name: "", phone: "", email: "", address: "", active: true, credit_enabled: false, unlimited_credit: false, credit_limit: "", credit_terms_days: "0" };
const money = (value: string | number, symbol: string, places: number) => `${symbol}${Number(value || 0).toFixed(places)}`;
const requestKey = (prefix: string) => `${prefix}-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`}`;

export default function FinancialModules({ activeModule, companyId, branchId, cashier, currencySymbol, decimalPlaces, printerConfig, onBackToSales }: Props) {
  const [customers, setCustomers] = useState<CreditCustomer[]>([]);
  const [selected, setSelected] = useState<CreditCustomer | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [receivables, setReceivables] = useState<Receivable[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [categories, setCategories] = useState<ExpenseCategory[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showCustomerForm, setShowCustomerForm] = useState(false);
  const [customerForm, setCustomerForm] = useState({ ...blankCustomer });
  const [editingCustomer, setEditingCustomer] = useState<CreditCustomer | null>(null);
  const [selectedReceivable, setSelectedReceivable] = useState<Receivable | null>(null);
  const [settlementAmount, setSettlementAmount] = useState("");
  const [settlementMethod, setSettlementMethod] = useState("cash");
  const [settlementReference, setSettlementReference] = useState("");
  const [settlementNote, setSettlementNote] = useState("");
  const settlementKey = useRef(requestKey("pos-settlement"));
  const [expenseForm, setExpenseForm] = useState({ category_id: "", amount: "", payment_method: "cash", reference: "", description: "" });
  const expenseKey = useRef(requestKey("pos-expense"));

  const canManageCredit = cashier?.role === "owner" || cashier?.role === "administrator" || Boolean(cashier?.permissions?.customers_manage);
  const canSettle = cashier?.role === "owner" || cashier?.role === "administrator" || Boolean(cashier?.permissions?.credit_settlements);
  const canPostExpense = cashier?.role === "owner" || cashier?.role === "administrator" || Boolean(cashier?.permissions?.expenses_create);

  const loadCustomers = useCallback(async () => {
    setCustomers(await searchCustomers(companyId, search, { limit: 500 }));
  }, [companyId, search]);

  const refreshCustomer = useCallback(async (customer: CreditCustomer) => {
    const [detail, history, open, paid] = await Promise.all([
      api.get(`/customers/${companyId}/${customer.id}`),
      api.get(`/customers/${companyId}/${customer.id}/transactions`),
      api.get(`/credit/${companyId}/receivables`, { params: { customer_id: customer.id, limit: 500 } }),
      canSettle
        ? api.get(`/credit/${companyId}/settlements`, { params: { customer_id: customer.id, limit: 500 } })
        : Promise.resolve({ data: [] }),
    ]);
    setSelected(detail.data);
    setTransactions(Array.isArray(history.data) ? history.data : []);
    setReceivables(Array.isArray(open.data) ? open.data : []);
    setSettlements(Array.isArray(paid.data) ? paid.data : []);
  }, [canSettle, companyId]);

  const loadExpenses = useCallback(async () => {
    const start = new Date(); start.setHours(0, 0, 0, 0);
    const [categoryResponse, expenseResponse] = await Promise.all([
      api.get(`/expenses/categories/${companyId}`, { params: { active: true } }),
      api.get(`/expenses/${companyId}`, { params: { branch_id: branchId, start_at: start.toISOString(), limit: 100 } }),
    ]);
    const nextCategories = Array.isArray(categoryResponse.data) ? categoryResponse.data : [];
    setCategories(nextCategories);
    setExpenses(Array.isArray(expenseResponse.data) ? expenseResponse.data : []);
    setExpenseForm((current) => ({ ...current, category_id: current.category_id || nextCategories[0]?.id || "" }));
  }, [branchId, companyId]);

  useEffect(() => {
    let live = true;
    setError(""); setNotice(""); setSelected(null); setTransactions([]); setReceivables([]); setSettlements([]);
    (async () => {
      try {
        if (!(await isDeviceOnline())) throw new Error(`${activeModule} requires an online connection.`);
        if (activeModule === "Expenses") await loadExpenses(); else await loadCustomers();
      } catch (reason) { if (live) setError(getApiErrorMessage(reason, `Unable to load ${activeModule}`)); }
    })();
    return () => { live = false; };
  }, [activeModule, loadCustomers, loadExpenses]);

  const openCustomerForm = (customer?: CreditCustomer) => {
    setEditingCustomer(customer || null);
    setCustomerForm(customer ? { customer_code: customer.customer_code, name: customer.name, phone: (customer as CreditCustomer & {phone?: string}).phone || "", email: (customer as CreditCustomer & {email?: string}).email || "", address: (customer as CreditCustomer & {address?: string}).address || "", active: customer.active, credit_enabled: customer.credit_enabled, unlimited_credit: customer.unlimited_credit, credit_limit: customer.credit_limit || "", credit_terms_days: String(customer.credit_terms_days) } : { ...blankCustomer });
    setShowCustomerForm(true); setError("");
  };

  const saveCustomer = async () => {
    if (!customerForm.name.trim() || (!editingCustomer && !customerForm.customer_code.trim())) { setError("Customer name and code are required."); return; }
    if (!(await isDeviceOnline())) { setError("Customer changes require an online connection."); return; }
    setBusy(true); setError("");
    try {
      const contact = { name: customerForm.name.trim(), phone: customerForm.phone.trim() || null, email: customerForm.email.trim() || null, address: customerForm.address.trim() || null };
      const policy = canManageCredit ? { active: customerForm.active, credit_enabled: customerForm.credit_enabled, unlimited_credit: customerForm.credit_enabled && customerForm.unlimited_credit, credit_limit: customerForm.credit_enabled && !customerForm.unlimited_credit ? customerForm.credit_limit : null, credit_terms_days: customerForm.credit_enabled ? Number(customerForm.credit_terms_days || 0) : 0 } : {};
      const response = editingCustomer
        ? await api.patch(`/customers/${companyId}/${editingCustomer.id}`, { ...contact, ...policy })
        : await api.post("/customers", { company_id: companyId, customer_code: customerForm.customer_code.trim(), ...contact, ...(canManageCredit ? policy : { active: true, credit_enabled: false, unlimited_credit: false, credit_limit: null, credit_terms_days: 0 }) });
      setShowCustomerForm(false); setNotice(editingCustomer ? "Customer updated." : "Customer created.");
      await loadCustomers(); await refreshCustomer(response.data);
    } catch (reason) { setError(getApiErrorMessage(reason, "Unable to save customer")); } finally { setBusy(false); }
  };

  const postSettlement = async () => {
    const amount = Number(settlementAmount);
    if (!selectedReceivable || !Number.isFinite(amount) || amount <= 0) { setError("Select a receivable and enter an amount greater than zero."); return; }
    if (amount > Number(selectedReceivable.outstanding_balance)) { setError("Settlement cannot exceed the outstanding balance."); return; }
    if (!(await isDeviceOnline())) { setError("Credit settlements are online-only."); return; }
    setBusy(true); setError("");
    try {
      const before = Number(selectedReceivable.outstanding_balance);
      const response = await api.post("/credit/settlements", { company_id: companyId, receivable_id: selectedReceivable.id, branch_id: branchId, amount: amount.toFixed(2), payment_method: settlementMethod, reference: settlementReference.trim() || null, note: settlementNote.trim() || null, idempotency_key: settlementKey.current });
      const posted = response.data as Settlement;
      let printMessage = "Receipt printed.";
      try {
        await printSettlement(posted, selectedReceivable, selected, cashier?.name || "Cashier", currencySymbol, decimalPlaces, before, printerConfig);
      } catch (printError) {
        printMessage = `Settlement posted, but printing failed: ${getApiErrorMessage(printError, "Printer unavailable")}`;
      }
      settlementKey.current = requestKey("pos-settlement"); setSettlementAmount(""); setSettlementReference(""); setSettlementNote(""); setSelectedReceivable(null); setNotice(`Settlement ${posted.receipt_number} posted. ${printMessage}`);
      if (selected) await refreshCustomer(selected);
    } catch (reason) { setError(getApiErrorMessage(reason, "Unable to post settlement")); } finally { setBusy(false); }
  };

  const postExpense = async () => {
    const amount = Number(expenseForm.amount);
    if (!expenseForm.category_id || !Number.isFinite(amount) || amount <= 0 || !expenseForm.description.trim()) { setError("Category, amount greater than zero, and description are required."); return; }
    if (!(await isDeviceOnline())) { setError("Expenses are online-only."); return; }
    setBusy(true); setError("");
    try {
      await api.post("/expenses", { company_id: companyId, category_id: expenseForm.category_id, branch_id: branchId, amount: amount.toFixed(2), occurred_at: new Date().toISOString(), payment_method: expenseForm.payment_method, reference: expenseForm.reference.trim() || null, description: expenseForm.description.trim(), idempotency_key: expenseKey.current });
      expenseKey.current = requestKey("pos-expense"); setExpenseForm((current) => ({ ...current, amount: "", reference: "", description: "" })); setNotice("Expense posted. Financial totals and expected cash have been updated."); await loadExpenses();
    } catch (reason) { setError(getApiErrorMessage(reason, "Unable to post expense")); } finally { setBusy(false); }
  };

  const openReceivables = useMemo(() => receivables.filter((item) => Number(item.outstanding_balance) > 0), [receivables]);
  const afterSettlement = selectedReceivable ? Math.max(0, Number(selectedReceivable.outstanding_balance) - Number(settlementAmount || 0)) : 0;

  return <section className="pos-module-overlay financial-module"><div className="pos-module-container">
    <header className="pos-module-header"><div><p className="pos-module-eyebrow">ApexRetail POS · Online</p><h1>{activeModule}</h1><p>{activeModule === "Customers" ? "Customer accounts and credit history" : activeModule === "Credit Settlements" ? "Receive and receipt customer credit payments" : "Post branch expenses and review today’s activity"}</p></div><button className="pos-module-sales-button" onClick={onBackToSales}>Return to Sales</button></header>
    {error && <div role="alert" className="pos-module-notice pos-module-error">{error}</div>}{notice && <div className="pos-module-notice">{notice}</div>}
    {activeModule !== "Expenses" && <>
      <div className="financial-toolbar"><form onSubmit={(event) => { event.preventDefault(); void loadCustomers(); }}><input aria-label="Search customers" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name, phone or customer code"/><button>Search</button></form>{activeModule === "Customers" && <button onClick={() => openCustomerForm()}>Add Customer</button>}</div>
      <div className="financial-split"><section className="financial-panel"><h2>Customers</h2><div className="financial-list">{customers.map((customer) => <button key={customer.id} className={selected?.id === customer.id ? "selected" : ""} onClick={() => void refreshCustomer(customer)}><span><strong>{customer.name}</strong><small>{customer.customer_code} · {customer.active ? "Active" : "Inactive"}</small></span><b>{money(customer.outstanding_balance, currencySymbol, decimalPlaces)}</b></button>)}</div></section>
      <section className="financial-panel">{!selected ? <p>Select a customer to view the account.</p> : <><div className="financial-title"><div><h2>{selected.name}</h2><p>{selected.customer_code}</p></div>{activeModule === "Customers" && <button onClick={() => openCustomerForm(selected)}>Edit</button>}</div><div className="financial-summary"><span>Outstanding<strong>{money(selected.outstanding_balance, currencySymbol, decimalPlaces)}</strong></span><span>Credit<strong>{selected.credit_enabled ? selected.unlimited_credit ? "Unlimited" : money(selected.credit_limit || 0, currencySymbol, decimalPlaces) : "Disabled"}</strong></span><span>Terms<strong>{selected.credit_terms_days} days</strong></span></div>
      {activeModule === "Customers" ? <><h3>Transaction & credit history</h3><div className="financial-table">{transactions.map((row) => <article key={`${row.transaction_type}-${row.transaction_id}`}><span><strong>{row.transaction_type === "credit_sale" ? "Credit sale" : "Settlement"}</strong><small>{row.receipt_number || row.reference || "—"} · {new Date(row.occurred_at).toLocaleString()} · {row.actor_name || row.actor_id || "Unknown"}</small></span><b>{money(row.amount, currencySymbol, decimalPlaces)}</b></article>)}</div></> : <>{!canSettle && <p className="financial-warning">This cashier can view customer balances but does not have settlement permission.</p>}<h3>Open receivables</h3><div className="financial-table">{openReceivables.map((row) => <article key={row.id} className={selectedReceivable?.id === row.id ? "selected" : ""}><button disabled={!canSettle} onClick={() => { setSelectedReceivable(row); setSettlementAmount(row.outstanding_balance); setError(""); }}><span><strong>{row.sale_receipt_number || row.id.slice(0, 8)}</strong><small>{new Date(row.created_at).toLocaleDateString()} · Due {row.due_date} · {row.status}</small></span><b>{money(row.outstanding_balance, currencySymbol, decimalPlaces)}</b></button></article>)}</div>{selectedReceivable && canSettle && <div className="financial-form"><h3>Post settlement</h3><div className="financial-summary"><span>Before<strong>{money(selectedReceivable.outstanding_balance, currencySymbol, decimalPlaces)}</strong></span><span>After<strong>{money(afterSettlement, currencySymbol, decimalPlaces)}</strong></span></div><label>Amount<input inputMode="decimal" value={settlementAmount} onChange={(e) => setSettlementAmount(e.target.value)}/></label><label>Payment method<select value={settlementMethod} onChange={(e) => setSettlementMethod(e.target.value)}><option value="cash">Cash</option><option value="card">Card</option><option value="mobile">Mobile / Transfer</option></select></label><label>Reference<input value={settlementReference} onChange={(e) => setSettlementReference(e.target.value)}/></label><label>Note<textarea value={settlementNote} onChange={(e) => setSettlementNote(e.target.value)}/></label><button disabled={busy} onClick={() => void postSettlement()}>{busy ? "Posting…" : "Confirm settlement"}</button></div>}<h3>Settlement history</h3><div className="financial-table">{settlements.map((row) => <article key={row.id}><span><strong>{row.receipt_number}</strong><small>{row.payment_method.toUpperCase()} · {new Date(row.received_at).toLocaleString()} · {row.actor_name || row.actor_id || "Unknown"}</small></span><b>{money(row.amount, currencySymbol, decimalPlaces)}</b></article>)}</div></>}</>}</section></div>
    </>}
    {activeModule === "Expenses" && <div className="financial-split"><section className="financial-panel"><h2>Add Expense</h2>{!canPostExpense ? <p className="financial-warning">This cashier does not have permission to post expenses.</p> : <div className="financial-form"><label>Category<select value={expenseForm.category_id} onChange={(e) => setExpenseForm({...expenseForm, category_id:e.target.value})}><option value="">Select category</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Amount<input inputMode="decimal" value={expenseForm.amount} onChange={(e) => setExpenseForm({...expenseForm, amount:e.target.value})}/></label><label>Payment method<select value={expenseForm.payment_method} onChange={(e) => setExpenseForm({...expenseForm, payment_method:e.target.value})}><option value="cash">Cash</option><option value="card">Card</option><option value="mobile">Mobile / Transfer</option></select></label><label>Reference<input value={expenseForm.reference} onChange={(e) => setExpenseForm({...expenseForm, reference:e.target.value})}/></label><label>Description / note<textarea value={expenseForm.description} onChange={(e) => setExpenseForm({...expenseForm, description:e.target.value})}/></label><p>Branch and cashier are recorded automatically from this POS session.</p><button disabled={busy} onClick={() => void postExpense()}>{busy ? "Posting…" : "Post expense"}</button></div>}</section><section className="financial-panel"><h2>Today’s expenses</h2><div className="financial-table">{expenses.map((row) => <article key={row.id}><span><strong>{row.category_name || "Expense"}</strong><small>{row.payment_method.toUpperCase()} · {row.reference || row.description} · {new Date(row.occurred_at).toLocaleTimeString()} · {row.actor_name || row.actor_id || "Unknown"}</small></span><b>{money(row.amount, currencySymbol, decimalPlaces)}</b></article>)}</div></section></div>}
    {showCustomerForm && <div className="financial-modal-backdrop"><div className="financial-modal" role="dialog" aria-modal="true"><h2>{editingCustomer ? "Edit Customer" : "Add Customer"}</h2><div className="financial-form"><div className="financial-form-scroll">{!editingCustomer && <label>Customer code<input value={customerForm.customer_code} onChange={(e) => setCustomerForm({...customerForm, customer_code:e.target.value})}/></label>}<label>Name<input value={customerForm.name} onChange={(e) => setCustomerForm({...customerForm, name:e.target.value})}/></label><label>Phone<input value={customerForm.phone} onChange={(e) => setCustomerForm({...customerForm, phone:e.target.value})}/></label><label>Email<input value={customerForm.email} onChange={(e) => setCustomerForm({...customerForm, email:e.target.value})}/></label><label>Address<textarea value={customerForm.address} onChange={(e) => setCustomerForm({...customerForm, address:e.target.value})}/></label>{canManageCredit ? <fieldset><legend>Manager credit configuration</legend><label><input type="checkbox" checked={customerForm.active} onChange={(e) => setCustomerForm({...customerForm, active:e.target.checked})}/> Active</label><label><input type="checkbox" checked={customerForm.credit_enabled} onChange={(e) => setCustomerForm({...customerForm, credit_enabled:e.target.checked})}/> Credit enabled</label><label><input type="checkbox" checked={customerForm.unlimited_credit} disabled={!customerForm.credit_enabled} onChange={(e) => setCustomerForm({...customerForm, unlimited_credit:e.target.checked})}/> Explicit unlimited credit</label><label>Credit limit<input inputMode="decimal" disabled={!customerForm.credit_enabled || customerForm.unlimited_credit} value={customerForm.credit_limit} onChange={(e) => setCustomerForm({...customerForm, credit_limit:e.target.value})}/></label><label>Credit terms / due days<input type="number" disabled={!customerForm.credit_enabled} value={customerForm.credit_terms_days} onChange={(e) => setCustomerForm({...customerForm, credit_terms_days:e.target.value})}/></label></fieldset> : <p>Credit settings and active status require manager permission.</p>}</div><div className="financial-actions"><button onClick={() => setShowCustomerForm(false)}>Cancel</button><button disabled={busy} onClick={() => void saveCustomer()}>{busy ? "Saving…" : "Save"}</button></div></div></div></div>}
  </div></section>;
}

async function printSettlement(settlement: Settlement, receivable: Receivable, customer: CreditCustomer | null, cashier: string, symbol: string, places: number, before: number, config: PrinterConfig) {
  const after = settlement.outstanding_balance == null ? before - Number(settlement.amount) : Number(settlement.outstanding_balance);
  const fields = [
    ["Customer", customer?.name || receivable.customer_name || "Customer"],
    ["Sale", receivable.sale_receipt_number || receivable.id.slice(0,8)],
    ["Cashier", cashier], ["Method", settlement.payment_method.toUpperCase()],
    ["Amount", money(settlement.amount,symbol,places)], ["Before", money(before,symbol,places)],
    ["After", money(after,symbol,places)], ["Reference", settlement.reference || "—"],
  ];
  const escape = (value:string) => value.replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[character] || character));
  const html = `<!doctype html><title>${escape(settlement.receipt_number)}</title><style>body{font-family:monospace;max-width:340px;margin:24px auto}h1{text-align:center;font-size:20px}dl div{display:flex;justify-content:space-between;margin:8px 0}hr{border:0;border-top:1px dashed}</style><h1>ApexRetail Credit Settlement</h1><p>${escape(settlement.receipt_number)}</p><hr><dl>${fields.map(([label,value])=>`<div><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`).join("")}</dl><p>${escape(new Date(settlement.received_at).toLocaleString())}</p>`;
  const text = ["\x1b@", "APEXRETAIL CREDIT SETTLEMENT", settlement.receipt_number, "--------------------------------", ...fields.map(([label,value])=>`${label}: ${value}`), new Date(settlement.received_at).toLocaleString(), "\n\n\n", "\x1dV\x00"].join("\n");
  await sendReceiptToPrinter({ config, html, rawDataBase64: encodeBase64(new TextEncoder().encode(text)), jobName: settlement.receipt_number });
}
