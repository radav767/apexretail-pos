import { useEffect, useState } from "react";
import { api } from "../api/client";
import "./settings.css";

type SettingsData = {
  company_id: string;
  name: string;
  owner_name: string | null;
  owner_email: string;
  business_type: string;
  country: string | null;
  phone: string | null;
  address: string | null;
  contact_email: string | null;
  currency_code: string;
  currency_symbol: string;
  decimal_places: number;
  tax_name: string;
  tax_rate: string | number;
  tax_inclusive: boolean;
  receipt_header: string | null;
  receipt_footer: string | null;
  paper_size: string;
  auto_print: boolean;
  payment_methods: string[];
};

type SettingsForm = {
  name: string;
  owner_name: string;
  owner_email: string;
  business_type: string;
  country: string;
  phone: string;
  address: string;
  contact_email: string;
  currency_code: string;
  currency_symbol: string;
  decimal_places: string;
  tax_name: string;
  tax_rate: string;
  tax_inclusive: boolean;
  receipt_header: string;
  receipt_footer: string;
  paper_size: string;
  auto_print: boolean;
  payment_methods: string[];
};

const defaultForm: SettingsForm = {
  name: "",
  owner_name: "",
  owner_email: "",
  business_type: "Retail",
  country: "",
  phone: "",
  address: "",
  contact_email: "",
  currency_code: "USD",
  currency_symbol: "$",
  decimal_places: "2",
  tax_name: "VAT",
  tax_rate: "0",
  tax_inclusive: false,
  receipt_header: "",
  receipt_footer: "",
  paper_size: "80mm",
  auto_print: false,
  payment_methods: ["cash", "card", "mobile", "credit"],
};

const availablePaymentMethods = [
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "mobile", label: "Mobile Money" },
  { value: "credit", label: "Credit" },
  { value: "cheque", label: "Cheque" },
  { value: "split", label: "Split Payment" },
];

export default function SettingsPage({
  companyId,
  onDataChanged,
}: {
  companyId: string;
  onDataChanged?: () => void;
}) {
  const [form, setForm] = useState<SettingsForm>(defaultForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadSettings() {
    try {
      setLoading(true);
      setError("");

      const response = await api.get<SettingsData>(
        `/settings/${companyId}`,
      );

      const data = response.data;

      setForm({
        name: data.name || "",
        owner_name: data.owner_name || "",
        owner_email: data.owner_email || "",
        business_type: data.business_type || "Retail",
        country: data.country || "",
        phone: data.phone || "",
        address: data.address || "",
        contact_email: data.contact_email || "",
        currency_code: data.currency_code || "USD",
        currency_symbol: data.currency_symbol || "$",
        decimal_places: String(data.decimal_places ?? 2),
        tax_name: data.tax_name || "VAT",
        tax_rate: String(data.tax_rate ?? 0),
        tax_inclusive: Boolean(data.tax_inclusive),
        receipt_header: data.receipt_header || "",
        receipt_footer: data.receipt_footer || "",
        paper_size: data.paper_size || "80mm",
        auto_print: Boolean(data.auto_print),
        payment_methods:
          data.payment_methods?.length > 0
            ? data.payment_methods
            : ["cash"],
      });
    } catch (requestError: any) {
      setError(
        requestError.response?.data?.detail ||
          "Failed to load business settings",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSettings();
  }, [companyId]);

  function updateField<K extends keyof SettingsForm>(
    field: K,
    value: SettingsForm[K],
  ) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function togglePaymentMethod(method: string) {
    setForm((current) => {
      const enabled = current.payment_methods.includes(method);

      return {
        ...current,
        payment_methods: enabled
          ? current.payment_methods.filter(
              (existingMethod) => existingMethod !== method,
            )
          : [...current.payment_methods, method],
      };
    });
  }

  async function saveSettings() {
    if (!form.name.trim()) {
      setError("Business name is required");
      return;
    }

    if (!form.business_type.trim()) {
      setError("Business type is required");
      return;
    }

    if (form.payment_methods.length === 0) {
      setError("Select at least one payment method");
      return;
    }

    try {
      setSaving(true);
      setError("");
      setMessage("");

      await api.patch(`/settings/${companyId}`, {
        name: form.name.trim(),
        owner_name: form.owner_name.trim() || null,
        business_type: form.business_type.trim(),
        country: form.country.trim() || null,
        phone: form.phone.trim() || null,
        address: form.address.trim() || null,
        contact_email: form.contact_email.trim() || null,
        currency_code: form.currency_code.trim().toUpperCase(),
        currency_symbol: form.currency_symbol.trim(),
        decimal_places: Number(form.decimal_places),
        tax_name: form.tax_name.trim(),
        tax_rate: Number(form.tax_rate),
        tax_inclusive: form.tax_inclusive,
        receipt_header: form.receipt_header.trim() || null,
        receipt_footer: form.receipt_footer.trim() || null,
        paper_size: form.paper_size,
        auto_print: form.auto_print,
        payment_methods: form.payment_methods,
      });

      setMessage("Business settings saved successfully");
      await loadSettings();
      onDataChanged?.();
    } catch (requestError: any) {
      setError(
        requestError.response?.data?.detail ||
          "Failed to save business settings",
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <section className="settings-loading">
        Loading business settings...
      </section>
    );
  }

  return (
    <div className="settings-page">
      <div className="settings-intro">
        <div>
          <h2>Business Settings</h2>
          <p>
            Configure business information, currency, taxes, receipts,
            payment methods and printing.
          </p>
        </div>

        <button
          className="settings-save-button"
          onClick={() => void saveSettings()}
          disabled={saving}
        >
          {saving ? "Saving..." : "Save Settings"}
        </button>
      </div>

      {error && <div className="settings-alert error">{error}</div>}
      {message && (
        <div className="settings-alert success">{message}</div>
      )}

      <section className="settings-card">
        <div className="settings-card-heading">
          <h3>Business Information</h3>
          <p>Information displayed in the Backoffice and receipts.</p>
        </div>

        <div className="settings-grid">
          <label>
            Business name
            <input
              value={form.name}
              onChange={(event) =>
                updateField("name", event.target.value)
              }
            />
          </label>

          <label>
            Owner name
            <input
              value={form.owner_name}
              onChange={(event) =>
                updateField("owner_name", event.target.value)
              }
            />
          </label>

          <label>
            Owner account email
            <input value={form.owner_email} disabled />
          </label>

          <label>
            Contact email
            <input
              type="email"
              value={form.contact_email}
              onChange={(event) =>
                updateField("contact_email", event.target.value)
              }
            />
          </label>

          <label>
            Business type
            <input
              value={form.business_type}
              onChange={(event) =>
                updateField("business_type", event.target.value)
              }
            />
          </label>

          <label>
            Country
            <input
              value={form.country}
              onChange={(event) =>
                updateField("country", event.target.value)
              }
            />
          </label>

          <label>
            Phone
            <input
              value={form.phone}
              onChange={(event) =>
                updateField("phone", event.target.value)
              }
            />
          </label>

          <label className="settings-wide-field">
            Business address
            <textarea
              rows={3}
              value={form.address}
              onChange={(event) =>
                updateField("address", event.target.value)
              }
            />
          </label>
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-heading">
          <h3>Currency and Tax</h3>
          <p>Control how totals, prices and taxes are calculated.</p>
        </div>

        <div className="settings-grid">
          <label>
            Currency code
            <input
              maxLength={10}
              value={form.currency_code}
              onChange={(event) =>
                updateField(
                  "currency_code",
                  event.target.value.toUpperCase(),
                )
              }
            />
          </label>

          <label>
            Currency symbol
            <input
              maxLength={10}
              value={form.currency_symbol}
              onChange={(event) =>
                updateField("currency_symbol", event.target.value)
              }
            />
          </label>

          <label>
            Decimal places
            <select
              value={form.decimal_places}
              onChange={(event) =>
                updateField("decimal_places", event.target.value)
              }
            >
              <option value="0">0</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
              <option value="4">4</option>
            </select>
          </label>

          <label>
            Tax name
            <input
              value={form.tax_name}
              onChange={(event) =>
                updateField("tax_name", event.target.value)
              }
            />
          </label>

          <label>
            Tax rate (%)
            <input
              type="number"
              min="0"
              max="100"
              step="0.001"
              value={form.tax_rate}
              onChange={(event) =>
                updateField("tax_rate", event.target.value)
              }
            />
          </label>

          <label className="settings-checkbox-row">
            <input
              type="checkbox"
              checked={form.tax_inclusive}
              onChange={(event) =>
                updateField("tax_inclusive", event.target.checked)
              }
            />
            Prices already include tax
          </label>
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-heading">
          <h3>Payment Methods</h3>
          <p>Select payment options available on the POS.</p>
        </div>

        <div className="payment-method-grid">
          {availablePaymentMethods.map((method) => (
            <label
              className="payment-method-option"
              key={method.value}
            >
              <input
                type="checkbox"
                checked={form.payment_methods.includes(method.value)}
                onChange={() => togglePaymentMethod(method.value)}
              />
              <span>{method.label}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-heading">
          <h3>Receipt Design</h3>
          <p>Customize information printed on customer receipts.</p>
        </div>

        <div className="settings-grid">
          <label className="settings-wide-field">
            Receipt header
            <textarea
              rows={4}
              placeholder="Thank you for shopping with us"
              value={form.receipt_header}
              onChange={(event) =>
                updateField("receipt_header", event.target.value)
              }
            />
          </label>

          <label className="settings-wide-field">
            Receipt footer
            <textarea
              rows={4}
              placeholder="Goods sold are subject to store policy"
              value={form.receipt_footer}
              onChange={(event) =>
                updateField("receipt_footer", event.target.value)
              }
            />
          </label>
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-heading">
          <h3>Printer Settings</h3>
          <p>Configure thermal receipt printing preferences.</p>
        </div>

        <div className="settings-grid">
          <label>
            Receipt paper size
            <select
              value={form.paper_size}
              onChange={(event) =>
                updateField("paper_size", event.target.value)
              }
            >
              <option value="58mm">58mm thermal printer</option>
              <option value="80mm">80mm thermal printer</option>
            </select>
          </label>

          <label className="settings-checkbox-row">
            <input
              type="checkbox"
              checked={form.auto_print}
              onChange={(event) =>
                updateField("auto_print", event.target.checked)
              }
            />
            Automatically print after payment
          </label>
        </div>
      </section>

      <div className="settings-footer-actions">
        <button
          className="settings-secondary-button"
          onClick={() => void loadSettings()}
          disabled={saving}
        >
          Reset Changes
        </button>

        <button
          className="settings-save-button"
          onClick={() => void saveSettings()}
          disabled={saving}
        >
          {saving ? "Saving..." : "Save Settings"}
        </button>
      </div>
    </div>
  );
}
