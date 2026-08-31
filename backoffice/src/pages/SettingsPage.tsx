import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import ShopsDevicesPage from "./ShopsDevicesPage";
import "./settings.css";

type SettingsSection =
  | "home"
  | "company"
  | "shops"
  | "receipts"
  | "subscription"
  | "devices";

type AggregateSettings = {
  company_id: string;
  name: string;
  owner_name: string | null;
  owner_email: string;
  business_type: string;
  country: string | null;
  phone: string | null;
  contact_email: string | null;
  currency_code: string;
  currency_symbol: string;
  decimal_places: number;
};

type ReceiptSettings = {
  company_id: string;
  receipt_header: string | null;
  receipt_footer: string | null;
  paper_size: string;
  auto_print: boolean;
  tax_name: string;
  tax_rate: string | number;
  tax_inclusive: boolean;
  payment_methods: string[];
};

type ShopSettings = {
  id: string;
  company_id: string;
  name: string;
  address_line_1: string | null;
  address_line_2: string | null;
  city: string | null;
  state_province: string | null;
  country: string | null;
  phone: string | null;
  tax_vat_number: string | null;
  active: boolean;
};

type CompanyForm = {
  name: string;
  owner_name: string;
  owner_email: string;
  business_type: string;
  country: string;
  phone: string;
  contact_email: string;
  currency_code: string;
  currency_symbol: string;
  decimal_places: string;
};

type ReceiptForm = {
  receipt_header: string;
  receipt_footer: string;
  paper_size: string;
  auto_print: boolean;
  tax_name: string;
  tax_rate: string;
  tax_inclusive: boolean;
  payment_methods: string[];
};

type ShopFormMap = Record<
  string,
  {
    name: string;
    address_line_1: string;
    address_line_2: string;
    city: string;
    state_province: string;
    country: string;
    phone: string;
    tax_vat_number: string;
  }
>;

type SubscriptionHistoryRow = {
  id: string;
  action: string;
  plan: string | null;
  status: string;
  provider: string | null;
  provider_reference: string | null;
  note: string | null;
  created_at: string;
};

type SubscriptionPageData = {
  current: {
    company_id: string;
    plan: string | null;
    status: string;
    display_status: string;
    display_status_label: string;
    plan_label: string;
    trial_started_at: string | null;
    trial_ends_at: string | null;
    trial_days_remaining: number | null;
    current_period_started_at: string | null;
    current_period_ends_at: string | null;
    grace_ends_at: string | null;
    subscription_started_at: string | null;
    renewal_or_expiry_at: string | null;
    provider: string | null;
    provider_reference: string | null;
    status_reason: string | null;
    snapshot: {
      status: string;
      display_status: string;
      display_status_label: string;
      writes_allowed: boolean;
      message: string | null;
    };
  };
  usage: {
    active_terminals: number;
    billable_terminals: number;
    licensed_terminal_allowance: number | null;
    available_terminal_slots: number | null;
    allowance_enforced: boolean;
  };
  billing_preview: {
    billing_period: string | null;
    currency: string;
    unit_price: string;
    terminal_count: number;
    total_amount: string;
    included_device_ids: string[];
  };
  billing_options: Array<{
    billing_period: string;
    currency: string;
    unit_price: string;
    terminal_count: number;
    total_amount: string;
  }>;
  latest_checkout: {
    id: string;
    session_reference: string;
    provider: string;
    status: string;
    billing_period: string | null;
    billing_currency: string | null;
    unit_price: string | null;
    terminal_count: number | null;
    total_amount: string | null;
    paynow_reference: string | null;
    checkout_url: string | null;
    poll_url: string | null;
    payment_status: string | null;
    expires_at: string | null;
    created_at: string;
    updated_at: string;
  } | null;
  history: SubscriptionHistoryRow[];
  activation_available: boolean;
  activation_message: string | null;
  provider_name: string | null;
  checkout_configured: boolean;
  webhook_configured: boolean;
  payment_configuration_required: string[];
  available_plans: string[];
};

const availablePaymentMethods = [
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "mobile", label: "Mobile Money" },
  { value: "credit", label: "Credit" },
  { value: "cheque", label: "Cheque" },
  { value: "split", label: "Split Payment" },
];

function requestErrorMessage(error: any, fallback: string) {
  return (
    error?.response?.data?.detail ||
    error?.message ||
    fallback
  );
}

function formatSubscriptionDate(value: string | null) {
  if (!value) {
    return "—";
  }

  return new Date(value).toLocaleString();
}

function formatUsd(value: string | number | null | undefined) {
  return `$${Number(value || 0).toFixed(2)}`;
}

export default function SettingsPage({
  companyId,
  onDataChanged,
}: {
  companyId: string;
  onDataChanged?: () => void;
}) {
  const [section, setSection] =
    useState<SettingsSection>("home");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [companyForm, setCompanyForm] =
    useState<CompanyForm>({
      name: "",
      owner_name: "",
      owner_email: "",
      business_type: "",
      country: "",
      phone: "",
      contact_email: "",
      currency_code: "USD",
      currency_symbol: "$",
      decimal_places: "2",
    });
  const [receiptForm, setReceiptForm] =
    useState<ReceiptForm>({
      receipt_header: "",
      receipt_footer: "",
      paper_size: "80mm",
      auto_print: false,
      tax_name: "VAT",
      tax_rate: "0",
      tax_inclusive: false,
      payment_methods: ["cash"],
    });
  const [shops, setShops] = useState<ShopSettings[]>([]);
  const [shopForms, setShopForms] = useState<ShopFormMap>({});
  const [savingShopId, setSavingShopId] = useState("");
  const [subscription, setSubscription] =
    useState<SubscriptionPageData | null>(null);
  const [subscriptionPlan, setSubscriptionPlan] =
    useState("monthly");
  const [shopsLoaded, setShopsLoaded] = useState(false);

  const summaryCards = useMemo(
    () => [
      {
        id: "company" as const,
        title: "Company",
        description:
          "Business identity, contact details and single-currency formatting.",
      },
      {
        id: "shops" as const,
        title: "Shops",
        description:
          "Per-shop address, phone and tax/VAT details for receipts.",
      },
      {
        id: "receipts" as const,
        title: "Receipts",
        description:
          "Tax label, footer, paper size, printing and payment methods.",
      },
      {
        id: "subscription" as const,
        title: "Subscription",
        description:
          "Trial status, renewals and subscription history.",
      },
      {
        id: "devices" as const,
        title: "Devices/POS",
        description:
          "Provision POS records, assign branches and control access.",
        hidden: true,
      },
    ].filter((card) => !card.hidden),
    [],
  );

  async function loadShops() {
    const shopsResponse = await api.get<ShopSettings[]>(
      `/settings/shops/${companyId}`,
    );
    const shopRows = shopsResponse.data;

    setShops(shopRows);
    setShopsLoaded(true);
    setShopForms(
      Object.fromEntries(
        shopRows.map((shop) => [
          shop.id,
          {
            name: shop.name || "",
            address_line_1: shop.address_line_1 || "",
            address_line_2: shop.address_line_2 || "",
            city: shop.city || "",
            state_province: shop.state_province || "",
            country: shop.country || "",
            phone: shop.phone || "",
            tax_vat_number: shop.tax_vat_number || "",
          },
        ]),
      ),
    );
  }

  async function loadSettings() {
    try {
      setLoading(true);
      setError("");
      setShops([]);
      setShopForms({});
      setShopsLoaded(false);

      const [
        aggregateResponse,
        receiptResponse,
        subscriptionResponse,
      ] =
        await Promise.all([
          api.get<AggregateSettings>(`/settings/${companyId}`),
          api.get<ReceiptSettings>(`/settings/receipts/${companyId}`),
          api.get<SubscriptionPageData>(
            `/subscriptions/${companyId}`,
          ),
        ]);

      const aggregate = aggregateResponse.data;
      const receipt = receiptResponse.data;
      const subscriptionPage = subscriptionResponse.data;

      setCompanyForm({
        name: aggregate.name || "",
        owner_name: aggregate.owner_name || "",
        owner_email: aggregate.owner_email || "",
        business_type: aggregate.business_type || "Retail",
        country: aggregate.country || "",
        phone: aggregate.phone || "",
        contact_email: aggregate.contact_email || "",
        currency_code: aggregate.currency_code || "USD",
        currency_symbol: aggregate.currency_symbol || "$",
        decimal_places: String(aggregate.decimal_places ?? 2),
      });

      setReceiptForm({
        receipt_header: receipt.receipt_header || "",
        receipt_footer: receipt.receipt_footer || "",
        paper_size: receipt.paper_size || "80mm",
        auto_print: Boolean(receipt.auto_print),
        tax_name: receipt.tax_name || "VAT",
        tax_rate: String(receipt.tax_rate ?? 0),
        tax_inclusive: Boolean(receipt.tax_inclusive),
        payment_methods:
          receipt.payment_methods?.length
            ? receipt.payment_methods
            : ["cash"],
      });

      setSubscription(subscriptionPage);
      setSubscriptionPlan(
        subscriptionPage.current.plan ||
          subscriptionPage.available_plans[0] ||
          "monthly",
      );
    } catch (requestError: any) {
      setError(
        requestErrorMessage(
          requestError,
          "Failed to load settings",
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSettings();
  }, [companyId]);

  useEffect(() => {
    if (section !== "shops" || shopsLoaded) {
      return;
    }

    void (async () => {
      try {
        setError("");
        await loadShops();
      } catch (requestError: any) {
        setError(
          requestErrorMessage(
            requestError,
            "Unable to load shop settings right now.",
          ),
        );
      }
    })();
  }, [companyId, section, shopsLoaded]);

  function updateCompanyField<K extends keyof CompanyForm>(
    field: K,
    value: CompanyForm[K],
  ) {
    setCompanyForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function updateReceiptField<K extends keyof ReceiptForm>(
    field: K,
    value: ReceiptForm[K],
  ) {
    setReceiptForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function updateShopField(
    shopId: string,
    field: keyof ShopFormMap[string],
    value: string,
  ) {
    setShopForms((current) => ({
      ...current,
      [shopId]: {
        ...current[shopId],
        [field]: value,
      },
    }));
  }

  function togglePaymentMethod(method: string) {
    setReceiptForm((current) => {
      const exists =
        current.payment_methods.includes(method);
      return {
        ...current,
        payment_methods: exists
          ? current.payment_methods.filter(
              (item) => item !== method,
            )
          : [...current.payment_methods, method],
      };
    });
  }

  async function saveCompanySettings() {
    try {
      setSaving(true);
      setError("");
      setMessage("");

      await api.patch(`/settings/${companyId}`, {
        name: companyForm.name.trim(),
        owner_name: companyForm.owner_name.trim() || null,
        business_type: companyForm.business_type.trim(),
        country: companyForm.country.trim() || null,
        phone: companyForm.phone.trim() || null,
        contact_email:
          companyForm.contact_email.trim() || null,
        currency_code:
          companyForm.currency_code.trim().toUpperCase(),
        currency_symbol: companyForm.currency_symbol.trim(),
        decimal_places: Number(companyForm.decimal_places),
      });

      setMessage("Company settings saved.");
      onDataChanged?.();
      await loadSettings();
    } catch (requestError: any) {
      setError(
        requestErrorMessage(
          requestError,
          "Failed to save company settings",
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveReceiptSettings() {
    try {
      setSaving(true);
      setError("");
      setMessage("");

      await api.patch(`/settings/receipts/${companyId}`, {
        receipt_header:
          receiptForm.receipt_header.trim() || null,
        receipt_footer:
          receiptForm.receipt_footer.trim() || null,
        paper_size: receiptForm.paper_size,
        auto_print: receiptForm.auto_print,
        tax_name: receiptForm.tax_name.trim(),
        tax_rate: Number(receiptForm.tax_rate),
        tax_inclusive: receiptForm.tax_inclusive,
        payment_methods: receiptForm.payment_methods,
      });

      setMessage("Receipt settings saved.");
      onDataChanged?.();
      await loadSettings();
    } catch (requestError: any) {
      setError(
        requestErrorMessage(
          requestError,
          "Failed to save receipt settings",
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveShop(shopId: string) {
    try {
      setSavingShopId(shopId);
      setError("");
      setMessage("");

      const form = shopForms[shopId];
      await api.patch(
        `/settings/shops/${companyId}/${shopId}`,
        {
          name: form.name.trim(),
          address_line_1:
            form.address_line_1.trim() || null,
          address_line_2:
            form.address_line_2.trim() || null,
          city: form.city.trim() || null,
          state_province:
            form.state_province.trim() || null,
          country: form.country.trim() || null,
          phone: form.phone.trim() || null,
          tax_vat_number:
            form.tax_vat_number.trim() || null,
        },
      );

      setMessage("Shop details saved.");
      await loadSettings();
    } catch (requestError: any) {
      setError(
        requestErrorMessage(
          requestError,
          "Failed to save shop details",
        ),
      );
    } finally {
      setSavingShopId("");
    }
  }

  async function activateSubscription(
    plan: string,
    actionLabel: string,
  ) {
    try {
      setSaving(true);
      setError("");
      setMessage("");
      const response = await api.post(
        "/subscriptions/activate",
        {
          company_id: companyId,
          plan,
        },
      );
      setMessage(
        response.data?.message ||
          `${actionLabel} request created.`,
      );
      if (response.data?.checkout_url) {
        window.open(
          response.data.checkout_url,
          "_blank",
          "noopener,noreferrer",
        );
      }
      await loadSettings();
    } catch (requestError: any) {
      setError(
        requestErrorMessage(
          requestError,
          `Unable to ${actionLabel.toLowerCase()} right now.`,
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  const selectedBillingOption =
    subscription?.billing_options.find(
      (option) => option.billing_period === subscriptionPlan,
    ) || subscription?.billing_options[0] || null;

  const rawSubscriptionStatus = (
    subscription?.current.display_status ||
    subscription?.current.status ||
    "expired"
  ).toLowerCase();
  const customerSubscriptionStatus = rawSubscriptionStatus === "trial"
    ? "Trial"
    : rawSubscriptionStatus === "active"
      ? "Active"
      : rawSubscriptionStatus === "past_due" ||
          rawSubscriptionStatus === "unpaid"
        ? "Past due"
        : "Expired";
  const isLegacySubscription = Boolean(
    subscription &&
      !subscription.current.plan &&
      subscription.current.snapshot.writes_allowed &&
      customerSubscriptionStatus === "Active",
  );
  const isChangingPlan = Boolean(
    subscription?.current.plan &&
      subscriptionPlan !== subscription.current.plan,
  );
  const subscriptionActionLabel = isChangingPlan
    ? "Change plan"
    : customerSubscriptionStatus === "Active" &&
        !isLegacySubscription &&
        Boolean(subscription?.current.plan)
      ? "Renew subscription"
      : "Continue to Paynow";
  const subscriptionActionName = isChangingPlan
    ? "Plan change"
    : subscriptionActionLabel === "Renew subscription"
      ? "Renewal"
      : "Activation";
  const subscriptionStatusMessage = isLegacySubscription
    ? "Your POS access remains active under legacy access."
    : customerSubscriptionStatus === "Trial"
      ? "Your trial is active. Choose a plan whenever you are ready."
      : customerSubscriptionStatus === "Active"
        ? "Your subscription is active and your POS is ready to use."
        : customerSubscriptionStatus === "Past due"
          ? "Payment is due. Continue to Paynow to keep your POS access current."
          : "Your subscription has expired. Choose a plan to restore full access.";
  const selectedPlanUnitLabel = subscriptionPlan === "yearly"
    ? "per terminal / year"
    : "per terminal / month";

  if (loading) {
    return (
      <section className="settings-loading">
        Loading settings...
      </section>
    );
  }

  return (
    <div className="settings-page">
      <div className="settings-intro">
        <div>
          <h2>
            {section === "home"
              ? "Settings"
              : summaryCards.find((card) => card.id === section)
                  ?.title || "Settings"}
          </h2>
          <p>
            {section === "home"
              ? "Choose one settings area at a time."
              : "Manage one settings page at a time and return to the hub when finished."}
          </p>
        </div>

        {section === "home" ? (
          <button
            className="settings-secondary-button"
            onClick={() => void loadSettings()}
            type="button"
          >
            Refresh
          </button>
        ) : (
          <button
            className="settings-secondary-button"
            onClick={() => setSection("home")}
            type="button"
          >
            Back to Settings
          </button>
        )}
      </div>

      {error ? (
        <div className="settings-alert error">{error}</div>
      ) : null}
      {message ? (
        <div className="settings-alert success">
          {message}
        </div>
      ) : null}

      {section === "home" ? (
        <section className="settings-home-grid">
          {summaryCards.map((card) => (
            <button
              key={card.id}
              className="settings-home-card"
              onClick={() => setSection(card.id)}
              type="button"
            >
              <strong>{card.title}</strong>
              <span>{card.description}</span>
            </button>
          ))}
        </section>
      ) : null}

      {section === "company" ? (
        <section className="settings-card">
          <div className="settings-card-heading">
            <h3>Company</h3>
            <p>
              Business identity, support contact and existing
              price formatting.
            </p>
          </div>

          <div className="settings-grid">
            <label>
              Business name
              <input
                value={companyForm.name}
                onChange={(event) =>
                  updateCompanyField("name", event.target.value)
                }
              />
            </label>

            <label>
              Owner name
              <input
                value={companyForm.owner_name}
                onChange={(event) =>
                  updateCompanyField(
                    "owner_name",
                    event.target.value,
                  )
                }
              />
            </label>

            <label>
              Owner account email
              <input value={companyForm.owner_email} disabled />
            </label>

            <label>
              Contact email
              <input
                value={companyForm.contact_email}
                onChange={(event) =>
                  updateCompanyField(
                    "contact_email",
                    event.target.value,
                  )
                }
              />
            </label>

            <label>
              Business type
              <input
                value={companyForm.business_type}
                onChange={(event) =>
                  updateCompanyField(
                    "business_type",
                    event.target.value,
                  )
                }
              />
            </label>

            <label>
              Country
              <input
                value={companyForm.country}
                onChange={(event) =>
                  updateCompanyField(
                    "country",
                    event.target.value,
                  )
                }
              />
            </label>

            <label>
              Phone
              <input
                value={companyForm.phone}
                onChange={(event) =>
                  updateCompanyField("phone", event.target.value)
                }
              />
            </label>

            <label>
              Currency code
              <input
                value={companyForm.currency_code}
                onChange={(event) =>
                  updateCompanyField(
                    "currency_code",
                    event.target.value.toUpperCase(),
                  )
                }
              />
            </label>

            <label>
              Currency symbol
              <input
                value={companyForm.currency_symbol}
                onChange={(event) =>
                  updateCompanyField(
                    "currency_symbol",
                    event.target.value,
                  )
                }
              />
            </label>

            <label>
              Decimal places
              <select
                value={companyForm.decimal_places}
                onChange={(event) =>
                  updateCompanyField(
                    "decimal_places",
                    event.target.value,
                  )
                }
              >
                <option value="0">0</option>
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="3">3</option>
                <option value="4">4</option>
              </select>
            </label>
          </div>

          <div className="settings-footer-actions">
            <button
              className="settings-save-button"
              onClick={() => void saveCompanySettings()}
              disabled={saving}
              type="button"
            >
              {saving ? "Saving..." : "Save Company"}
            </button>
          </div>
        </section>
      ) : null}

      {section === "shops" ? (
        <section className="settings-card">
          <div className="settings-card-heading">
            <h3>Shops</h3>
            <p>
              Each shop keeps its own receipt address and
              contact information.
            </p>
          </div>

          <div className="settings-shop-list">
            {shops.map((shop) => {
              const form = shopForms[shop.id];
              if (!form) {
                return null;
              }

              return (
                <article
                  className="settings-shop-card"
                  key={shop.id}
                >
                  <div className="settings-shop-header">
                    <div>
                      <strong>{shop.name}</strong>
                      <span>
                        {shop.active ? "Active shop" : "Inactive shop"}
                      </span>
                    </div>

                    <button
                      className="settings-save-button"
                      disabled={savingShopId === shop.id}
                      onClick={() => void saveShop(shop.id)}
                      type="button"
                    >
                      {savingShopId === shop.id
                        ? "Saving..."
                        : "Save Shop"}
                    </button>
                  </div>

                  <div className="settings-grid">
                    <label>
                      Shop name
                      <input
                        value={form.name}
                        onChange={(event) =>
                          updateShopField(
                            shop.id,
                            "name",
                            event.target.value,
                          )
                        }
                      />
                    </label>

                    <label>
                      Phone
                      <input
                        value={form.phone}
                        onChange={(event) =>
                          updateShopField(
                            shop.id,
                            "phone",
                            event.target.value,
                          )
                        }
                      />
                    </label>

                    <label className="settings-wide-field">
                      Address line 1
                      <input
                        value={form.address_line_1}
                        onChange={(event) =>
                          updateShopField(
                            shop.id,
                            "address_line_1",
                            event.target.value,
                          )
                        }
                      />
                    </label>

                    <label className="settings-wide-field">
                      Address line 2
                      <input
                        value={form.address_line_2}
                        onChange={(event) =>
                          updateShopField(
                            shop.id,
                            "address_line_2",
                            event.target.value,
                          )
                        }
                      />
                    </label>

                    <label>
                      City
                      <input
                        value={form.city}
                        onChange={(event) =>
                          updateShopField(
                            shop.id,
                            "city",
                            event.target.value,
                          )
                        }
                      />
                    </label>

                    <label>
                      State / Province
                      <input
                        value={form.state_province}
                        onChange={(event) =>
                          updateShopField(
                            shop.id,
                            "state_province",
                            event.target.value,
                          )
                        }
                      />
                    </label>

                    <label>
                      Country
                      <input
                        value={form.country}
                        onChange={(event) =>
                          updateShopField(
                            shop.id,
                            "country",
                            event.target.value,
                          )
                        }
                      />
                    </label>

                    <label>
                      Tax / VAT number
                      <input
                        value={form.tax_vat_number}
                        onChange={(event) =>
                          updateShopField(
                            shop.id,
                            "tax_vat_number",
                            event.target.value,
                          )
                        }
                      />
                    </label>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {section === "receipts" ? (
        <section className="settings-card">
          <div className="settings-card-heading">
            <h3>Receipts</h3>
            <p>
              Tax presentation, receipt copy and printer defaults.
            </p>
          </div>

          <div className="settings-grid">
            <label>
              Tax name
              <input
                value={receiptForm.tax_name}
                onChange={(event) =>
                  updateReceiptField(
                    "tax_name",
                    event.target.value,
                  )
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
                value={receiptForm.tax_rate}
                onChange={(event) =>
                  updateReceiptField(
                    "tax_rate",
                    event.target.value,
                  )
                }
              />
            </label>

            <label className="settings-checkbox-row">
              <input
                type="checkbox"
                checked={receiptForm.tax_inclusive}
                onChange={(event) =>
                  updateReceiptField(
                    "tax_inclusive",
                    event.target.checked,
                  )
                }
              />
              Prices already include tax
            </label>

            <label className="settings-checkbox-row">
              <input
                type="checkbox"
                checked={receiptForm.auto_print}
                onChange={(event) =>
                  updateReceiptField(
                    "auto_print",
                    event.target.checked,
                  )
                }
              />
              Automatically print after payment
            </label>

            <label>
              Receipt paper size
              <select
                value={receiptForm.paper_size}
                onChange={(event) =>
                  updateReceiptField(
                    "paper_size",
                    event.target.value,
                  )
                }
              >
                <option value="58mm">58mm thermal printer</option>
                <option value="80mm">80mm thermal printer</option>
              </select>
            </label>

            <label className="settings-wide-field">
              Receipt header
              <textarea
                rows={4}
                value={receiptForm.receipt_header}
                onChange={(event) =>
                  updateReceiptField(
                    "receipt_header",
                    event.target.value,
                  )
                }
              />
            </label>

            <label className="settings-wide-field">
              Receipt footer
              <textarea
                rows={4}
                value={receiptForm.receipt_footer}
                onChange={(event) =>
                  updateReceiptField(
                    "receipt_footer",
                    event.target.value,
                  )
                }
              />
            </label>
          </div>

          <div className="payment-method-grid">
            {availablePaymentMethods.map((method) => (
              <label
                className="payment-method-option"
                key={method.value}
              >
                <input
                  checked={receiptForm.payment_methods.includes(
                    method.value,
                  )}
                  onChange={() =>
                    togglePaymentMethod(method.value)
                  }
                  type="checkbox"
                />
                <span>{method.label}</span>
              </label>
            ))}
          </div>

          <div className="settings-footer-actions">
            <button
              className="settings-save-button"
              onClick={() => void saveReceiptSettings()}
              disabled={saving}
              type="button"
            >
              {saving ? "Saving..." : "Save Receipts"}
            </button>
          </div>
        </section>
      ) : null}

      {section === "devices" ? (
        <ShopsDevicesPage
          companyId={companyId}
          embedded
        />
      ) : null}

      {section === "subscription" && subscription ? (
        <section className="settings-card subscription-panel">
          <div className="subscription-panel-heading">
            <div>
              <span className="subscription-eyebrow">Subscription</span>
              <h3>
                {isLegacySubscription
                  ? "Legacy access"
                  : subscription.current.plan
                    ? subscription.current.plan === "yearly"
                      ? "Yearly plan"
                      : "Monthly plan"
                    : "Choose your plan"}
              </h3>
              <p>{subscriptionStatusMessage}</p>
            </div>
            <span
              className={`subscription-status-pill subscription-status-${rawSubscriptionStatus}`}
            >
              {customerSubscriptionStatus}
            </span>
          </div>

          <div className="subscription-plan-grid">
            <div className="subscription-metric">
              <span>Active terminals</span>
              <strong>{subscription.usage.active_terminals}</strong>
            </div>

            <label className="subscription-plan-select">
              Plan
              <select
                value={subscriptionPlan}
                onChange={(event) =>
                  setSubscriptionPlan(event.target.value)
                }
              >
                {subscription.available_plans.map((plan) => (
                  <option key={plan} value={plan}>
                    {plan === "monthly" ? "Monthly" : "Yearly"}
                  </option>
                ))}
              </select>
            </label>

            <div className="subscription-metric">
              <span>Price per terminal</span>
              <strong>
                {formatUsd(selectedBillingOption?.unit_price)}
              </strong>
              <small>{selectedPlanUnitLabel}</small>
            </div>

            <div className="subscription-total">
              <span>Total</span>
              <strong>
                {formatUsd(selectedBillingOption?.total_amount)}
              </strong>
              <small>
                {formatUsd(selectedBillingOption?.unit_price)} ×{" "}
                {selectedBillingOption?.terminal_count ??
                  subscription.usage.active_terminals}{" "}
                active terminal
                {(selectedBillingOption?.terminal_count ??
                  subscription.usage.active_terminals) === 1
                  ? ""
                  : "s"}
              </small>
            </div>
          </div>

          {customerSubscriptionStatus === "Trial" &&
          subscription.current.trial_ends_at ? (
            <div className="subscription-date-row">
              <span>Trial expires</span>
              <strong>
                {formatSubscriptionDate(subscription.current.trial_ends_at)}
              </strong>
            </div>
          ) : null}

          {customerSubscriptionStatus === "Active" &&
          !isLegacySubscription &&
          subscription.current.renewal_or_expiry_at ? (
            <div className="subscription-date-row">
              <span>Next renewal</span>
              <strong>
                {formatSubscriptionDate(
                  subscription.current.renewal_or_expiry_at,
                )}
              </strong>
            </div>
          ) : null}

          <button
            className="settings-save-button subscription-primary-action"
            onClick={() =>
              void activateSubscription(
                subscriptionPlan,
                subscriptionActionName,
              )
            }
            disabled={saving || !subscription.activation_available}
            type="button"
          >
            {saving ? "Processing..." : subscriptionActionLabel}
          </button>
        </section>
      ) : null}
    </div>
  );
}
