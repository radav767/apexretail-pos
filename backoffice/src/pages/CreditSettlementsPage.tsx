import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import {
  balanceAfterSettlement,
  matchesReceivableFilters,
  matchesSettlementFilters,
  receivableDisplayStatus,
  settlementAmountError,
} from "./creditSettlementLogic";
import type { ReceivableFilterRow, SettlementFilterRow } from "./creditSettlementLogic";
import "./credit-settlements.css";

type Customer = {
  id: string;
  company_id: string;
  customer_code: string;
  name: string;
  phone: string | null;
  active: boolean;
  credit_enabled: boolean;
  outstanding_balance: string | number;
};

type Receivable = ReceivableFilterRow & {
  id: string;
  sale_id: string;
  currency_code: string;
  customer_name: string | null;
  customer_code: string | null;
  sale_receipt_number: string | null;
};

type Settlement = SettlementFilterRow & {
  id: string;
  actor_user_id: string | null;
  cashier_employee_id: string | null;
  amount: string | number;
  reference: string | null;
  note: string | null;
  receipt_number: string;
  created_at: string;
};

type Branch = { id: string; shop_id: string; shop_name: string; name: string };

const today = new Date();
const defaultDateTo = today.toISOString().slice(0, 10);

function money(value: string | number, currency = "USD") {
  const amount = Number(value || 0);
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount); }
  catch { return `${currency} ${amount.toFixed(2)}`; }
}

function shortId(value: string | null) {
  return value ? value.slice(0, 8).toUpperCase() : "Unknown";
}

function statusLabel(status: ReturnType<typeof receivableDisplayStatus>) {
  return status === "partially_paid" ? "Partially Paid" : status[0].toUpperCase() + status.slice(1);
}

function branchLabel(branches: Branch[], branchId: string) {
  const branch = branches.find((item) => item.id === branchId);
  return branch ? `${branch.shop_name} — ${branch.name}` : `Branch ${shortId(branchId)}`;
}

function requestKey() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `settlement-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function CreditSettlementsPage({ companyId }: { companyId: string }) {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [receivables, setReceivables] = useState<Receivable[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [customerSearch, setCustomerSearch] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [branchId, setBranchId] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("");
  const [status, setStatus] = useState("outstanding");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState(defaultDateTo);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [selectedReceivable, setSelectedReceivable] = useState<Receivable | null>(null);
  const [settlementAmount, setSettlementAmount] = useState("");
  const [settlementMethod, setSettlementMethod] = useState<"cash" | "card" | "mobile">("cash");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [posting, setPosting] = useState(false);

  const loadData = useCallback(async (preserveMessage = false) => {
    if (!companyId) return;
    setLoading(true);
    if (!preserveMessage) setMessage("");
    try {
      const [customerResponse, receivableResponse, settlementResponse, branchResponse] = await Promise.all([
        api.get(`/customers/${companyId}`, { params: { limit: 500 } }),
        api.get(`/credit/${companyId}/receivables`, { params: { limit: 500 } }),
        api.get(`/credit/${companyId}/settlements`, { params: { limit: 500 } }),
        api.get(`/inventory/branches/${companyId}`),
      ]);
      setCustomers(customerResponse.data);
      setReceivables(receivableResponse.data);
      setSettlements(settlementResponse.data);
      setBranches(branchResponse.data);
    } catch (error: any) {
      if (error.response?.status === 403) setMessage("You do not have permission to view or post credit settlements.");
      else setMessage(error.response?.data?.detail || "Failed to load credit settlement data.");
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { void loadData(); }, [loadData]);

  const visibleCustomers = useMemo(() => {
    const query = customerSearch.trim().toLowerCase();
    if (!query) return customers;
    return customers.filter((customer) => [customer.name, customer.customer_code, customer.phone || ""].some((value) => value.toLowerCase().includes(query)));
  }, [customerSearch, customers]);

  const filters = useMemo(
    () => ({ companyId, customerId, branchId, paymentMethod, status, dateFrom, dateTo }),
    [companyId, customerId, branchId, paymentMethod, status, dateFrom, dateTo],
  );
  const filteredReceivables = useMemo(
    () => receivables.filter((item) => matchesReceivableFilters(item, filters)),
    [receivables, filters],
  );
  const receivableById = useMemo(() => new Map(receivables.map((item) => [item.id, item])), [receivables]);
  const filteredSettlements = useMemo(
    () => settlements.filter((item) => matchesSettlementFilters(item, filters, receivableById.get(item.receivable_id))),
    [settlements, filters, receivableById],
  );
  const customerById = useMemo(() => new Map(customers.map((item) => [item.id, item])), [customers]);
  const selectedCustomer = customerId ? customerById.get(customerId) : undefined;
  const totalOutstanding = (selectedCustomer ? Number(selectedCustomer.outstanding_balance) : filteredReceivables.reduce((sum, item) => sum + Number(item.outstanding_balance), 0));
  const cashSettlements = filteredSettlements.filter((item) => item.payment_method === "cash").reduce((sum, item) => sum + Number(item.amount), 0);
  const amountError = selectedReceivable ? settlementAmountError(settlementAmount, selectedReceivable.outstanding_balance) : "Select a receivable.";
  const projectedBalance = selectedReceivable ? balanceAfterSettlement(settlementAmount, selectedReceivable.outstanding_balance) : 0;

  function openSettlement(receivable: Receivable) {
    setSelectedReceivable(receivable);
    setSettlementAmount(String(receivable.outstanding_balance));
    setSettlementMethod("cash");
    setReference("");
    setNote("");
    setReviewing(false);
    setMessage("");
  }

  function closeSettlement() {
    if (posting) return;
    setSelectedReceivable(null);
    setReviewing(false);
  }

  function reviewSettlement(event: FormEvent) {
    event.preventDefault();
    if (amountError) {
      setMessage(amountError);
      return;
    }
    setMessage("");
    setReviewing(true);
  }

  async function postSettlement() {
    if (!selectedReceivable || amountError) {
      setMessage(amountError || "Select a receivable.");
      return;
    }
    setPosting(true);
    setMessage("");
    try {
      await api.post("/credit/settlements", {
        company_id: companyId,
        receivable_id: selectedReceivable.id,
        branch_id: selectedReceivable.branch_id,
        amount: Number(settlementAmount),
        payment_method: settlementMethod,
        reference: reference.trim() || null,
        note: note.trim() || null,
        idempotency_key: requestKey(),
      });
      const customerName = selectedReceivable.customer_name || "Customer";
      const settledCustomerId = selectedReceivable.customer_id;
      setSelectedReceivable(null);
      setReviewing(false);
      setCustomerSearch("");
      setCustomerId(settledCustomerId);
      setStatus("all");
      setMessage(`Settlement posted for ${customerName}. Customer balances and history are now up to date.`);
      await loadData(true);
      window.dispatchEvent(new CustomEvent("apex:credit-settlement-posted", { detail: { customerId: settledCustomerId } }));
    } catch (error: any) {
      setReviewing(false);
      setMessage(!error.response
        ? "Credit settlements are online-only. Reconnect and try again; this payment was not queued."
        : error.response?.data?.detail || "Failed to post settlement.");
    } finally {
      setPosting(false);
    }
  }

  return <div className="credit-settlements-page">
    <section className="credit-summary-grid" aria-label="Credit settlement summary">
      <article><span>{selectedCustomer ? `${selectedCustomer.name} outstanding` : "Filtered outstanding"}</span><strong>{money(totalOutstanding, filteredReceivables[0]?.currency_code)}</strong><small>Authoritative customer receivable balance</small></article>
      <article><span>Open receivables</span><strong>{filteredReceivables.filter((item) => receivableDisplayStatus(item) !== "paid").length}</strong><small>Open, partially paid or overdue</small></article>
      <article><span>Settlements shown</span><strong>{filteredSettlements.length}</strong><small>Posted immutable transactions</small></article>
      <article><span>Cash settlements</span><strong>{money(cashSettlements, filteredReceivables[0]?.currency_code)}</strong><small>Included in expected cash-on-hand</small></article>
    </section>

    <section className="credit-filter-panel">
      <div className="credit-section-header"><div><h2>Find customer credit</h2><p>Filters remain company-scoped and branch access is enforced by the server.</p></div><button type="button" onClick={() => void loadData()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button></div>
      <div className="credit-filters">
        <label>Search customer<input value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} placeholder="Name, phone or code" /></label>
        <label>Select customer<select value={customerId} onChange={(event) => setCustomerId(event.target.value)}><option value="">All customers</option>{visibleCustomers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name} — {customer.customer_code}</option>)}</select></label>
        <label>Branch<select value={branchId} onChange={(event) => setBranchId(event.target.value)}><option value="">All permitted branches</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.shop_name} — {branch.name}</option>)}</select></label>
        <label>Payment method<select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}><option value="">All methods</option><option value="cash">Cash</option><option value="card">Card</option><option value="mobile">Mobile / Transfer</option></select></label>
        <label>Account status<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="outstanding">All outstanding</option><option value="open">Open</option><option value="partially_paid">Partially Paid</option><option value="paid">Paid</option><option value="overdue">Overdue</option><option value="all">All statuses</option></select></label>
        <label>Date from<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
        <label>Date to<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
      </div>
      {message && <p className="credit-message" role="status">{message}</p>}
    </section>

    <section className="credit-receivables-panel">
      <div className="credit-section-header"><div><h2>Credit sales and receivables</h2><p>Select an open receivable to post a full or partial payment.</p></div><span className="credit-online-badge">Online posting only</span></div>
      <div className="credit-table-wrapper"><table className="credit-responsive-table"><thead><tr><th>Customer / sale</th><th>Sale date</th><th>Original</th><th>Settled</th><th>Outstanding</th><th>Due date</th><th>Branch</th><th>Status</th><th>Action</th></tr></thead><tbody>
        {!loading && filteredReceivables.length === 0 && <tr><td colSpan={9} className="credit-empty">No receivables match these filters.</td></tr>}
        {filteredReceivables.map((item) => {
          const displayStatus = receivableDisplayStatus(item);
          return <tr key={item.id}>
            <td data-label="Customer / sale"><strong>{item.customer_name || customerById.get(item.customer_id)?.name || "Customer"}</strong><small>{item.sale_receipt_number || `Sale ${shortId(item.sale_id)}`}</small></td>
            <td data-label="Sale date">{new Date(item.created_at).toLocaleDateString()}</td>
            <td data-label="Original">{money(item.original_amount, item.currency_code)}</td>
            <td data-label="Settled">{money(item.amount_settled, item.currency_code)}</td>
            <td data-label="Outstanding"><strong>{money(item.outstanding_balance, item.currency_code)}</strong></td>
            <td data-label="Due date">{new Date(`${item.due_date}T00:00:00`).toLocaleDateString()}</td>
            <td data-label="Branch">{branchLabel(branches, item.branch_id)}</td>
            <td data-label="Status"><span className={`credit-status credit-status-${displayStatus}`}>{statusLabel(displayStatus)}</span></td>
            <td data-label="Action"><button type="button" disabled={displayStatus === "paid"} onClick={() => openSettlement(item)}>{displayStatus === "paid" ? "Paid" : "Settle"}</button></td>
          </tr>;
        })}
      </tbody></table></div>
    </section>

    <section className="credit-history-panel">
      <div className="credit-section-header"><div><h2>Settlement history</h2><p>Posted settlements are immutable and do not rewrite the original credit sale.</p></div></div>
      <div className="credit-table-wrapper"><table className="credit-responsive-table"><thead><tr><th>Customer</th><th>Sale / settlement</th><th>Amount</th><th>Method</th><th>Reference</th><th>Branch</th><th>User</th><th>Date and time</th></tr></thead><tbody>
        {!loading && filteredSettlements.length === 0 && <tr><td colSpan={8} className="credit-empty">No settlements match these filters.</td></tr>}
        {filteredSettlements.map((item) => {
          const receivable = receivableById.get(item.receivable_id);
          const customer = customerById.get(item.customer_id);
          return <tr key={item.id}>
            <td data-label="Customer"><strong>{customer?.name || receivable?.customer_name || "Customer"}</strong><small>{customer?.customer_code || receivable?.customer_code}</small></td>
            <td data-label="Sale / settlement"><strong>{receivable?.sale_receipt_number || `Sale ${shortId(receivable?.sale_id || null)}`}</strong><small>{item.receipt_number}</small></td>
            <td data-label="Amount"><strong>{money(item.amount, receivable?.currency_code)}</strong></td>
            <td data-label="Method"><span className={`credit-method credit-method-${item.payment_method}`}>{item.payment_method === "mobile" ? "Mobile / Transfer" : statusLabel(item.payment_method as "open")}</span></td>
            <td data-label="Reference">{item.reference || "—"}{item.note && <small>{item.note}</small>}</td>
            <td data-label="Branch">{branchLabel(branches, item.branch_id)}</td>
            <td data-label="User">{item.cashier_employee_id ? `Employee ${shortId(item.cashier_employee_id)}` : `Backoffice ${shortId(item.actor_user_id)}`}</td>
            <td data-label="Date and time">{new Date(item.received_at).toLocaleString()}</td>
          </tr>;
        })}
      </tbody></table></div>
    </section>

    {selectedReceivable && <div className="credit-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeSettlement(); }}>
      <section className="credit-dialog" role="dialog" aria-modal="true" aria-labelledby="credit-dialog-title">
        <div className="credit-section-header"><div><span className="credit-eyebrow">{selectedReceivable.sale_receipt_number || "Credit sale"}</span><h2 id="credit-dialog-title">Post settlement</h2><p>{selectedReceivable.customer_name} · {branchLabel(branches, selectedReceivable.branch_id)}</p></div><button type="button" onClick={closeSettlement}>Close</button></div>
        <div className="credit-balance-preview"><div><span>Balance before</span><strong>{money(selectedReceivable.outstanding_balance, selectedReceivable.currency_code)}</strong></div><div><span>Settlement</span><strong>{money(Number(settlementAmount || 0), selectedReceivable.currency_code)}</strong></div><div><span>Balance after</span><strong>{money(projectedBalance, selectedReceivable.currency_code)}</strong></div></div>
        {!reviewing ? <form onSubmit={reviewSettlement}>
          <div className="credit-settlement-form">
            <label>Settlement amount<input type="number" inputMode="decimal" min="0.01" max={Number(selectedReceivable.outstanding_balance)} step="0.01" value={settlementAmount} onChange={(event) => { setSettlementAmount(event.target.value); setReviewing(false); }} required /></label>
            <label>Payment method<select value={settlementMethod} onChange={(event) => setSettlementMethod(event.target.value as typeof settlementMethod)}><option value="cash">Cash</option><option value="card">Card</option><option value="mobile">Mobile / Transfer</option></select></label>
            <label>Reference<input maxLength={160} value={reference} onChange={(event) => setReference(event.target.value)} placeholder="Receipt, transfer or card reference" /></label>
            <label className="credit-note-field">Optional note<textarea maxLength={1000} value={note} onChange={(event) => setNote(event.target.value)} /></label>
          </div>
          {amountError && settlementAmount !== "" && <p className="credit-validation" role="alert">{amountError}</p>}
          <div className="credit-dialog-actions"><button type="button" onClick={() => setSettlementAmount(String(selectedReceivable.outstanding_balance))}>Pay full balance</button><button type="submit" className="primary-button" disabled={Boolean(amountError)}>Review settlement</button></div>
        </form> : <div className="credit-confirmation">
          <h3>Confirm immutable settlement</h3>
          <p>This posts a separate {settlementMethod === "mobile" ? "mobile / transfer" : settlementMethod} transaction. The original sale amount remains unchanged.</p>
          {settlementMethod === "cash" && <p className="credit-cash-note">This cash payment will increase expected cash-on-hand.</p>}
          <div className="credit-dialog-actions"><button type="button" onClick={() => setReviewing(false)} disabled={posting}>Back</button><button type="button" className="primary-button" onClick={() => void postSettlement()} disabled={posting}>{posting ? "Posting online…" : `Confirm ${money(settlementAmount, selectedReceivable.currency_code)}`}</button></div>
        </div>}
      </section>
    </div>}
  </div>;
}
