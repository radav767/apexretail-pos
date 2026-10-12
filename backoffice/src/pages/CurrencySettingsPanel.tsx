import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import Pagination from "../components/Pagination";
import type { PageMeta } from "../components/pagination";
import { multiplyDecimalStrings, positiveRateError } from "./currencyLogic";
import "./currencies.css";

type Currency = {
  id: string;
  company_id: string;
  code: string;
  display_name: string;
  symbol: string;
  decimal_places: number;
  active: boolean;
  is_base: boolean;
  cash_accepted: boolean;
  card_accepted: boolean;
  mobile_accepted: boolean;
  display_order: number;
  current_rate: string | null;
  current_rate_id: string | null;
  rate_effective_at: string | null;
  previous_rate: string | null;
  previous_rate_effective_at: string | null;
};

type Rate = {
  id: string;
  currency_id: string;
  currency_code: string;
  base_currency_code: string;
  foreign_units_per_base: string;
  effective_at: string;
  actor_id: string | null;
  actor_name: string;
  created_at: string;
  note: string | null;
};

type CurrencyForm = {
  code: string;
  displayName: string;
  symbol: string;
  decimalPlaces: string;
  active: boolean;
  cash: boolean;
  card: boolean;
  mobile: boolean;
  order: string;
};

const emptyForm: CurrencyForm = {
  code: "",
  displayName: "",
  symbol: "",
  decimalPlaces: "2",
  active: true,
  cash: true,
  card: true,
  mobile: true,
  order: "0",
};

const emptyPage: PageMeta = { page: 1, page_size: 25, total: 0, total_pages: 0 };

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "Not yet effective";
}

function apiMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((row) => row.msg).join("; ");
  return detail || fallback;
}

export default function CurrencySettingsPanel({ companyId }: { companyId: string }) {
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [rates, setRates] = useState<Rate[]>([]);
  const [ratePage, setRatePage] = useState<PageMeta>(emptyPage);
  const [multiCurrencyEnabled, setMultiCurrencyEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<CurrencyForm>(emptyForm);
  const [rateCurrencyId, setRateCurrencyId] = useState("");
  const [rate, setRate] = useState("");
  const [rateEffectiveAt, setRateEffectiveAt] = useState("");
  const [rateNote, setRateNote] = useState("");

  const load = useCallback(async (page = 1) => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const [currencyResponse, historyResponse, settingsResponse] = await Promise.all([
        api.get<Currency[]>(`/currencies/${companyId}`),
        api.get(`/currencies/${companyId}/rates/history`, { params: { page, page_size: 25 } }),
        api.get(`/settings/${companyId}`),
      ]);
      setCurrencies(currencyResponse.data);
      setRates(historyResponse.data.items);
      setRatePage({
        page: historyResponse.data.page,
        page_size: historyResponse.data.page_size,
        total: historyResponse.data.total,
        total_pages: historyResponse.data.total_pages,
      });
      setMultiCurrencyEnabled(Boolean(settingsResponse.data.multi_currency_enabled));
      const firstForeign = currencyResponse.data.find((row) => !row.is_base && row.active);
      setRateCurrencyId((current) => current || firstForeign?.id || "");
    } catch (requestError: any) {
      setError(apiMessage(requestError, "Failed to load currency settings."));
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { void load(); }, [load]);

  const base = currencies.find((row) => row.is_base);
  const selectedRateCurrency = currencies.find((row) => row.id === rateCurrencyId);
  const previewError = rate ? positiveRateError(rate) : null;
  const preview = !previewError && rate && selectedRateCurrency
    ? multiplyDecimalStrings("10", rate, selectedRateCurrency.decimal_places)
    : "—";

  const sortedCurrencies = useMemo(
    () => [...currencies].sort((a, b) => a.display_order - b.display_order || a.code.localeCompare(b.code)),
    [currencies],
  );

  function startAdd() {
    setEditingId(null);
    setForm(emptyForm);
    setFormOpen(true);
    setError("");
    setMessage("");
  }

  function startEdit(currency: Currency) {
    setEditingId(currency.id);
    setForm({
      code: currency.code,
      displayName: currency.display_name,
      symbol: currency.symbol,
      decimalPlaces: String(currency.decimal_places),
      active: currency.active,
      cash: currency.cash_accepted,
      card: currency.card_accepted,
      mobile: currency.mobile_accepted,
      order: String(currency.display_order),
    });
    setFormOpen(true);
    setError("");
    setMessage("");
  }

  async function saveCurrency() {
    const code = form.code.trim().toUpperCase();
    if (!code || !form.displayName.trim() || !form.symbol.trim()) {
      setError("Currency code, display name and symbol are required.");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    const values = {
      display_name: form.displayName.trim(),
      symbol: form.symbol.trim(),
      decimal_places: Number(form.decimalPlaces),
      active: form.active,
      cash_accepted: form.cash,
      card_accepted: form.card,
      mobile_accepted: form.mobile,
      display_order: Number(form.order || 0),
    };
    try {
      if (editingId) {
        await api.patch(`/currencies/${companyId}/${editingId}`, values);
      } else {
        await api.post("/currencies", { company_id: companyId, code, is_base: false, ...values });
      }
      setFormOpen(false);
      setMessage(editingId ? "Currency settings updated." : "Accepted currency added.");
      await load(ratePage.page);
    } catch (requestError: any) {
      setError(apiMessage(requestError, "Failed to save currency."));
    } finally {
      setSaving(false);
    }
  }

  async function chooseBase(currency: Currency) {
    if (!window.confirm(`Make ${currency.code} the company base currency? This is blocked after financial activity or rate history exists.`)) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await api.post(`/currencies/${companyId}/${currency.id}/set-base`);
      setMessage(`${currency.code} is now the company base currency.`);
      await load(1);
    } catch (requestError: any) {
      setError(apiMessage(requestError, "Base currency could not be changed."));
    } finally {
      setSaving(false);
    }
  }

  async function toggleMultiCurrency() {
    setSaving(true);
    setError("");
    try {
      await api.patch(`/currencies/configuration/${companyId}`, { enabled: !multiCurrencyEnabled });
      setMultiCurrencyEnabled((value) => !value);
      setMessage(`Multi-currency payments ${multiCurrencyEnabled ? "disabled" : "enabled"}.`);
    } catch (requestError: any) {
      setError(apiMessage(requestError, "Multi-currency setting could not be changed."));
    } finally {
      setSaving(false);
    }
  }

  async function createRate() {
    const validation = positiveRateError(rate);
    if (!rateCurrencyId) { setError("Choose a foreign currency."); return; }
    if (validation) { setError(validation); return; }
    if (!rateEffectiveAt) { setError("Choose when the exchange rate becomes effective."); return; }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await api.post("/currencies/rates", {
        company_id: companyId,
        currency_id: rateCurrencyId,
        foreign_units_per_base: rate.trim(),
        effective_at: new Date(rateEffectiveAt).toISOString(),
        note: rateNote.trim() || null,
      });
      setRate("");
      setRateNote("");
      setMessage("New immutable exchange-rate entry added.");
      await load(1);
    } catch (requestError: any) {
      setError(apiMessage(requestError, "Exchange rate could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  if (loading && !currencies.length) return <section className="currency-loading">Loading currencies…</section>;

  return <div className="currency-settings">
    {error && <div className="currency-alert currency-alert-error">{error}</div>}
    {message && <div className="currency-alert currency-alert-success">{message}</div>}

    <section className="currency-base-card">
      <div><span className="currency-eyebrow">Company base currency</span><h3>{base ? `${base.code} · ${base.display_name}` : "Not configured"}</h3><p>The base rate is always 1. Historical transactions are never converted when settings change.</p></div>
      <div className="currency-base-actions"><strong>{base?.symbol || ""} 1 {base?.code || ""}</strong><button type="button" onClick={() => void toggleMultiCurrency()} disabled={saving}>{multiCurrencyEnabled ? "Disable multi-currency" : "Enable multi-currency"}</button></div>
    </section>

    <aside className="currency-policy-note"><strong>Protected accounting setting</strong><span>Changing the base currency is allowed only before financial activity, cashier shifts, or exchange-rate history exists. No historical records are rewritten.</span></aside>

    <section className="currency-panel">
      <div className="currency-panel-heading"><div><h3>Accepted currencies</h3><p>Codes are company-scoped and normalized to uppercase. Deactivate currencies instead of deleting financial history.</p></div><button type="button" onClick={startAdd}>Add currency</button></div>
      <div className="currency-table-wrap"><table className="currency-table"><thead><tr><th>Currency</th><th>Rate</th><th>Status</th><th>Accepted methods</th><th>Precision</th><th>Order</th><th>Actions</th></tr></thead><tbody>{sortedCurrencies.map((currency) => <tr key={currency.id}>
        <td data-label="Currency"><strong>{currency.code} · {currency.symbol}</strong><small>{currency.display_name}{currency.is_base ? " · Base" : ""}</small></td>
        <td data-label="Rate"><strong>{currency.is_base ? "1" : currency.current_rate || "No current rate"}</strong><small>{currency.is_base ? "Logical base rate" : `Previous: ${currency.previous_rate || "—"}`}<br />{dateTime(currency.rate_effective_at)}</small></td>
        <td data-label="Status"><span className={`currency-status ${currency.active ? "active" : "inactive"}`}>{currency.active ? "Active" : "Inactive"}</span></td>
        <td data-label="Accepted methods"><span className="currency-methods">{currency.cash_accepted && <em>Cash</em>}{currency.card_accepted && <em>Card</em>}{currency.mobile_accepted && <em>Mobile</em>}{!currency.cash_accepted && !currency.card_accepted && !currency.mobile_accepted && <small>None</small>}</span></td>
        <td data-label="Precision">{currency.decimal_places} decimals</td><td data-label="Order">{currency.display_order}</td>
        <td data-label="Actions"><div className="currency-row-actions"><button type="button" onClick={() => startEdit(currency)}>Edit</button>{!currency.is_base && <button type="button" onClick={() => void chooseBase(currency)} disabled={saving || !currency.active}>Make base</button>}</div></td>
      </tr>)}</tbody></table></div>
    </section>

    {formOpen && <section className="currency-panel currency-form-panel"><div className="currency-panel-heading"><div><h3>{editingId ? "Edit accepted currency" : "Add accepted currency"}</h3><p>Currency codes cannot be changed after creation; deactivate an obsolete currency instead.</p></div></div><div className="currency-form-grid">
      <label>Currency code<input value={form.code} disabled={Boolean(editingId)} maxLength={8} onChange={(event) => setForm((value) => ({ ...value, code: event.target.value.toUpperCase() }))} placeholder="EUR" /></label>
      <label>Display name<input value={form.displayName} onChange={(event) => setForm((value) => ({ ...value, displayName: event.target.value }))} placeholder="Euro" /></label>
      <label>Symbol<input value={form.symbol} maxLength={10} onChange={(event) => setForm((value) => ({ ...value, symbol: event.target.value }))} placeholder="€" /></label>
      <label>Decimal places<select value={form.decimalPlaces} onChange={(event) => setForm((value) => ({ ...value, decimalPlaces: event.target.value }))}>{[0,1,2,3,4].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Display priority<input type="number" step="1" value={form.order} onChange={(event) => setForm((value) => ({ ...value, order: event.target.value }))} /></label>
      <label className="currency-check"><input type="checkbox" checked={form.active} disabled={currencies.find((row) => row.id === editingId)?.is_base} onChange={(event) => setForm((value) => ({ ...value, active: event.target.checked }))} />Active</label>
      <label className="currency-check"><input type="checkbox" checked={form.cash} onChange={(event) => setForm((value) => ({ ...value, cash: event.target.checked }))} />Accepted for Cash</label>
      <label className="currency-check"><input type="checkbox" checked={form.card} onChange={(event) => setForm((value) => ({ ...value, card: event.target.checked }))} />Accepted for Card</label>
      <label className="currency-check"><input type="checkbox" checked={form.mobile} onChange={(event) => setForm((value) => ({ ...value, mobile: event.target.checked }))} />Accepted for Mobile</label>
    </div><div className="currency-form-actions"><button type="button" className="secondary" onClick={() => setFormOpen(false)}>Cancel</button><button type="button" onClick={() => void saveCurrency()} disabled={saving}>{saving ? "Saving…" : "Save currency"}</button></div></section>}

    <section className="currency-panel currency-rate-panel"><div className="currency-panel-heading"><div><h3>Add exchange rate</h3><p>Foreign currency units per 1 base currency. Saving creates a new immutable history entry.</p></div></div><div className="currency-rate-grid">
      <label>Foreign currency<select value={rateCurrencyId} onChange={(event) => setRateCurrencyId(event.target.value)}><option value="">Choose currency</option>{currencies.filter((row) => !row.is_base && row.active).map((row) => <option key={row.id} value={row.id}>{row.code} · {row.display_name}</option>)}</select></label>
      <label>Rate<input inputMode="decimal" value={rate} onChange={(event) => setRate(event.target.value)} placeholder="18.50" /></label>
      <label>Effective date and time<input type="datetime-local" value={rateEffectiveAt} onChange={(event) => setRateEffectiveAt(event.target.value)} /></label>
      <label>Note<input value={rateNote} onChange={(event) => setRateNote(event.target.value)} placeholder="Optional rate source or note" /></label>
    </div><div className="currency-preview" aria-live="polite"><strong>Conversion preview</strong><span>1 {base?.code || "BASE"} = {rate || "—"} {selectedRateCurrency?.code || "FOREIGN"}</span><span>10 {base?.code || "BASE"} = {preview} {selectedRateCurrency?.code || "FOREIGN"}</span>{previewError && <small>{previewError}</small>}</div><div className="currency-form-actions"><button type="button" onClick={() => void createRate()} disabled={saving}>{saving ? "Saving…" : "Add rate"}</button></div></section>

    <section className="currency-panel"><div className="currency-panel-heading"><div><h3>Immutable rate history</h3><p>Newest effective rate first. Actor names fall back safely to their audit identifier.</p></div><strong>{ratePage.total} records</strong></div><div className="currency-table-wrap"><table className="currency-table rate-history-table"><thead><tr><th>Currency pair</th><th>Rate</th><th>Effective</th><th>Changed by</th><th>Created</th></tr></thead><tbody>{!rates.length && <tr><td colSpan={5}>No exchange-rate history yet.</td></tr>}{rates.map((row) => <tr key={row.id}><td data-label="Currency pair">{row.base_currency_code} → {row.currency_code}</td><td data-label="Rate"><strong>{row.foreign_units_per_base}</strong></td><td data-label="Effective">{dateTime(row.effective_at)}</td><td data-label="Changed by">{row.actor_name || row.actor_id || "Unknown"}</td><td data-label="Created">{dateTime(row.created_at)}</td></tr>)}</tbody></table></div><Pagination meta={ratePage} onPage={(page) => void load(page)} /></section>
  </div>;
}
