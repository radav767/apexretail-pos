import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, getApiErrorMessage } from "./api/client";
import type { CreditCustomer } from "./creditSale";
import { isDeviceOnline } from "./offline/offlineAuth";
import { sendReceiptToPrinter } from "./printing/printerConfig";
import { encodeBase64 } from "./printing/receiptFormatter";
import type { PrinterConfig } from "./printing/types";
import { convertBaseToForeign, convertForeignToBase, isCurrencyAmountAtLeast, subtractCurrencyAmounts } from "./decimal";
import "./financial-modules.css";

export type FinancialModuleName = "Customers" | "Credit Settlements" | "Expenses";

type Cashier = { id: string; name: string; role: string; permissions?: Record<string, boolean> };
type Transaction = { transaction_type: string; transaction_id: string; sale_id?: string | null; receipt_number?: string | null; amount: string; payment_method?: string | null; occurred_at: string; due_date?: string | null; reference?: string | null; actor_id?: string | null; actor_name?: string | null };
type Receivable = { id: string; customer_id: string; customer_name?: string; customer_code?: string; sale_receipt_number?: string; original_amount: string; amount_settled: string; amount_credited?: string; outstanding_balance: string; due_date: string; status: string; created_at: string };
type Settlement = { id: string; receivable_id: string; customer_id: string; amount: string; base_currency_code?: string | null; payment_currency_code?: string | null; exchange_rate_snapshot?: string | null; original_amount?: string | null; tendered_amount_original?: string | null; change_amount_original?: string | null; payment_method: string; reference?: string | null; note?: string | null; received_at: string; receipt_number: string; outstanding_balance?: string | null; actor_id?: string | null; actor_name?: string | null };
type ExpenseCategory = { id: string; name: string; active: boolean };
type Expense = { id: string; category_name?: string; amount: string; original_amount?: string | null; currency_code?: string | null; base_currency_code?: string | null; exchange_rate_snapshot?: string | null; payment_method: string; description: string; reference?: string | null; occurred_at: string; employee_id?: string | null; actor_user_id?: string | null; actor_id?: string | null; actor_name?: string | null };
type CurrencyOption = { code: string; display_name: string; symbol: string; decimal_places: number; active: boolean; is_base: boolean; cash_accepted: boolean; card_accepted: boolean; mobile_accepted: boolean; current_rate: string | null; current_rate_id: string | null };
type CurrencyConfig = { base_currency_code: string; version: number; multi_currency_enabled: boolean; currencies: CurrencyOption[] };

type Props = { activeModule: FinancialModuleName; companyId: string; branchId: string; cashier: Cashier | null; currencySymbol: string; decimalPlaces: number; printerConfig: PrinterConfig; onBackToSales: () => void };
type PageEnvelope<T> = { items: T[]; page: number; page_size: number; total: number; total_pages: number };
type PageState = Pick<PageEnvelope<unknown>, "page" | "page_size" | "total" | "total_pages">;

const emptyPage = (pageSize = 25): PageState => ({ page: 1, page_size: pageSize, total: 0, total_pages: 0 });
function pageData<T>(value: T[] | PageEnvelope<T>): { items: T[]; meta: PageState } {
  if (Array.isArray(value)) return { items: value, meta: { page: 1, page_size: value.length || 25, total: value.length, total_pages: value.length ? 1 : 0 } };
  return { items: value.items, meta: value };
}
function Pager({ meta, onPage }: { meta: PageState; onPage: (page: number) => void }) {
  return <nav className="financial-pager" aria-label="Pagination"><span>{meta.total} record{meta.total === 1 ? "" : "s"}</span><div><button disabled={meta.page <= 1} onClick={() => onPage(meta.page - 1)}>Previous</button><span>Page {meta.page} of {Math.max(meta.total_pages, 1)}</span><button disabled={meta.page >= meta.total_pages} onClick={() => onPage(meta.page + 1)}>Next</button></div></nav>;
}

const blankCustomer = { customer_code: "", name: "", phone: "", email: "", address: "", active: true, credit_enabled: false, unlimited_credit: false, credit_limit: "", credit_terms_days: "0" };
const money = (value: string | number, symbol: string, places: number) => {
  const raw = String(value ?? "0").trim();
  const [whole = "0", fraction = ""] = raw.split(".");
  return `${symbol}${whole}${places ? `.${(fraction + "0".repeat(places)).slice(0, places)}` : ""}`;
};
const requestKey = (prefix: string) => `${prefix}-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`}`;

export default function FinancialModules({ activeModule, companyId, branchId, cashier, currencySymbol, decimalPlaces, printerConfig, onBackToSales }: Props) {
  const [customers, setCustomers] = useState<CreditCustomer[]>([]);
  const [selected, setSelected] = useState<CreditCustomer | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [receivables, setReceivables] = useState<Receivable[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [categories, setCategories] = useState<ExpenseCategory[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [customerPage, setCustomerPage] = useState<PageState>(emptyPage());
  const [activityPage, setActivityPage] = useState<PageState>(emptyPage());
  const [expensePage, setExpensePage] = useState<PageState>(emptyPage());
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [creditFilter, setCreditFilter] = useState("");
  const [transactionType, setTransactionType] = useState("");
  const [historyFrom, setHistoryFrom] = useState("");
  const [historyTo, setHistoryTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showCustomerForm, setShowCustomerForm] = useState(false);
  const [customerForm, setCustomerForm] = useState({ ...blankCustomer });
  const [editingCustomer, setEditingCustomer] = useState<CreditCustomer | null>(null);
  const [selectedReceivable, setSelectedReceivable] = useState<Receivable | null>(null);
  const [settlementAmount, setSettlementAmount] = useState("");
  const [settlementCurrencyCode, setSettlementCurrencyCode] = useState("");
  const [settlementFull, setSettlementFull] = useState(true);
  const [settlementTendered, setSettlementTendered] = useState("");
  const [settlementMethod, setSettlementMethod] = useState("cash");
  const [settlementReference, setSettlementReference] = useState("");
  const [settlementNote, setSettlementNote] = useState("");
  const settlementKey = useRef(requestKey("pos-settlement"));
  const [expenseForm, setExpenseForm] = useState({ category_id: "", amount: "", currency_code: "", payment_method: "cash", reference: "", description: "" });
  const [currencyConfig, setCurrencyConfig] = useState<CurrencyConfig | null>(null);
  const previousSettlementCurrency = useRef("");
  const expenseKey = useRef(requestKey("pos-expense"));

  const canManageCredit = cashier?.role === "owner" || cashier?.role === "administrator" || Boolean(cashier?.permissions?.customers_manage);
  const canSettle = cashier?.role === "owner" || cashier?.role === "administrator" || Boolean(cashier?.permissions?.credit_settlements);
  const canPostExpense = cashier?.role === "owner" || cashier?.role === "administrator" || Boolean(cashier?.permissions?.expenses_create);

  const loadCurrencyConfig = useCallback(async () => {
    const response = await api.get(`/currencies/${companyId}/pos-config`);
    const config = response.data as CurrencyConfig;
    setCurrencyConfig(config);
    setSettlementCurrencyCode((current) => current || config.base_currency_code);
    setExpenseForm((current) => ({ ...current, currency_code: current.currency_code || config.base_currency_code }));
    return config;
  }, [companyId]);

  const currenciesForMethod = (method: string) => (currencyConfig?.currencies || []).filter((currency) =>
    currency.active && (currency.is_base || currencyConfig?.multi_currency_enabled) &&
    (method === "cash" ? currency.cash_accepted : method === "card" ? currency.card_accepted : currency.mobile_accepted),
  );
  const currencyByCode = (code: string) => currencyConfig?.currencies.find((currency) => currency.code === code) || null;
  const settlementCurrency = currencyByCode(settlementCurrencyCode);
  const expenseCurrency = currencyByCode(expenseForm.currency_code);
  const settlementRate = settlementCurrency?.current_rate || (settlementCurrency?.is_base ? "1" : null);
  const settlementPayAmount = (() => {
    if (!selectedReceivable || !settlementCurrency || !settlementRate) return "";
    try {
      return settlementFull
        ? convertBaseToForeign(selectedReceivable.outstanding_balance, decimalPlaces, settlementRate, settlementCurrency.decimal_places)
        : settlementAmount;
    } catch { return ""; }
  })();
  const settlementBaseAmount = (() => {
    if (!settlementPayAmount || !settlementCurrency || !settlementRate) return "";
    if (settlementFull && selectedReceivable) return selectedReceivable.outstanding_balance;
    try { return convertForeignToBase(settlementPayAmount, settlementCurrency.decimal_places, settlementRate, decimalPlaces); }
    catch { return ""; }
  })();
  const afterSettlement = (() => {
    if (!selectedReceivable) return "0";
    if (settlementFull) return "0";
    try { return subtractCurrencyAmounts(selectedReceivable.outstanding_balance, settlementBaseAmount, decimalPlaces); }
    catch { return "—"; }
  })();

  useEffect(() => {
    if (previousSettlementCurrency.current && previousSettlementCurrency.current !== settlementCurrencyCode && selectedReceivable) {
      setSettlementFull(true);
      setSettlementAmount("");
      setSettlementTendered("");
    }
    previousSettlementCurrency.current = settlementCurrencyCode;
  }, [selectedReceivable, settlementCurrencyCode]);

  const loadCustomers = useCallback(async (page = 1) => {
    setBusy(true);
    try {
      const response = await api.get(`/customers/${companyId}`, { params: { search: search.trim() || undefined, active: activeFilter === "" ? undefined : activeFilter === "active", credit_enabled: creditFilter === "" ? undefined : creditFilter === "enabled", page, page_size: 25 } });
      const result = pageData<CreditCustomer>(response.data);
      setCustomers(result.items); setCustomerPage(result.meta);
    } finally { setBusy(false); }
  }, [activeFilter, companyId, creditFilter, search]);

  const refreshCustomer = useCallback(async (customer: CreditCustomer, page = 1) => {
    const [detail, history, open, paid] = await Promise.all([
      api.get(`/customers/${companyId}/${customer.id}`),
      api.get(`/customers/${companyId}/${customer.id}/transactions`, { params: { transaction_type: transactionType || undefined, start_at: historyFrom ? new Date(`${historyFrom}T00:00:00`).toISOString() : undefined, end_at: historyTo ? new Date(new Date(`${historyTo}T00:00:00`).getTime() + 86400000).toISOString() : undefined, page, page_size: 25 } }),
      api.get(`/credit/${companyId}/receivables`, { params: { customer_id: customer.id, status: activeModule === "Credit Settlements" ? "outstanding" : undefined, page, page_size: 25 } }),
      canSettle
        ? api.get(`/credit/${companyId}/settlements`, { params: { customer_id: customer.id, page, page_size: 25 } })
        : Promise.resolve({ data: [] }),
    ]);
    const historyPage = pageData<Transaction>(history.data);
    const receivablePage = pageData<Receivable>(open.data);
    const settlementPage = pageData<Settlement>(paid.data);
    setSelected(detail.data);
    setTransactions(historyPage.items);
    setReceivables(receivablePage.items);
    setSettlements(settlementPage.items);
    setActivityPage(activeModule === "Customers" ? historyPage.meta : receivablePage.meta);
  }, [activeModule, canSettle, companyId, historyFrom, historyTo, transactionType]);

  const loadExpenses = useCallback(async (page = 1) => {
    const start = new Date(); start.setHours(0, 0, 0, 0);
    const [categoryResponse, expenseResponse] = await Promise.all([
      api.get(`/expenses/categories/${companyId}`, { params: { active: true } }),
      api.get(`/expenses/${companyId}`, { params: { branch_id: branchId, start_at: start.toISOString(), page, page_size: 25 } }),
    ]);
    const nextCategories = Array.isArray(categoryResponse.data) ? categoryResponse.data : [];
    setCategories(nextCategories);
    const result = pageData<Expense>(expenseResponse.data);
    setExpenses(result.items); setExpensePage(result.meta);
    setExpenseForm((current) => ({ ...current, category_id: current.category_id || nextCategories[0]?.id || "" }));
  }, [branchId, companyId]);

  useEffect(() => {
    let live = true;
    setError(""); setNotice(""); setSelected(null); setTransactions([]); setReceivables([]); setSettlements([]);
    (async () => {
      try {
        if (!(await isDeviceOnline())) throw new Error(`${activeModule} requires an online connection.`);
        if (activeModule === "Credit Settlements" || activeModule === "Expenses") await loadCurrencyConfig();
        if (activeModule === "Expenses") await loadExpenses(); else await loadCustomers();
      } catch (reason) { if (live) setError(getApiErrorMessage(reason, `Unable to load ${activeModule}`)); }
    })();
    return () => { live = false; };
  }, [activeModule, loadCurrencyConfig, loadCustomers, loadExpenses]);

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
    const amount = settlementPayAmount;
    if (!selectedReceivable || !amount || !settlementCurrency || !settlementRate || !currencyConfig) { setError("Select an open receivable and a configured payment currency."); return; }
    if (!settlementFull && (!settlementAmount.trim() || !/^\d+(?:\.\d+)?$/.test(settlementAmount) || /^0+(?:\.0*)?$/.test(settlementAmount))) { setError("Enter a settlement amount greater than zero."); return; }
    try {
      if (!isCurrencyAmountAtLeast(selectedReceivable.outstanding_balance, settlementBaseAmount, decimalPlaces)) { setError("Settlement cannot exceed the outstanding balance."); return; }
      if (settlementMethod === "cash" && settlementTendered && !isCurrencyAmountAtLeast(settlementTendered, amount, settlementCurrency.decimal_places)) { setError("Tendered amount is less than the settlement amount."); return; }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Enter a valid settlement amount."); return; }
    if (!(await isDeviceOnline())) { setError("Credit settlements are online-only."); return; }
    setBusy(true); setError("");
    try {
      const before = selectedReceivable.outstanding_balance;
      const response = await api.post("/credit/settlements", {
        company_id: companyId, receivable_id: selectedReceivable.id, branch_id: branchId,
        settle_full: settlementFull, original_amount: amount,
        tendered_amount_original: settlementMethod === "cash" ? settlementTendered || amount : amount,
        payment_currency_code: settlementCurrency.code, exchange_rate_id: settlementCurrency.current_rate_id,
        currency_config_version: currencyConfig.version, payment_method: settlementMethod,
        reference: settlementReference.trim() || null, note: settlementNote.trim() || null,
        idempotency_key: settlementKey.current,
      });
      const posted = response.data as Settlement;
      let printMessage = "Receipt printed.";
      try {
        await printSettlement(posted, selectedReceivable, selected, cashier?.name || "Cashier", currencySymbol, decimalPlaces, before, settlementCurrency.symbol, settlementCurrency.decimal_places, printerConfig);
      } catch (printError) {
        printMessage = `Settlement posted, but printing failed: ${getApiErrorMessage(printError, "Printer unavailable")}`;
      }
      settlementKey.current = requestKey("pos-settlement"); setSettlementAmount(""); setSettlementTendered(""); setSettlementReference(""); setSettlementNote(""); setSelectedReceivable(null); setNotice(`Settlement ${posted.receipt_number} posted. ${printMessage}`);
      if (selected) await refreshCustomer(selected);
    } catch (reason) { setError(getApiErrorMessage(reason, "Unable to post settlement")); } finally { setBusy(false); }
  };

  const postExpense = async () => {
    const amount = expenseForm.amount.trim();
    if (!expenseForm.category_id || !expenseCurrency || !amount || !/^\d+(?:\.\d+)?$/.test(amount) || /^0+(?:\.0*)?$/.test(amount) || !expenseForm.description.trim()) { setError("Category, a valid amount greater than zero, and description are required."); return; }
    try { convertForeignToBase(amount, expenseCurrency.decimal_places, expenseCurrency.current_rate || (expenseCurrency.is_base ? "1" : ""), decimalPlaces); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "A valid exchange rate is required."); return; }
    if (!(await isDeviceOnline())) { setError("Expenses are online-only."); return; }
    setBusy(true); setError("");
    try {
      await api.post("/expenses", { company_id: companyId, category_id: expenseForm.category_id, branch_id: branchId, original_amount: amount, currency_code: expenseCurrency.code, exchange_rate_id: expenseCurrency.current_rate_id, currency_config_version: currencyConfig?.version, occurred_at: new Date().toISOString(), payment_method: expenseForm.payment_method, reference: expenseForm.reference.trim() || null, description: expenseForm.description.trim(), idempotency_key: expenseKey.current });
      expenseKey.current = requestKey("pos-expense"); setExpenseForm((current) => ({ ...current, amount: "", reference: "", description: "" })); setNotice("Expense posted. Financial totals and expected cash have been updated."); await loadExpenses();
    } catch (reason) { setError(getApiErrorMessage(reason, "Unable to post expense")); } finally { setBusy(false); }
  };

  const openReceivables = useMemo(() => receivables.filter((item) => {
    try { return subtractCurrencyAmounts(item.outstanding_balance, "0", decimalPlaces) !== money("0", "", decimalPlaces); }
    catch { return false; }
  }), [decimalPlaces, receivables]);

  return <section className="pos-module-overlay financial-module"><div className="pos-module-container">
    <header className="pos-module-header"><div><p className="pos-module-eyebrow">ApexRetail POS · Online</p><h1>{activeModule}</h1><p>{activeModule === "Customers" ? "Customer accounts and credit history" : activeModule === "Credit Settlements" ? "Receive and receipt customer credit payments" : "Post branch expenses and review today’s activity"}</p></div><button className="pos-module-sales-button" onClick={onBackToSales}>Return to Sales</button></header>
    {error && <div role="alert" className="pos-module-notice pos-module-error">{error}</div>}{notice && <div className="pos-module-notice">{notice}</div>}
    {activeModule !== "Expenses" && <>
      <div className="financial-toolbar"><form onSubmit={(event) => { event.preventDefault(); void loadCustomers(1); }}><input aria-label="Search customers" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name, phone or customer code"/><select aria-label="Customer status" value={activeFilter} onChange={(e) => setActiveFilter(e.target.value)}><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select><select aria-label="Credit status" value={creditFilter} onChange={(e) => setCreditFilter(e.target.value)}><option value="">All credit policies</option><option value="enabled">Credit enabled</option><option value="disabled">Credit disabled</option></select><button>Search</button></form>{activeModule === "Customers" && <button onClick={() => openCustomerForm()}>Add Customer</button>}</div>
      <div className="financial-split"><section className="financial-panel"><h2>Customers</h2>{busy && !customers.length && <p>Loading customers…</p>}<div className="financial-list">{!busy && !customers.length && <p>No customers match this search.</p>}{customers.map((customer) => <button key={customer.id} className={selected?.id === customer.id ? "selected" : ""} onClick={() => void refreshCustomer(customer, 1)}><span><strong>{customer.name}</strong><small>{customer.customer_code} · {customer.active ? "Active" : "Inactive"}</small></span><b>{money(customer.outstanding_balance, currencySymbol, decimalPlaces)}</b></button>)}</div><Pager meta={customerPage} onPage={(page) => void loadCustomers(page)}/></section>
      <section className="financial-panel">{!selected ? <p>Select a customer to view the account.</p> : <><div className="financial-title"><div><h2>{selected.name}</h2><p>{selected.customer_code}</p></div>{activeModule === "Customers" && <button onClick={() => openCustomerForm(selected)}>Edit</button>}</div><div className="financial-summary"><span>Outstanding<strong>{money(selected.outstanding_balance, currencySymbol, decimalPlaces)}</strong></span><span>Credit<strong>{selected.credit_enabled ? selected.unlimited_credit ? "Unlimited" : money(selected.credit_limit || 0, currencySymbol, decimalPlaces) : "Disabled"}</strong></span><span>Terms<strong>{selected.credit_terms_days} days</strong></span></div>
      {activeModule === "Customers" ? <><h3>Transaction & credit history</h3><div className="financial-history-filters"><select aria-label="Transaction type" value={transactionType} onChange={(e) => setTransactionType(e.target.value)}><option value="">All transactions</option><option value="credit_sale">Credit sales</option><option value="settlement">Settlements</option></select><input aria-label="History date from" type="date" value={historyFrom} onChange={(e) => setHistoryFrom(e.target.value)}/><input aria-label="History date to" type="date" value={historyTo} onChange={(e) => setHistoryTo(e.target.value)}/><button onClick={() => void refreshCustomer(selected, 1)}>Apply</button></div><div className="financial-table">{!transactions.length && <p>No customer transactions found.</p>}{transactions.map((row) => <article key={`${row.transaction_type}-${row.transaction_id}`}><span><strong>{row.transaction_type === "credit_sale" ? "Credit sale" : "Settlement"}</strong><small>{row.receipt_number || row.reference || "—"} · {new Date(row.occurred_at).toLocaleString()} · {row.actor_name || row.actor_id || "Unknown"}</small></span><b>{money(row.amount, currencySymbol, decimalPlaces)}</b></article>)}</div></> : <>{!canSettle && <p className="financial-warning">This cashier can view customer balances but does not have settlement permission.</p>}<h3>Open receivables</h3><div className="financial-table">{!openReceivables.length && <p>No open receivables found.</p>}{openReceivables.map((row) => <article key={row.id} className={selectedReceivable?.id === row.id ? "selected" : ""}><button disabled={!canSettle} onClick={() => { setSelectedReceivable(row); setSettlementAmount(""); setSettlementFull(true); setSettlementTendered(""); setSettlementCurrencyCode(currencyConfig?.base_currency_code || ""); setError(""); }}><span><strong>{row.sale_receipt_number || row.id.slice(0, 8)}</strong><small>{new Date(row.created_at).toLocaleDateString()} · Due {row.due_date} · {row.status}</small></span><b>{money(row.outstanding_balance, currencySymbol, decimalPlaces)}</b></button></article>)}</div>{selectedReceivable && canSettle && <div className="financial-form"><h3>Post settlement</h3><div className="financial-summary"><span>Outstanding ({currencyConfig?.base_currency_code || "base"})<strong>{money(selectedReceivable.outstanding_balance, currencySymbol, decimalPlaces)}</strong></span><span>Projected balance<strong>{money(afterSettlement, currencySymbol, decimalPlaces)}</strong></span></div><label>Payment method<select value={settlementMethod} onChange={(e) => { const method = e.target.value; setSettlementMethod(method); const accepted = currenciesForMethod(method); if (!accepted.some((currency) => currency.code === settlementCurrencyCode)) setSettlementCurrencyCode(accepted[0]?.code || ""); }}><option value="cash">Cash</option><option value="card">Card</option><option value="mobile">Mobile / Transfer</option></select></label><label>Payment currency<select aria-label="Settlement payment currency" value={settlementCurrencyCode} onChange={(e) => setSettlementCurrencyCode(e.target.value)}>{currenciesForMethod(settlementMethod).map((currency) => <option key={currency.code} value={currency.code}>{currency.code} · {currency.display_name}</option>)}</select></label>{settlementCurrency && <p>Rate: 1 {currencyConfig?.base_currency_code} = {settlementRate} {settlementCurrency.code}</p>}<label><span>Amount to apply ({settlementCurrency?.code || "currency"})</span><input inputMode="decimal" disabled={settlementFull} value={settlementFull ? settlementPayAmount : settlementAmount} onChange={(e) => { setSettlementFull(false); setSettlementAmount(e.target.value); }}/></label><button type="button" onClick={() => { setSettlementFull(true); setSettlementAmount(""); }}>Settle full balance</button>{settlementMethod === "cash" && <><label>Tendered ({settlementCurrency?.code || "currency"})<input inputMode="decimal" value={settlementTendered} placeholder={settlementPayAmount || "Enter amount received"} onChange={(e) => setSettlementTendered(e.target.value)}/></label><p>Change: {settlementCurrency ? money(settlementTendered ? (() => { try { return subtractCurrencyAmounts(settlementTendered, settlementPayAmount, settlementCurrency.decimal_places); } catch { return "0"; } })() : "0", settlementCurrency.symbol, settlementCurrency.decimal_places) : "—"}</p></>}<p>Applied base amount: {money(settlementBaseAmount || "0", currencySymbol, decimalPlaces)}</p><label>Reference<input value={settlementReference} onChange={(e) => setSettlementReference(e.target.value)}/></label><label>Note<textarea value={settlementNote} onChange={(e) => setSettlementNote(e.target.value)}/></label><button disabled={busy || !settlementCurrency || !settlementRate} onClick={() => void postSettlement()}>{busy ? "Posting…" : "Confirm settlement"}</button></div>}<h3>Settlement history</h3><div className="financial-table">{settlements.map((row) => { const currency = currencyByCode(row.payment_currency_code || "") ; return <article key={row.id}><span><strong>{row.receipt_number}</strong><small>{row.payment_method.toUpperCase()} · {row.original_amount ? money(row.original_amount, currency?.symbol || row.payment_currency_code || "", currency?.decimal_places ?? 2) : money(row.amount, currencySymbol, decimalPlaces)} {row.payment_currency_code || currencyConfig?.base_currency_code || ""} · {new Date(row.received_at).toLocaleString()} · {row.actor_name || row.actor_id || "Unknown"}</small></span><b>{money(row.amount, currencySymbol, decimalPlaces)} {row.base_currency_code || currencyConfig?.base_currency_code}</b></article>; })}</div></>}<Pager meta={activityPage} onPage={(page) => void refreshCustomer(selected, page)}/></>}</section></div>
    </>}
    {activeModule === "Credit Settlements" && selectedReceivable && canSettle && settlementFull && <div className="financial-panel"><button type="button" onClick={() => { setSettlementFull(false); setSettlementAmount(settlementPayAmount); }}>Enter partial amount</button></div>}
    {activeModule === "Expenses" && <div className="financial-split"><section className="financial-panel"><h2>Add Expense</h2>{!canPostExpense ? <p className="financial-warning">This cashier does not have permission to post expenses.</p> : <div className="financial-form"><label>Category<select value={expenseForm.category_id} onChange={(e) => setExpenseForm({...expenseForm, category_id:e.target.value})}><option value="">Select category</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Amount<input inputMode="decimal" value={expenseForm.amount} onChange={(e) => setExpenseForm({...expenseForm, amount:e.target.value})}/></label><label>Payment method<select value={expenseForm.payment_method} onChange={(e) => { const method=e.target.value; setExpenseForm({...expenseForm, payment_method:method, currency_code:currenciesForMethod(method).some((currency) => currency.code === expenseForm.currency_code) ? expenseForm.currency_code : currenciesForMethod(method)[0]?.code || ""}); }}><option value="cash">Cash</option><option value="card">Card</option><option value="mobile">Mobile / Transfer</option></select></label><label>Payment currency<select aria-label="Expense payment currency" value={expenseForm.currency_code} onChange={(e) => setExpenseForm({...expenseForm, currency_code:e.target.value})}>{currenciesForMethod(expenseForm.payment_method).map((currency) => <option key={currency.code} value={currency.code}>{currency.code} · {currency.display_name}</option>)}</select></label>{expenseCurrency && <><p>Rate: 1 {currencyConfig?.base_currency_code} = {expenseCurrency.current_rate || (expenseCurrency.is_base ? "1" : "Unavailable")} {expenseCurrency.code}</p><p>Base-currency expense: {(() => { try { return money(convertForeignToBase(expenseForm.amount || "0", expenseCurrency.decimal_places, expenseCurrency.current_rate || (expenseCurrency.is_base ? "1" : ""), decimalPlaces), currencySymbol, decimalPlaces); } catch { return "—"; } })()}</p></>}<label>Reference<input value={expenseForm.reference} onChange={(e) => setExpenseForm({...expenseForm, reference:e.target.value})}/></label><label>Description / note<textarea value={expenseForm.description} onChange={(e) => setExpenseForm({...expenseForm, description:e.target.value})}/></label><p>Branch, cashier, and a matching open shift are recorded from this POS session.</p><button disabled={busy || !expenseCurrency || (!expenseCurrency.is_base && !expenseCurrency.current_rate)} onClick={() => void postExpense()}>{busy ? "Posting…" : "Post expense"}</button></div>}</section><section className="financial-panel"><h2>Today’s expenses</h2><div className="financial-table">{!busy && !expenses.length && <p>No expenses found today.</p>}{expenses.map((row) => { const currency = currencyByCode(row.currency_code || ""); return <article key={row.id}><span><strong>{row.category_name || "Expense"}</strong><small>{row.payment_method.toUpperCase()} · {row.reference || row.description} · {new Date(row.occurred_at).toLocaleTimeString()} · {row.actor_name || row.actor_id || "Unknown"}</small></span><b>{money(row.original_amount || row.amount, currency?.symbol || row.currency_code || currencySymbol, currency?.decimal_places ?? decimalPlaces)} {row.currency_code || row.base_currency_code || currencyConfig?.base_currency_code}</b></article>; })}</div><Pager meta={expensePage} onPage={(page) => void loadExpenses(page)}/></section></div>}
    {showCustomerForm && <div className="financial-modal-backdrop"><div className="financial-modal" role="dialog" aria-modal="true"><h2>{editingCustomer ? "Edit Customer" : "Add Customer"}</h2><div className="financial-form"><div className="financial-form-scroll">{!editingCustomer && <label>Customer code<input value={customerForm.customer_code} onChange={(e) => setCustomerForm({...customerForm, customer_code:e.target.value})}/></label>}<label>Name<input value={customerForm.name} onChange={(e) => setCustomerForm({...customerForm, name:e.target.value})}/></label><label>Phone<input value={customerForm.phone} onChange={(e) => setCustomerForm({...customerForm, phone:e.target.value})}/></label><label>Email<input value={customerForm.email} onChange={(e) => setCustomerForm({...customerForm, email:e.target.value})}/></label><label>Address<textarea value={customerForm.address} onChange={(e) => setCustomerForm({...customerForm, address:e.target.value})}/></label>{canManageCredit ? <fieldset><legend>Manager credit configuration</legend><label><input type="checkbox" checked={customerForm.active} onChange={(e) => setCustomerForm({...customerForm, active:e.target.checked})}/> Active</label><label><input type="checkbox" checked={customerForm.credit_enabled} onChange={(e) => setCustomerForm({...customerForm, credit_enabled:e.target.checked})}/> Credit enabled</label><label><input type="checkbox" checked={customerForm.unlimited_credit} disabled={!customerForm.credit_enabled} onChange={(e) => setCustomerForm({...customerForm, unlimited_credit:e.target.checked})}/> Explicit unlimited credit</label><label>Credit limit<input inputMode="decimal" disabled={!customerForm.credit_enabled || customerForm.unlimited_credit} value={customerForm.credit_limit} onChange={(e) => setCustomerForm({...customerForm, credit_limit:e.target.value})}/></label><label>Credit terms / due days<input type="number" disabled={!customerForm.credit_enabled} value={customerForm.credit_terms_days} onChange={(e) => setCustomerForm({...customerForm, credit_terms_days:e.target.value})}/></label></fieldset> : <p>Credit settings and active status require manager permission.</p>}</div><div className="financial-actions"><button onClick={() => setShowCustomerForm(false)}>Cancel</button><button disabled={busy} onClick={() => void saveCustomer()}>{busy ? "Saving…" : "Save"}</button></div></div></div></div>}
  </div></section>;
}

async function printSettlement(settlement: Settlement, receivable: Receivable, customer: CreditCustomer | null, cashier: string, symbol: string, places: number, before: string, paymentSymbol: string, paymentPlaces: number, config: PrinterConfig) {
  const after = settlement.outstanding_balance == null ? subtractCurrencyAmounts(before, settlement.amount, places) : settlement.outstanding_balance;
  const paymentCurrency = settlement.payment_currency_code || settlement.base_currency_code || "";
  const fields = [
    ["Customer", customer?.name || receivable.customer_name || "Customer"],
    ["Sale", receivable.sale_receipt_number || receivable.id.slice(0,8)],
    ["Cashier", cashier], ["Method", settlement.payment_method.toUpperCase()],
    ["Applied (base)", `${money(settlement.amount,symbol,places)} ${settlement.base_currency_code || ""}`],
    ["Paid", `${money(settlement.original_amount || settlement.amount, paymentSymbol, paymentPlaces)} ${paymentCurrency}`],
    ...(settlement.exchange_rate_snapshot ? [["Rate", `1 ${settlement.base_currency_code} = ${settlement.exchange_rate_snapshot} ${paymentCurrency}`]] : []),
    ...(settlement.payment_method === "cash" ? [["Tendered", `${money(settlement.tendered_amount_original || settlement.original_amount || settlement.amount, paymentSymbol, paymentPlaces)} ${paymentCurrency}`], ["Change", `${money(settlement.change_amount_original || "0", paymentSymbol, paymentPlaces)} ${paymentCurrency}`]] : []),
    ["Before", `${money(before,symbol,places)} ${settlement.base_currency_code || ""}`],
    ["After", `${money(after,symbol,places)} ${settlement.base_currency_code || ""}`], ["Reference", settlement.reference || "—"],
  ];
  const escape = (value:string) => value.replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[character] || character));
  const html = `<!doctype html><title>${escape(settlement.receipt_number)}</title><style>body{font-family:monospace;max-width:340px;margin:24px auto}h1{text-align:center;font-size:20px}dl div{display:flex;justify-content:space-between;margin:8px 0}hr{border:0;border-top:1px dashed}</style><h1>ApexRetail Credit Settlement</h1><p>${escape(settlement.receipt_number)}</p><hr><dl>${fields.map(([label,value])=>`<div><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`).join("")}</dl><p>${escape(new Date(settlement.received_at).toLocaleString())}</p>`;
  const text = ["\x1b@", "APEXRETAIL CREDIT SETTLEMENT", settlement.receipt_number, "--------------------------------", ...fields.map(([label,value])=>`${label}: ${value}`), new Date(settlement.received_at).toLocaleString(), "\n\n\n", "\x1dV\x00"].join("\n");
  await sendReceiptToPrinter({ config, html, rawDataBase64: encodeBase64(new TextEncoder().encode(text)), jobName: settlement.receipt_number });
}
