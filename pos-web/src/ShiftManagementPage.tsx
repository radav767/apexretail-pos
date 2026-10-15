import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, getApiErrorMessage } from "./api/client";
import { isDeviceOnline } from "./offline/offlineAuth";
import "./shift-management.css";

type Cashier = { id: string; name: string; role: string };
type CurrencyConfig = {
  code: string; display_name: string; symbol: string; decimal_places: number;
  active: boolean; cash_accepted: boolean;
};
type ShiftCurrency = {
  currency_code: string; currency_name: string; symbol: string; decimal_places: number;
  cash_accepted: boolean; opening_float: string; cash_sales: string; cash_refunds: string;
  cash_settlements: string; cash_expenses: string; cash_in: string; cash_out: string;
  cash_paid_out: string; expected_cash: string; counted_cash: string | null; variance: string | null;
};
export type ShiftRecord = {
  id: string; shift_number: string; company_id: string; shop_id: string; branch_id: string;
  device_id: string; employee_id: string; cashier_name?: string | null; shop_name?: string | null;
  branch_name?: string | null; register_name?: string | null; status: "open" | "closed";
  opened_at: string; closed_at: string | null; opening_note?: string | null; closing_note?: string | null;
  offline_shift_token?: string | null;
  currencies: ShiftCurrency[]; cash_movements?: CashMovement[];
  summary: { total_sales_base?: string | null; base_currency_code?: string | null };
};
type CashMovement = {
  id: string; movement_type: "cash_in" | "cash_out"; currency_code: string; amount: string;
  reason: string; actor_name?: string | null; created_at: string;
};
type PageResult = { items: ShiftRecord[]; page: number; page_size: number; total: number; total_pages: number };

type Props = {
  companyId: string;
  branchId: string;
  cashier: Cashier | null;
  onBackToSales: () => void;
  onPrintShiftSummary: (shift: ShiftRecord) => Promise<void>;
  onShiftChanged?: (shift: ShiftRecord | null) => void;
};

const emptyPage: PageResult = { items: [], page: 1, page_size: 10, total: 0, total_pages: 0 };
const formatted = (value: string | number | null | undefined, currency: Pick<ShiftCurrency, "currency_code" | "symbol" | "decimal_places">) => {
  const amount = Number(value ?? 0);
  if (!Number.isFinite(amount)) return "—";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency", currency: currency.currency_code,
      minimumFractionDigits: currency.decimal_places, maximumFractionDigits: currency.decimal_places,
    }).format(amount);
  } catch {
    return `${currency.symbol}${amount.toFixed(currency.decimal_places)} ${currency.currency_code}`;
  }
};
const amountLabel = (value: string | number | null | undefined, currency: Pick<ShiftCurrency, "currency_code" | "symbol" | "decimal_places">) =>
  formatted(value, currency);
function validAmount(value: string, decimalPlaces: number, positiveOnly = false) {
  const pattern = decimalPlaces === 0 ? /^\d+$/ : new RegExp(`^\\d+(?:\\.\\d{1,${decimalPlaces}})?$`);
  return pattern.test(value) && (!positiveOnly || /[1-9]/.test(value));
}
const idempotencyKey = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;

export default function ShiftManagementPage({ companyId, branchId, cashier, onBackToSales, onPrintShiftSummary, onShiftChanged }: Props) {
  const [online, setOnline] = useState(false);
  const [shift, setShift] = useState<ShiftRecord | null>(null);
  const [currencies, setCurrencies] = useState<CurrencyConfig[]>([]);
  const [history, setHistory] = useState<PageResult>(emptyPage);
  const [historyDetail, setHistoryDetail] = useState<ShiftRecord | null>(null);
  const [opening, setOpening] = useState<Record<string, string>>({});
  const [counts, setCounts] = useState<Record<string, string>>({});
  const [movementType, setMovementType] = useState<"cash_in" | "cash_out">("cash_in");
  const [movementAmount, setMovementAmount] = useState("");
  const [movementCurrency, setMovementCurrency] = useState("");
  const [movementReason, setMovementReason] = useState("");
  const [openingNote, setOpeningNote] = useState("");
  const [closingNote, setClosingNote] = useState("");
  const [confirmClose, setConfirmClose] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const mutationInFlight = useRef(false);

  const cashCurrencies = useMemo(
    () => shift?.currencies.filter((row) => row.cash_accepted) || [],
    [shift],
  );
  const configuredCashCurrencies = useMemo(
    () => currencies.filter((row) => row.active && row.cash_accepted),
    [currencies],
  );

  const refreshHistory = useCallback(async (page = 1) => {
    const response = await api.get<PageResult>("/shifts/my-history", { params: { page, page_size: 10 } });
    setHistory(response.data);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    const isOnline = await isDeviceOnline();
    setOnline(isOnline);
    if (!isOnline) {
      setError("Shift changes require an online POS session. No shift action has been queued; reconnect to refresh authoritative shift data.");
      setLoading(false);
      return;
    }
    try {
      const [currentResult, currencyResult] = await Promise.all([
        api.get<ShiftRecord | null>("/shifts/current"),
        api.get<{ currencies: CurrencyConfig[] }>(`/currencies/${companyId}/pos-config`),
      ]);
      setShift(currentResult.data);
      setCurrencies(currencyResult.data.currencies || []);
      if (currentResult.data) {
        setCounts(Object.fromEntries(currentResult.data.currencies.filter((row) => row.cash_accepted).map((row) => [row.currency_code, ""])));
        setMovementCurrency((current) => current || currentResult.data!.currencies.find((row) => row.cash_accepted)?.currency_code || "");
      } else {
        setOpening((current) => {
          const next = { ...current };
          for (const currency of currencyResult.data.currencies || []) {
            if (currency.active && currency.cash_accepted && next[currency.code] === undefined) next[currency.code] = "0";
          }
          return next;
        });
        setMovementCurrency((current) => current || currencyResult.data.currencies.find((row) => row.active && row.cash_accepted)?.code || "");
      }
      await refreshHistory(1);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Could not load shift information. Reconnect and try again."));
    } finally {
      setLoading(false);
    }
  }, [companyId, refreshHistory]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function ensureOnline() {
    const currentOnline = await isDeviceOnline();
    setOnline(currentOnline);
    if (!currentOnline) {
      setError("Shift management is online-only. No changes were saved or queued. Reconnect and try again.");
      return false;
    }
    return true;
  }

  async function openShift() {
    if (mutationInFlight.current) return;
    mutationInFlight.current = true;
    if (!(await ensureOnline())) { mutationInFlight.current = false; return; }
    const balances = configuredCashCurrencies.map((currency) => ({
      currency_code: currency.code,
      amount: (opening[currency.code] || "0").trim(),
    }));
    if (balances.some((item) => !validAmount(item.amount, configuredCashCurrencies.find((currency) => currency.code === item.currency_code)?.decimal_places ?? 2))) {
      setError("Enter a valid non-negative opening amount for every cash currency.");
      mutationInFlight.current = false;
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await api.post<ShiftRecord>("/shifts/open", {
        opening_balances: balances,
        opening_note: openingNote.trim() || null,
        idempotency_key: idempotencyKey(),
      });
      setShift(response.data);
      onShiftChanged?.(response.data);
      setOpeningNote("");
      setNotice(`Shift ${response.data.shift_number} opened at ${new Date(response.data.opened_at).toLocaleString()}.`);
      await refreshHistory(1);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Could not open shift. An open shift may already exist for this cashier or register."));
    } finally { mutationInFlight.current = false; setBusy(false); }
  }

  async function postMovement() {
    if (mutationInFlight.current) return;
    if (!shift) return;
    mutationInFlight.current = true;
    if (!(await ensureOnline())) { mutationInFlight.current = false; return; }
    const selectedCurrency = cashCurrencies.find((currency) => currency.currency_code === movementCurrency);
    if (!movementReason.trim() || !selectedCurrency || !validAmount(movementAmount, selectedCurrency.decimal_places, true)) {
      setError("Enter a positive amount and a reason for the cash movement.");
      mutationInFlight.current = false;
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api.post(`/shifts/${shift.id}/cash-movements`, {
        movement_type: movementType, currency_code: movementCurrency,
        amount: movementAmount.trim(), reason: movementReason.trim(), idempotency_key: idempotencyKey(),
      });
      setMovementAmount(""); setMovementReason("");
      setNotice(movementType === "cash_in" ? "Cash-in recorded." : "Cash-out recorded.");
      await refresh();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Cash movement was not recorded."));
    } finally { mutationInFlight.current = false; setBusy(false); }
  }

  async function closeShift() {
    if (mutationInFlight.current) return;
    if (!shift) return;
    mutationInFlight.current = true;
    if (!(await ensureOnline())) { mutationInFlight.current = false; return; }
    if (!confirmClose) { setError("Confirm that the physical drawer count is complete before closing."); mutationInFlight.current = false; return; }
    const counted = cashCurrencies.map((currency) => ({ currency_code: currency.currency_code, amount: (counts[currency.currency_code] || "").trim() }));
    if (counted.some((item) => !validAmount(item.amount, cashCurrencies.find((currency) => currency.currency_code === item.currency_code)?.decimal_places ?? 2))) {
      setError("Enter an actual counted balance for each physical cash currency.");
      mutationInFlight.current = false;
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await api.post<ShiftRecord>(`/shifts/${shift.id}/close`, {
        counted_balances: counted, closing_note: closingNote.trim() || null,
        idempotency_key: idempotencyKey(), confirmed: true,
      });
      setShift(null);
      onShiftChanged?.(null);
      setHistoryDetail(response.data);
      setConfirmClose(false); setClosingNote("");
      setNotice(`Shift ${response.data.shift_number} closed at ${new Date(response.data.closed_at || Date.now()).toLocaleString()}.`);
      await refreshHistory(1);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Shift could not be closed. Review the counts and reconnect if needed."));
    } finally { mutationInFlight.current = false; setBusy(false); }
  }

  async function openHistoryDetails(shiftId: string) {
    if (!(await ensureOnline())) return;
    setBusy(true); setError("");
    try {
      const response = await api.get<ShiftRecord>(`/shifts/mine/${shiftId}`);
      setHistoryDetail(response.data);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Could not load shift history."));
    } finally { setBusy(false); }
  }

  const baseCurrency = shift?.summary.base_currency_code || "";

  async function printSummary(target: ShiftRecord) {
    setError(""); setNotice("");
    try {
      await onPrintShiftSummary(target);
      setNotice(`Printed shift summary ${target.shift_number}. Printing does not create a financial transaction.`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Could not print shift summary."));
    }
  }

  return <main className="pos-shift-page">
    <header className="pos-shift-header">
      <div><p className="pos-shift-eyebrow">ApexRetail POS · {online ? "Online" : "Offline"}</p><h1>Shift Management</h1><p>Open, reconcile, and review the cashier shift for this POS register.</p></div>
      <div className="pos-shift-header-actions"><button type="button" onClick={() => void refresh()} disabled={loading}>Refresh</button><button type="button" onClick={onBackToSales}>Return to Sales</button></div>
    </header>
    {!online && <div className="pos-shift-offline" role="status">Shift management is online-only. Existing offline sales remain available; shift changes are never queued.</div>}
    {error && <p className="pos-shift-error" role="alert">{error}</p>}
    {notice && <p className="pos-shift-notice" role="status">{notice}</p>}

    {loading ? <section className="pos-shift-panel"><p>Loading shift data…</p></section> : shift ? <>
      <section className="pos-shift-current">
        <div className="pos-shift-current-heading"><div><span className="pos-shift-status">OPEN SHIFT</span><h2>{shift.shift_number}</h2><p>{shift.cashier_name || cashier?.name || "Cashier"} · {shift.shop_name || "Current shop"} · {shift.branch_name || "Assigned branch"} · {shift.register_name || "Current register"}</p></div><button type="button" onClick={() => void printSummary(shift)}>Print shift summary</button></div>
        <div className="pos-shift-facts"><span>Cashier<strong>{shift.cashier_name || cashier?.name || "Cashier"}</strong></span><span>Register<strong>{shift.register_name || "Current register"}</strong></span><span>Opened<strong>{new Date(shift.opened_at).toLocaleString()}</strong></span><span>Sales this shift<strong>{formatted(shift.summary.total_sales_base || 0, { currency_code: baseCurrency || "USD", symbol: "$", decimal_places: 2 })}</strong></span></div>
        <h3>Drawer balances by physical currency</h3>
        <div className="pos-shift-currency-grid">{shift.currencies.filter((row) => row.cash_accepted).map((row) => <article key={row.currency_code}><header><strong>{row.currency_name}</strong><span>{row.currency_code}</span></header><dl><div><dt>Opening</dt><dd>{amountLabel(row.opening_float, row)}</dd></div><div><dt>Cash sales</dt><dd>{amountLabel(row.cash_sales, row)}</dd></div><div><dt>Cash in</dt><dd>{amountLabel(row.cash_in, row)}</dd></div><div><dt>Cash out</dt><dd>{amountLabel(row.cash_out, row)}</dd></div><div><dt>Cash settlements</dt><dd>{amountLabel(row.cash_settlements, row)}</dd></div><div><dt>Refunds + expenses</dt><dd>{amountLabel(Number(row.cash_refunds) + Number(row.cash_expenses), row)}</dd></div><div className="expected"><dt>Current expected cash</dt><dd>{amountLabel(row.expected_cash, row)}</dd></div></dl></article>)}</div>
      <section className="pos-shift-panel"><h3>Record cash movement</h3><div className="pos-shift-form-grid"><label>Movement<select value={movementType} onChange={(event) => setMovementType(event.target.value as "cash_in" | "cash_out")}><option value="cash_in">Cash in</option><option value="cash_out">Cash out</option></select></label><label>Currency<select value={movementCurrency} onChange={(event) => setMovementCurrency(event.target.value)}>{cashCurrencies.map((row) => <option key={row.currency_code} value={row.currency_code}>{row.currency_code} — {row.currency_name}</option>)}</select></label><label>Amount<input inputMode="decimal" value={movementAmount} onChange={(event) => setMovementAmount(event.target.value)} placeholder="0.00" /></label><label>Reason<input value={movementReason} onChange={(event) => setMovementReason(event.target.value)} maxLength={500} placeholder="Required reason" /></label><button type="button" onClick={() => void postMovement()} disabled={busy || !online}>{busy ? "Saving…" : "Record movement"}</button></div>
        {shift.cash_movements?.length ? <div className="pos-shift-movements"><h4>Cash movement history</h4>{shift.cash_movements.slice(0, 10).map((row) => { const currency = shift.currencies.find((item) => item.currency_code === row.currency_code)!; return <article key={row.id}><span><strong>{row.movement_type === "cash_in" ? "Cash in" : "Cash out"} · {row.reason}</strong><small>{row.actor_name || shift.cashier_name || "Cashier"} · {new Date(row.created_at).toLocaleString()}</small></span><b>{amountLabel(row.amount, currency)}</b></article>; })}</div> : null}</section>
      <section className="pos-shift-panel pos-shift-close-panel"><h3>Close shift</h3><p>Count each enabled cash currency separately. Closing is final for this shift.</p><div className="pos-shift-count-grid">{cashCurrencies.map((row) => <label key={row.currency_code}>Counted {row.currency_code}<input inputMode="decimal" value={counts[row.currency_code] || ""} onChange={(event) => setCounts((current) => ({ ...current, [row.currency_code]: event.target.value }))} placeholder={`Expected ${amountLabel(row.expected_cash, row)}`} /></label>)}</div><label className="pos-shift-note">Closing note (optional)<textarea value={closingNote} onChange={(event) => setClosingNote(event.target.value)} maxLength={1000} /></label><label className="pos-shift-confirm"><input type="checkbox" checked={confirmClose} onChange={(event) => setConfirmClose(event.target.checked)} />I have physically counted the cash drawer and reviewed the expected balances.</label><button className="danger" type="button" onClick={() => void closeShift()} disabled={busy || !online || !confirmClose}>{busy ? "Closing…" : "Confirm and close shift"}</button></section>
      </section>
    </> : <section className="pos-shift-panel pos-shift-open-panel"><h2>Open a shift</h2><p>Cashier, shop, register, and opening time come from the authenticated POS session. Opening balances may be zero and are recorded per cash currency.</p><div className="pos-shift-session-facts"><span>Cashier<strong>{cashier?.name || "Current cashier"}</strong></span><span>Branch<strong>{branchId || "Assigned branch"}</strong></span><span>Register<strong>Derived from POS session</strong></span></div><div className="pos-shift-count-grid">{configuredCashCurrencies.map((currency) => <label key={currency.code}>Opening {currency.code}<input inputMode="decimal" value={opening[currency.code] ?? "0"} onChange={(event) => setOpening((current) => ({ ...current, [currency.code]: event.target.value }))} placeholder="0" /></label>)}{configuredCashCurrencies.length === 0 && <p>No active cash currencies are configured for this company.</p>}</div><label className="pos-shift-note">Opening note (optional)<textarea value={openingNote} onChange={(event) => setOpeningNote(event.target.value)} maxLength={1000} /></label><button type="button" onClick={() => void openShift()} disabled={busy || !online || configuredCashCurrencies.length === 0}>{busy ? "Opening…" : "Open shift"}</button></section>}

    <section className="pos-shift-panel"><div className="pos-shift-history-heading"><div><h2>Recent shifts for this cashier and register</h2><p>{history.total} matching shifts</p></div><div><button type="button" onClick={() => void refreshHistory(Math.max(1, history.page - 1))} disabled={history.page <= 1 || busy}>Previous</button><span>Page {history.page} of {Math.max(1, history.total_pages)}</span><button type="button" onClick={() => void refreshHistory(history.page + 1)} disabled={history.page >= history.total_pages || busy}>Next</button></div></div>{history.items.length ? <div className="pos-shift-history">{history.items.map((row) => <article key={row.id}><div><strong>{row.shift_number}</strong><small>{new Date(row.opened_at).toLocaleString()} · {row.status.toUpperCase()} · {row.register_name || "Register"}</small></div><div className="pos-shift-history-currencies">{row.currencies.filter((currency) => currency.cash_accepted).map((currency) => <span key={currency.currency_code}>{currency.currency_code}: {amountLabel(currency.counted_cash ?? currency.expected_cash, currency)}{currency.variance !== null ? ` · Δ ${amountLabel(currency.variance, currency)}` : " · open"}</span>)}</div><button type="button" onClick={() => void openHistoryDetails(row.id)} disabled={busy}>Details</button></article>)}</div> : <p>No previous shifts for this cashier and register.</p>}</section>

    {historyDetail && <div className="pos-shift-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setHistoryDetail(null); }}><section className="pos-shift-modal" role="dialog" aria-modal="true" aria-labelledby="pos-shift-history-title"><header><div><h2 id="pos-shift-history-title">{historyDetail.shift_number}</h2><p>{historyDetail.cashier_name} · {historyDetail.register_name}</p></div><button type="button" onClick={() => setHistoryDetail(null)}>Close</button></header><p>{historyDetail.status.toUpperCase()} · Opened {new Date(historyDetail.opened_at).toLocaleString()} · Closed {historyDetail.closed_at ? new Date(historyDetail.closed_at).toLocaleString() : "—"}</p><div className="pos-shift-currency-grid">{historyDetail.currencies.filter((row) => row.cash_accepted).map((row) => <article key={row.currency_code}><strong>{row.currency_code}</strong><p>Opening: {amountLabel(row.opening_float, row)}</p><p>Cash sales: {amountLabel(row.cash_sales, row)}</p><p>Cash in/out: {amountLabel(row.cash_in, row)} / {amountLabel(row.cash_out, row)}</p><p>Expected: {amountLabel(row.expected_cash, row)}</p><p>Counted: {row.counted_cash === null ? "Not counted" : amountLabel(row.counted_cash, row)}</p><p>Variance: {row.variance === null ? "Open" : amountLabel(row.variance, row)}</p></article>)}</div>{historyDetail.cash_movements?.length ? <div className="pos-shift-movements"><h3>Cash movements</h3>{historyDetail.cash_movements.map((row) => { const currency = historyDetail.currencies.find((item) => item.currency_code === row.currency_code)!; return <article key={row.id}><span>{row.movement_type === "cash_in" ? "Cash in" : "Cash out"}: {row.reason}<small>{row.actor_name || "Cashier"} · {new Date(row.created_at).toLocaleString()}</small></span><b>{amountLabel(row.amount, currency)}</b></article>; })}</div> : null}<button type="button" onClick={() => void printSummary(historyDetail)}>Print shift summary</button></section></div>}
  </main>;
}
