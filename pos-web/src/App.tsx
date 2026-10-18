import { applyDiscounts } from "./discounts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  ArrowRightStartOnRectangleIcon,
  QrCodeIcon,
  UsersIcon,
} from "@heroicons/react/24/outline";
import {
  api,
  getApiErrorMessage,
} from "./api/client";
import PosModulePage, { type PosModuleName } from "./PosModulePage";
import PosNavigation from "./components/PosNavigation";
import PosSessionHeader from "./components/PosSessionHeader";
import ShiftManagementPage, { type ShiftRecord } from "./ShiftManagementPage";
import {
  projectCreditSale,
  type CreditCustomer,
} from "./creditSale";
import { searchCustomers } from "./customerApi";
import BarcodeScannerDialog from "./barcode/BarcodeScannerDialog";
import { resolveBarcodeProduct } from "./barcode/barcode";
import { KeyboardWedgeDetector } from "./barcode/keyboardWedge";
import { useKeyboardWedge } from "./barcode/useKeyboardWedge";
import {
  clearAuthenticationPreservingDeviceIdentity,
  getOrCreateDeviceKey,
  getPinLoginDeviceIdentity,
  rememberDeviceIdentity,
} from "./deviceIdentity";
import { registerCurrentDevice } from "./device";
import {
  authenticateOfflineCashier,
  cacheOfflineCashier,
  isDeviceOnline,
} from "./offline/offlineAuth";

import {
  createClientSaleId,
  archiveReceiptSnapshot,
  exportQuarantinedOfflineSales,
  getArchivedReceiptSnapshot,
  getQuarantinedOfflineSales,
  isAndroidNativeApp,
  isNetworkFailure,
  queueOfflineSale,
  startAutomaticOfflineSaleSync,
  type OfflineSalePayload,
  type QuarantinedOfflineSale,
} from "./offline/offlineSales";
import {
  formatCents,
  formatMillis,
  multiplyPriceByQuantity,
  parseMoneyToCents,
  parseQuantityToMillis,
  quantityFromAmount,
  subtractQuantities,
  convertBaseToForeign,
  isCurrencyAmountAtLeast,
  subtractCurrencyAmounts,
} from "./decimal";
import {
  classifyEntitlementRefreshFailure,
  entitlementReconnectMessage,
  entitlementRefreshFailureMessage,
  loadEntitlementSnapshot,
  saveEntitlementSnapshot,
  verifyEntitlementSnapshotDetailed,
  type CachedEntitlementSnapshot,
} from "./offline/entitlement";
import {
  createTestReceiptSnapshot,
  getBluetoothStatus,
  getDefaultPrinterConfig,
  listBluetoothPrinters,
  listUsbPrinters,
  loadPrinterConfig,
  onBluetoothSettingsClosed,
  onPrinterAppResumed,
  onUsbDevicesChanged,
  openAppSettings,
  openBluetoothSettings,
  openPrintSettings,
  requestBluetoothAccess,
  requestUsbPermission,
  savePrinterConfig,
  sendReceiptToPrinter,
  verifyNativePrinterBridge,
} from "./printing/printerConfig";
import {
  buildEscPosPayload,
  buildReceiptHtml,
  encodeBase64,
} from "./printing/receiptFormatter";
import type {
  BluetoothStatus,
  PrinterConnectionType,
  PrinterConfig,
  PrinterDevice,
  ReceiptLineItem,
  ReceiptSnapshot,
} from "./printing/types";

import "./sales-responsive.css";
type Product = {
  id: string;
  name: string;
  sku?: string;
  barcode?: string;
  selling_price: string;
  stock_qty: string;
  unit?: string;
  active?: boolean;
  tax_rate?: string|null; tax_exempt?: boolean;
  variants?: Array<{id:string;product_id:string;name:string;sku?:string|null;barcode?:string|null;selling_price?:string|null;stock_qty:string;active:boolean}>;
  price_levels?:Array<{product_id:string;name:string;price:string;minimum_quantity:string;active:boolean}>;
};

type CartItem = Product & {
  cart_key:string; base_selling_price:string; variant_id?:string|null; variant_name?:string|null;
  line_discount_amount?: string;
  quantity: string;
  selling_unit: string;
  line_total: string;
};

type Receipt = {
  id: string;
  receipt_number: string;
  shift_id?: string | null;
  base_currency_code?: string | null;
  payment_currency_code?: string | null;
  exchange_rate_id?: string | null;
  exchange_rate_snapshot?: string | null;
  payment_amount_original?: string | null;
  tendered_amount_original?: string | null;
  change_amount_original?: string | null;
  cashier_name?: string | null;
  shop_id?: string | null;
  shop_name_snapshot?: string | null;
  shop_address_snapshot?: {
    address_line_1?: string | null;
    address_line_2?: string | null;
    city?: string | null;
    state_province?: string | null;
    country?: string | null;
    phone?: string | null;
    tax_vat_number?: string | null;
  } | null;
  branch_name_snapshot?: string | null;
  device_id?: string | null;
  pos_name_snapshot?: string | null;
  pos_number_snapshot?: string | null;
  receipt_footer_snapshot?: string | null;
  customer_id?: string | null;
  customer_name_snapshot?: string | null;
  customer_code_snapshot?: string | null;
  credit_due_date?: string | null;
  credit_outstanding_balance?: string | null;
  subtotal_amount?: string;
  tax_name?: string | null;
  tax_rate?: string;
  tax_amount?: string;
  tax_inclusive?: boolean;
  total_amount: string;
  discount_amount?: string | null;
  sale_discount_amount?: string | null;
  amount_received: string;
  change_due: string;
  payment_method: string;
  status: string;
  created_at: string;
  reprint_count?: number;
  last_reprinted_at?: string | null;
};


type BusinessSettings = {
  name?: string;
  currency_code?: string;
  currency_symbol?: string;
  decimal_places?: number;
  tax_name?: string;
  tax_rate?: string;
  tax_inclusive?: boolean;
  receipt_header?: string | null;
  receipt_footer?: string | null;
  paper_size?: string;
  auto_print?: boolean;
  payment_methods?: string[];
  shift_enforcement_enabled?: boolean;
};

type PosCurrency = {
  code: string;
  display_name: string;
  symbol: string;
  decimal_places: number;
  active: boolean;
  is_base: boolean;
  cash_accepted: boolean;
  card_accepted: boolean;
  mobile_accepted: boolean;
  current_rate: string | null;
  current_rate_id: string | null;
  rate_effective_at: string | null;
};

type PosCurrencyConfig = {
  company_id: string;
  version: number;
  generated_at: string;
  multi_currency_enabled: boolean;
  base_currency_code: string;
  currencies: PosCurrency[];
};

type SubscriptionSnapshot = {
  status: string;
  plan?: string | null;
  effective_until?: string | null;
  offline_grace_expires_at: string;
  snapshot_token: string;
  snapshot_expires_at: string;
  writes_allowed: boolean;
  message?: string | null;
};

type SubscriptionPage = {
  current: {
    status: string;
    plan?: string | null;
    snapshot: SubscriptionSnapshot;
  };
};

type RegistrationCurrency = {
  code: string;
  display_name: string;
  symbol: string;
  decimal_places: number;
};

type SaleReceiptResponse = Receipt & {
  items: Array<{
    product_id?: string;
    product_name: string;
    quantity: string;
    selling_unit?: string;
    unit_price: string;
    line_total: string;
    line_discount_amount?: string | null;
  }>;
  cashier_name?: string | null;
};

type CashierSession = {
  id: string;
  name: string;
  role: string;
  branch_id: string;
  permissions?: Record<string, boolean>;
  access_token?: string;
};

function logPrinterDiagnostic(action: string, error: unknown) {
  console.error(`[printer] ${action}`, error);
}

function getPrinterErrorCode(error: unknown): string {
  if (
    error &&
    typeof error === "object" &&
    "code" in error &&
    typeof (error as { code?: unknown }).code === "string"
  ) {
    return (error as { code: string }).code;
  }

  if (error instanceof Error) {
    const match = error.message.match(/\(([^)]+)\)$/);
    if (match?.[1]) {
      return match[1];
    }
  }

  return "";
}

function roundMoneyValue(value: string | number): number {
  return Number(formatCents(parseMoneyToCents(value)));
}

function initialPosModule(): PosModuleName {
  const requested = new URLSearchParams(window.location.search).get("module");
  return (["Sales", "Sales Management", "Customers", "Credit Settlements", "Expenses", "Shift Management", "Products", "Inventory", "Reports", "Settings"] as PosModuleName[])
    .includes(requested as PosModuleName) ? requested as PosModuleName : "Sales";
}

function App() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [companyId, setCompanyId] = useState(
    localStorage.getItem("company_id") || "",
  );
  
  const [branchId, setBranchId] = useState(
    localStorage.getItem("branch_id") || "",
  );

const [loggedIn, setLoggedIn] = useState(
    Boolean(localStorage.getItem("token")),
  );

  const [authMode, setAuthMode] =
    useState<"login" | "register">("login");

  const [ownerName, setOwnerName] = useState("");
  const [ownerPin, setOwnerPin] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [businessType, setBusinessType] = useState("Retail");
  const [country, setCountry] = useState("Zimbabwe");
  const [phone, setPhone] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [registrationCurrencies, setRegistrationCurrencies] = useState<RegistrationCurrency[]>([]);
  const [baseCurrencyCode, setBaseCurrencyCode] = useState("");
  const [registrationCurrenciesLoading, setRegistrationCurrenciesLoading] = useState(false);
  const [registrationCurrenciesError, setRegistrationCurrenciesError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);


  const [products, setProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [saleDiscount, setSaleDiscount] = useState("0");
  const [search, setSearch] = useState("");
  const [salesScannerOpen, setSalesScannerOpen] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [message, setMessage] = useState("");
  const [quarantinedSales, setQuarantinedSales] =
    useState<QuarantinedOfflineSale[]>([]);
  const [processing, setProcessing] = useState(false);
  const [showCreditSale, setShowCreditSale] = useState(false);
  const [creditCustomerSearch, setCreditCustomerSearch] = useState("");
  const [creditCustomers, setCreditCustomers] = useState<CreditCustomer[]>([]);
  const [selectedCreditCustomer, setSelectedCreditCustomer] =
    useState<CreditCustomer | null>(null);
  const [creditCustomersLoading, setCreditCustomersLoading] = useState(false);
  const [variantProduct,setVariantProduct]=useState<Product|null>(null);
  const [pricingCustomer,setPricingCustomer]=useState<CreditCustomer|null>(null);
  const [creditDialogMessage, setCreditDialogMessage] = useState("");
  const [menuOpen, setMenuOpen] = useState(() =>
    window.matchMedia("(min-width: 1024px)").matches,
  );
  const [activePosModule, setActivePosModule] = useState<PosModuleName>(initialPosModule);

  useEffect(() => {
    const syncModule = () => {
      setActivePosModule(initialPosModule());
      setMenuOpen(window.matchMedia("(min-width: 1024px)").matches);
      setMessage("");
    };
    window.addEventListener("popstate", syncModule);
    return () => window.removeEventListener("popstate", syncModule);
  }, []);

  const [showTender, setShowTender] = useState(false);
  const [amountReceived, setAmountReceived] = useState("");
  const [currencyConfig, setCurrencyConfig] = useState<PosCurrencyConfig | null>(null);
  const [selectedPaymentCurrencyCode, setSelectedPaymentCurrencyCode] = useState("");
  const [currencyQuoteError, setCurrencyQuoteError] = useState("");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [receiptItems, setReceiptItems] = useState<CartItem[]>([]);
  const [businessSettings, setBusinessSettings] =
    useState<BusinessSettings | null>(null);
  const [entitlementSnapshot, setEntitlementSnapshot] =
    useState<CachedEntitlementSnapshot | null>(null);
  const [entitlementVerificationMessage, setEntitlementVerificationMessage] =
    useState("");
  const [entitlementRefreshNotice, setEntitlementRefreshNotice] =
    useState("");
  const [weightedProduct, setWeightedProduct] =
    useState<Product | null>(null);
  const [weightedQuantity, setWeightedQuantity] = useState("0.250");
  const [weightedAmount, setWeightedAmount] = useState("1.00");
  const [printerConfig, setPrinterConfig] =
    useState<PrinterConfig>(getDefaultPrinterConfig());
  const [printerConfigLoaded, setPrinterConfigLoaded] = useState(false);
  const [bluetoothPrinterDevices, setBluetoothPrinterDevices] =
    useState<PrinterDevice[]>([]);
  const [usbPrinterDevices, setUsbPrinterDevices] =
    useState<PrinterDevice[]>([]);
  const [isDiscoveringDevices, setIsDiscoveringDevices] = useState(false);
  const [isSavingPrinter, setIsSavingPrinter] = useState(false);
  const [isTestingPrinter, setIsTestingPrinter] = useState(false);
  const [printerNotice, setPrinterNotice] = useState("");
  const [printerDiscoveryError, setPrinterDiscoveryError] = useState("");
  const [printerSaveError, setPrinterSaveError] = useState("");
  const [printerTestError, setPrinterTestError] = useState("");
  const [bluetoothPermissionDenied, setBluetoothPermissionDenied] =
    useState(false);
  const [bluetoothStatus, setBluetoothStatus] =
    useState<BluetoothStatus>({
      available: false,
      enabled: false,
    });
  const [printerRefreshSignal, setPrinterRefreshSignal] = useState(0);

  const [cashier, setCashier] =
    useState<CashierSession | null>(null);
  const [currentShift, setCurrentShift] = useState<(ShiftRecord & { offline_shift_token?: string | null }) | null>(null);
  const [shiftLoading, setShiftLoading] = useState(false);
  const [shiftPromptDismissed, setShiftPromptDismissed] = useState(false);
  const [cashierPin, setCashierPin] = useState("");
  const [pinLoading, setPinLoading] = useState(false);
  const [pinMessage, setPinMessage] = useState("");
  const [pinSelection, setPinSelection] = useState<{shops: Array<{id:string;name:string}>; terminals: Array<{id:string;shop_id:string;branch_id:string;name:string;pos_number?:number|null}>; pin:string} | null>(null);
  const [selectedShopId, setSelectedShopId] = useState("");
  const [selectedTerminalId, setSelectedTerminalId] = useState("");
  const [takeoverPrompt, setTakeoverPrompt] = useState(false);
  const [takeoverSelection, setTakeoverSelection] = useState<{
    shop_id: string;
    device_id: string;
  } | null>(null);
  const latestDiscoveryRequestIdRef = useRef(0);
  const activeDiscoveryScopeRef = useRef<string | null>(null);
  const saleSubmissionInFlightRef = useRef(false);
  const creditClientSaleIdRef = useRef<string | null>(null);
  const nonCreditSaleIdentityRef = useRef<{
    fingerprint: string;
    clientSaleId: string;
  } | null>(null);
  const salesSearchWedgeRef = useRef(new KeyboardWedgeDetector());

  useKeyboardWedge(
    Boolean(
      loggedIn &&
      cashier &&
      activePosModule === "Sales" &&
      !menuOpen &&
      !showTender &&
      !showCreditSale &&
      !weightedProduct &&
      !receipt &&
      !salesScannerOpen
    ),
    handleSalesBarcode,
  );

  function validateRegistrationForm() {
    const trimmedOwnerName = ownerName.trim();
    const trimmedBusinessName =
      businessName.trim();
    const trimmedBusinessType =
      businessType.trim();
    const trimmedCountry = country.trim();
    const trimmedPhone = phone.trim();
    const normalizedEmail =
      email.trim().toLowerCase();
    const selectedCurrency = registrationCurrencies.find(
      (currency) => currency.code === baseCurrencyCode,
    );

    if (trimmedOwnerName.length < 2) {
      throw new Error(
        "owner name: String should have at least 2 characters",
      );
    }

    if (!/^\d{4}$/.test(ownerPin)) {
      throw new Error(
        "owner pin: String should match pattern '^\\d{4}$'",
      );
    }

    if (trimmedBusinessName.length < 2) {
      throw new Error(
        "business name: String should have at least 2 characters",
      );
    }

    if (trimmedBusinessType.length < 2) {
      throw new Error(
        "business type: String should have at least 2 characters",
      );
    }

    if (trimmedCountry.length < 2) {
      throw new Error(
        "country: String should have at least 2 characters",
      );
    }

    if (trimmedPhone.length < 3) {
      throw new Error(
        "phone: String should have at least 3 characters",
      );
    }

    if (!normalizedEmail) {
      throw new Error("email: Value is required");
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      throw new Error("email: Value is not a valid email address");
    }

    if (password.length < 8) {
      throw new Error(
        "password: String should have at least 8 characters",
      );
    }

    if (confirmPassword.length < 8) {
      throw new Error(
        "confirm password: String should have at least 8 characters",
      );
    }

    if (password !== confirmPassword) {
      throw new Error("confirm password: Passwords do not match");
    }

    if (!selectedCurrency) {
      throw new Error("base currency: Select a base currency");
    }

    return {
      owner_name: trimmedOwnerName,
      owner_pin: ownerPin,
      business_name: trimmedBusinessName,
      business_type: trimmedBusinessType,
      country: trimmedCountry,
      phone: trimmedPhone,
      email: normalizedEmail,
      password,
      confirm_password: confirmPassword,
      base_currency_code: selectedCurrency.code,
      base_currency_symbol: selectedCurrency.symbol,
      base_currency_decimal_places: selectedCurrency.decimal_places,
    };
  }

  useEffect(() => {
    if (loggedIn || authMode !== "register" || registrationCurrencies.length) {
      return;
    }

    let cancelled = false;
    setRegistrationCurrenciesLoading(true);
    setRegistrationCurrenciesError("");
    void api.get("/auth/registration-currencies")
      .then((response) => {
        if (!cancelled) {
          setRegistrationCurrencies(response.data?.items || []);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setRegistrationCurrenciesError(
            getApiErrorMessage(error, "Unable to load supported currencies"),
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setRegistrationCurrenciesLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [authMode, loggedIn, registrationCurrencies.length]);

  useEffect(() => {
    const onInvalidated = () => {
      setCashier(null);
      setPinMessage("This POS session was ended on another device. Please sign in again.");
      setCart([]);
      setSaleDiscount("0");
    };
    window.addEventListener("apex-session-invalidated", onInvalidated);
    return () => window.removeEventListener("apex-session-invalidated", onInvalidated);
  }, []);

  useEffect(() => {
    void loadPrinterConfig()
      .then((config) => {
        setPrinterConfig(config);
      })
      .catch((error) => {
        logPrinterDiagnostic("load config", error);
      })
      .finally(() => {
        setPrinterConfigLoaded(true);
      });
  }, []);

  const signalPrinterRefresh = useCallback((reason: string) => {
    console.info("[printer] discovery signal", { reason });
    setPrinterRefreshSignal((current) => current + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const listenerHandles: Array<{
      remove: () => Promise<void>;
    }> = [];

    async function attachPrinterListeners() {
      const bluetoothHandle =
        await onBluetoothSettingsClosed(() => {
          if (cancelled) {
            return;
          }

          signalPrinterRefresh("bluetooth-settings-closed");
        });

      if (bluetoothHandle) {
        listenerHandles.push(bluetoothHandle);
      }

      const usbHandle = await onUsbDevicesChanged(() => {
        if (cancelled) {
          return;
        }

        signalPrinterRefresh("usb-devices-changed");
      });

      if (usbHandle) {
        listenerHandles.push(usbHandle);
      }

      const resumeHandle =
        await onPrinterAppResumed(() => {
          if (cancelled || activePosModule !== "Settings") {
            return;
          }

          signalPrinterRefresh("app-resume");
        });

      if (resumeHandle) {
        listenerHandles.push(resumeHandle);
      }
    }

    void attachPrinterListeners();

    return () => {
      cancelled = true;
      listenerHandles.forEach((handle) => {
        void handle.remove();
      });
    };
  }, [activePosModule, signalPrinterRefresh]);

  useEffect(() => {
    if (
      !loggedIn ||
      !companyId ||
      !isAndroidNativeApp()
    ) {
      return;
    }

    let disposed = false;
    let stopSyncListener:
      | (() => Promise<void>)
      | undefined;

    void (async () => {
      try {
        stopSyncListener =
          await startAutomaticOfflineSaleSync(
            (result) => {
              if (disposed) {
                return;
              }

              if (result.synced > 0) {
                setMessage(
                  `Synced ${result.synced} offline sale${
                    result.synced === 1 ? "" : "s"
                  } successfully`,
                );

                void loadProducts(
                  companyId,
                  branchId || undefined,
                );
              } else if (result.quarantined > 0) {
                setMessage(
                  `${result.quarantined} offline sale${
                    result.quarantined === 1 ? " is" : "s are"
                  } quarantined and will not retry automatically`,
                );
              } else if (result.pending > 0) {
                setMessage(
                  `${result.pending} offline sale${
                    result.pending === 1 ? "" : "s"
                  } waiting to sync`,
                );
              }
              void getQuarantinedOfflineSales()
                .then(setQuarantinedSales)
                .catch((error) => console.error(
                  "Failed to load quarantined offline sales",
                  error,
                ));
            },
          );
      } catch (error) {
        console.error(
          "Offline synchronization startup failed",
          error,
        );
      }
    })();

    return () => {
      disposed = true;

      if (stopSyncListener) {
        void stopSyncListener();
      }
    };
  }, [loggedIn, companyId, branchId]);

  async function exportOfflineQuarantine() {
    try {
      const contents = await exportQuarantinedOfflineSales();
      const blob = new Blob([contents], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `apexretail-offline-quarantine-${new Date()
        .toISOString().replace(/[:.]/g, "-")}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setMessage("Quarantined offline sales exported. The original queue remains unchanged.");
    } catch (error) {
      setMessage(getApiErrorMessage(error, "Failed to export quarantined offline sales"));
    }
  }

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();

    return products.filter((product) =>
      product.name.toLowerCase().includes(query) ||
      (product.sku || "").toLowerCase().includes(query) ||
      (product.barcode || "").toLowerCase().includes(query)
    );
  }, [products, search]);

  let discountError = "";
  let discounted = {
    items: cart,
    line_discount_total: "0.00",
    discount_amount: "0.00",
    sale_discount_amount: "0.00",
    total: "0.00",
  };
  try {
    discounted = applyDiscounts(cart, cart.length ? saleDiscount : "0");
  } catch (error) {
    discountError = (error as Error).message;
  }
  const cartAmount = Number(discounted.total);

  const configuredTaxRate = Math.max(
    0,
    Number(businessSettings?.tax_rate || 0),
  );

  const taxInclusive = Boolean(
    businessSettings?.tax_inclusive,
  );

  const taxName =
    businessSettings?.tax_name?.trim() || "Tax";

  let subtotal = cartAmount;
  let taxAmount = 0;
  let total = cartAmount;

  const productTaxRules=discounted.items.some(item=>item.tax_exempt||item.tax_rate!=null);
  if(productTaxRules){taxAmount=roundMoneyValue(discounted.items.reduce((sum,item)=>{const rate=item.tax_exempt?0:Number(item.tax_rate??configuredTaxRate),line=Number(item.line_total);return sum+(rate<=0?0:taxInclusive?line*rate/(100+rate):line*rate/100)},0));if(taxInclusive){total=cartAmount;subtotal=roundMoneyValue(total-taxAmount)}else{subtotal=cartAmount;total=roundMoneyValue(subtotal+taxAmount)}} else if (configuredTaxRate > 0) {
    if (taxInclusive) {
      total = cartAmount;

      taxAmount = roundMoneyValue(
        total *
          (configuredTaxRate / (100 + configuredTaxRate)),
      );

      subtotal = roundMoneyValue(
        total - taxAmount,
      );
    } else {
      subtotal = cartAmount;

      taxAmount = roundMoneyValue(
        subtotal *
          (configuredTaxRate / 100),
      );

      total = roundMoneyValue(
        subtotal + taxAmount,
      );
    }
  }

  const basePosCurrency = currencyConfig?.currencies.find((currency) => currency.is_base) || null;
  const acceptedPaymentCurrencies = currencyConfig?.currencies.filter((currency) => {
    const method = paymentMethod.trim().toLowerCase();
    const accepted = method === "cash" ? currency.cash_accepted
      : method === "card" ? currency.card_accepted
        : method === "mobile" ? currency.mobile_accepted : false;
    return currency.active && accepted && (currency.is_base || currencyConfig.multi_currency_enabled);
  }) || [];
  const activePaymentCurrency = acceptedPaymentCurrencies.find(
    (currency) => currency.code === selectedPaymentCurrencyCode,
  ) || basePosCurrency;
  let paymentDueText = "";
  let paymentChangeText = "";
  try {
    if (activePaymentCurrency && basePosCurrency) {
      paymentDueText = convertBaseToForeign(
        total.toFixed(basePosCurrency.decimal_places), basePosCurrency.decimal_places,
        String(activePaymentCurrency.current_rate ?? "1"), activePaymentCurrency.decimal_places,
      );
      paymentChangeText = subtractCurrencyAmounts(
        amountReceived || "0", paymentDueText, activePaymentCurrency.decimal_places,
      );
    }
  } catch {
    paymentDueText = "";
    paymentChangeText = "";
  }
  const creditProjection = projectCreditSale(
    selectedCreditCustomer,
    total,
  );

  async function loadBusinessSettings(
    selectedCompanyId: string,
  ) {
    if (!selectedCompanyId) {
      return;
    }

    const response = await api.get(
      `/settings/${selectedCompanyId}`,
    );

    const loadedSettings =
      response.data as BusinessSettings;

    setBusinessSettings(loadedSettings);

    const methods = (
      loadedSettings.payment_methods || []
    )
      .map((method) =>
        String(method).trim().toLowerCase(),
      )
      .filter(Boolean);

    if (methods.length) {
      setPaymentMethod((currentMethod) =>
        methods.includes(currentMethod)
          ? currentMethod
          : methods[0],
      );
    }
  }

  async function loadSubscriptionSnapshot(
    selectedCompanyId: string,
  ) {
    if (!selectedCompanyId) {
      return;
    }

    try {
      const response = await api.get(
        `/subscriptions/${selectedCompanyId}`,
      );
      const subscription =
        response.data as SubscriptionPage;
      const snapshot = subscription.current.snapshot;
      const cached: CachedEntitlementSnapshot = {
        company_id: selectedCompanyId,
        status: snapshot.status,
        plan: snapshot.plan || null,
        writes_allowed: snapshot.writes_allowed,
        effective_until: snapshot.effective_until || null,
        offline_grace_expires_at:
          snapshot.offline_grace_expires_at,
        snapshot_expires_at:
          snapshot.snapshot_expires_at,
        snapshot_token: snapshot.snapshot_token,
        message: snapshot.message || null,
        updated_at: new Date().toISOString(),
      };
      const verification = await verifyEntitlementSnapshotDetailed(cached);
      if (verification.ok) {
        // Never replace the last known-good offline authorization until the
        // newly issued snapshot has passed local signature and claim checks.
        saveEntitlementSnapshot(cached);
        setEntitlementSnapshot(cached);
        setEntitlementVerificationMessage("");
        setEntitlementRefreshNotice("");
      } else {
        setEntitlementSnapshot(null);
        setEntitlementRefreshNotice("");
        setEntitlementVerificationMessage(
          entitlementReconnectMessage(verification.category),
        );
      }
    } catch (error) {
      const refreshFailure = classifyEntitlementRefreshFailure(error);
      if (refreshFailure.category !== "temporary_unavailable") {
        setEntitlementSnapshot(null);
        setEntitlementRefreshNotice("");
        setEntitlementVerificationMessage(
          entitlementRefreshFailureMessage(refreshFailure, false),
        );
        throw error;
      }

      const cached = loadEntitlementSnapshot(selectedCompanyId);
      if (!cached) {
        setEntitlementSnapshot(null);
        setEntitlementVerificationMessage("");
        setEntitlementRefreshNotice(
          entitlementRefreshFailureMessage(refreshFailure, false),
        );
        return;
      }
      const verification = await verifyEntitlementSnapshotDetailed(cached);
      if (verification.ok) {
        setEntitlementSnapshot(cached);
        setEntitlementVerificationMessage("");
        setEntitlementRefreshNotice(
          entitlementRefreshFailureMessage(refreshFailure, true),
        );
      } else {
        setEntitlementSnapshot(null);
        setEntitlementRefreshNotice(
          entitlementRefreshFailureMessage(refreshFailure, false),
        );
        setEntitlementVerificationMessage(
          entitlementReconnectMessage(verification.category),
        );
      }
    }
  }

  const currencySymbol =
    businessSettings?.currency_symbol || "$";

  const decimalPlaces =
    businessSettings?.decimal_places ?? 2;

  function formatMoney(value: number | string) {
    const numericValue = Number(value || 0);

    return `${currencySymbol}${numericValue.toFixed(
      decimalPlaces,
    )}`;
  }

  function formatQuantity(
    quantity: string | number,
    sellingUnit?: string,
  ) {
    const rendered = Number(quantity || 0)
      .toFixed(3)
      .replace(/\.?0+$/, "");
    return sellingUnit
      ? `${rendered} ${sellingUnit}`
      : rendered;
  }

  async function canCreateOfflineSale() {
    const verification = await verifyEntitlementSnapshotDetailed(
      entitlementSnapshot,
    );
    if (verification.ok) {
      setEntitlementVerificationMessage("");
      return true;
    }
    setEntitlementVerificationMessage(
      entitlementReconnectMessage(verification.category),
    );
    return false;
  }

  function getBranchName() {
    return localStorage.getItem("branch_name") || "Assigned branch";
  }

  function getShopName() {
    return localStorage.getItem("shop_name") || "Main shop";
  }

  function getPosName() {
    return localStorage.getItem("pos_name") || "POS";
  }

  function getPosNumber() {
    return localStorage.getItem("pos_number");
  }

  function getShopAddressSnapshot() {
    const rawValue = localStorage.getItem(
      "shop_address_snapshot",
    );

    if (!rawValue) {
      return null;
    }

    try {
      return JSON.parse(rawValue) as ReceiptSnapshot["shop_address"];
    } catch {
      return null;
    }
  }

  function buildReceiptSnapshot(
    sale: Receipt,
    items: ReceiptLineItem[],
    cashierName?: string | null,
  ): ReceiptSnapshot {
    return {
      id: sale.id,
      receipt_number: sale.receipt_number,
      company_id: companyId,
      device_id:
        sale.device_id ||
        localStorage.getItem("device_id") ||
        null,
      shop_id:
        sale.shop_id ||
        localStorage.getItem("shop_id") ||
        null,
      shop_name:
        sale.shop_name_snapshot ||
        getShopName(),
      shop_address:
        sale.shop_address_snapshot ||
        getShopAddressSnapshot(),
      branch_id: branchId || null,
      branch_name:
        sale.branch_name_snapshot ||
        getBranchName(),
      business_name:
        businessSettings?.name?.trim() || "ApexRetail POS",
      pos_name:
        sale.pos_name_snapshot ||
        getPosName(),
      pos_number:
        sale.pos_number_snapshot ||
        getPosNumber(),
      receipt_header: businessSettings?.receipt_header || null,
      receipt_footer:
        sale.receipt_footer_snapshot ||
        businessSettings?.receipt_footer ||
        null,
      created_at: sale.created_at,
      shift_id: sale.shift_id || null,
      base_currency_code: sale.base_currency_code || businessSettings?.currency_code || null,
      payment_currency_code: sale.payment_currency_code || sale.base_currency_code || businessSettings?.currency_code || null,
      exchange_rate_id: sale.exchange_rate_id || null,
      exchange_rate_snapshot: sale.exchange_rate_snapshot || null,
      payment_amount_original: sale.payment_amount_original || null,
      tendered_amount_original: sale.tendered_amount_original || null,
      change_amount_original: sale.change_amount_original || null,
      cashier_name: cashierName || cashier?.name || null,
      customer_name: sale.customer_name_snapshot || null,
      customer_code: sale.customer_code_snapshot || null,
      credit_due_date: sale.credit_due_date || null,
      credit_outstanding_balance:
        sale.credit_outstanding_balance || null,
      subtotal_amount: sale.subtotal_amount,
      tax_name: sale.tax_name || null,
      tax_rate: sale.tax_rate,
      tax_amount: sale.tax_amount,
      tax_inclusive: sale.tax_inclusive,
      total_amount: sale.total_amount,
      discount_amount: sale.discount_amount,
      sale_discount_amount: sale.sale_discount_amount,
      amount_received: sale.amount_received,
      change_due: sale.change_due,
      payment_method: sale.payment_method,
      status: sale.status,
      items,
    };
  }

  const persistPrinterConfig = useCallback(async (
    nextConfig: PrinterConfig,
  ): Promise<void> => {
    if (
      nextConfig.connectionType === "bluetooth" &&
      nextConfig.selectedPrinterId
    ) {
      console.info("[printer] selected device", {
        id: nextConfig.selectedPrinterId,
        name: nextConfig.selectedPrinterName,
      });
    }

    try {
      setIsSavingPrinter(true);
      setPrinterSaveError("");
      const savedConfig = await savePrinterConfig(nextConfig);
      setPrinterConfig(savedConfig);
      console.info("[printer] save success", {
        connectionType: savedConfig.connectionType,
        selectedPrinterId: savedConfig.selectedPrinterId,
        selectedPrinterName: savedConfig.selectedPrinterName,
      });
      setPrinterNotice(
        savedConfig.connectionType === "bluetooth"
          ? "Printer saved."
          : "Printer settings saved on this device.",
      );
    } catch (error) {
      setPrinterSaveError(
        getApiErrorMessage(error, "Failed to save printer settings."),
      );
      console.error("[printer] save failure", error);
      logPrinterDiagnostic("save config", error);
      throw error;
    } finally {
      setIsSavingPrinter(false);
    }
  }, []);

  const refreshPrinterDevices = useCallback(async (
    connectionType?: PrinterConnectionType,
  ) => {
    const refreshScope = connectionType || "all";

    if (activeDiscoveryScopeRef.current === refreshScope) {
      console.info("[printer] discovery skipped overlapping refresh", {
        connectionType: refreshScope,
      });
      return;
    }

    const requestId = latestDiscoveryRequestIdRef.current + 1;
    latestDiscoveryRequestIdRef.current = requestId;
    activeDiscoveryScopeRef.current = refreshScope;
    console.info("[printer] discovery start", {
      requestId,
      connectionType: refreshScope,
    });

    setIsDiscoveringDevices(true);
    setPrinterNotice("");
    setPrinterDiscoveryError("");
    setBluetoothPermissionDenied(false);

    try {
      await verifyNativePrinterBridge();

      const shouldLoadBluetooth =
        !connectionType || connectionType === "bluetooth";
      const shouldLoadUsb =
        !connectionType || connectionType === "usb";

      if (shouldLoadBluetooth) {
        const permissionResult =
          await requestBluetoothAccess();
        if (requestId !== latestDiscoveryRequestIdRef.current) {
          return;
        }
        console.info("[printer] permission result", permissionResult);

        if (!permissionResult.granted) {
          setBluetoothPrinterDevices([]);
          setBluetoothPermissionDenied(true);
          setPrinterNotice(
            "Bluetooth permission denied.",
          );
          return;
        }

        const nextBluetoothStatus =
          await getBluetoothStatus();
        if (requestId !== latestDiscoveryRequestIdRef.current) {
          return;
        }
        setBluetoothStatus(nextBluetoothStatus);

        if (!nextBluetoothStatus.available) {
          throw new Error(
            "Bluetooth is not available on this Android device.",
          );
        }

        if (!nextBluetoothStatus.enabled) {
          setBluetoothPrinterDevices([]);
          setPrinterNotice(
            "Bluetooth is off.",
          );
          return;
        }

        const bondedDevices =
          await listBluetoothPrinters();
        if (requestId !== latestDiscoveryRequestIdRef.current) {
          return;
        }
        setBluetoothPrinterDevices(
          bondedDevices,
        );
        setPrinterNotice(
          bondedDevices.length
            ? ""
            : "No paired Bluetooth printers found.",
        );
      }

      if (shouldLoadUsb) {
        const nextUsbDevices = await listUsbPrinters();
        if (requestId !== latestDiscoveryRequestIdRef.current) {
          return;
        }
        setUsbPrinterDevices(nextUsbDevices);
      }
    } catch (error) {
      if (requestId !== latestDiscoveryRequestIdRef.current) {
        return;
      }
      logPrinterDiagnostic("refresh devices", error);
      const errorCode = getPrinterErrorCode(error);
      if (errorCode === "bluetooth_permission_denied") {
        setBluetoothPrinterDevices([]);
        setBluetoothPermissionDenied(true);
      }
      const message =
        errorCode === "bluetooth_permission_denied"
          ? "Bluetooth permission denied."
          : error instanceof Error &&
              /ApexPrinter|plugin is not implemented|bridge/i.test(error.message)
            ? "Printer services are unavailable in this Android build."
            : getApiErrorMessage(
                error,
                "Printer list could not be updated.",
              );
      setPrinterDiscoveryError(message);
      setPrinterNotice(message);
    } finally {
      if (requestId === latestDiscoveryRequestIdRef.current) {
        console.info("[printer] discovery end", {
          requestId,
          connectionType: refreshScope,
        });
        activeDiscoveryScopeRef.current = null;
        setIsDiscoveringDevices(false);
      }
    }
  }, []);

  const handleOpenBluetoothSettings = useCallback(async () => {
    console.info("[printer] settings launch", {
      target: "bluetooth",
    });
    try {
      await openBluetoothSettings();
    } catch (error) {
      logPrinterDiagnostic("open bluetooth settings", error);
      throw error;
    }
  }, []);

  const handleOpenAppSettings = useCallback(async () => {
    console.info("[printer] settings launch", {
      target: "app",
    });
    try {
      await openAppSettings();
    } catch (error) {
      logPrinterDiagnostic("open app settings", error);
      throw error;
    }
  }, []);

  const handleOpenPrintSettings = useCallback(async () => {
    console.info("[printer] settings launch", {
      target: "system-print",
    });
    try {
      await openPrintSettings();
    } catch (error) {
      logPrinterDiagnostic("open android print settings", error);
      throw error;
    }
  }, []);

  async function printReceiptSnapshot(
    snapshot: ReceiptSnapshot,
    config: PrinterConfig = printerConfig,
  ) {
    const html = buildReceiptHtml(
      snapshot,
      config,
    );
    const rawDataBase64 = encodeBase64(
      buildEscPosPayload(snapshot, config),
    );

    await sendReceiptToPrinter({
      config,
      html,
      rawDataBase64,
      jobName: snapshot.receipt_number,
    });
  }

  async function handlePrintShiftSummary(shift: ShiftRecord, authoritativeHtml?: string) {
    const shiftMoney = (value: string | number | null | undefined, currency: ShiftRecord["currencies"][number]) => {
      const numeric = Number(value ?? 0);
      try {
        return new Intl.NumberFormat(undefined, {
          style: "currency", currency: currency.currency_code,
          minimumFractionDigits: currency.decimal_places,
          maximumFractionDigits: currency.decimal_places,
        }).format(numeric);
      } catch {
        return `${currency.symbol}${numeric.toFixed(currency.decimal_places)} ${currency.currency_code}`;
      }
    };
    const lines = [
      { label: "Status", value: shift.status.toUpperCase() },
      { label: "Opened", value: new Date(shift.opened_at).toLocaleString() },
      { label: "Closed", value: shift.closed_at ? new Date(shift.closed_at).toLocaleString() : "Still open" },
      ...(shift.summary.base_currency_code ? [{ label: `Sales (${shift.summary.base_currency_code})`, value: String(shift.summary.total_sales_base || "0.00") }] : []),
      ...shift.currencies.filter((currency) => currency.cash_accepted).flatMap((currency) => [
        { label: `${currency.currency_code} opening`, value: shiftMoney(currency.opening_float, currency) },
        { label: `${currency.currency_code} cash sales`, value: shiftMoney(currency.cash_sales, currency) },
        { label: `${currency.currency_code} settlements`, value: shiftMoney(currency.cash_settlements, currency) },
        { label: `${currency.currency_code} cash in`, value: shiftMoney(currency.cash_in, currency) },
        { label: `${currency.currency_code} cash out`, value: shiftMoney(currency.cash_out, currency) },
        { label: `${currency.currency_code} refunds`, value: shiftMoney(currency.cash_refunds, currency) },
        { label: `${currency.currency_code} expenses`, value: shiftMoney(currency.cash_expenses, currency) },
        { label: `${currency.currency_code} expected`, value: shiftMoney(currency.expected_cash, currency) },
        { label: `${currency.currency_code} counted`, value: currency.counted_cash === null ? "Not counted" : shiftMoney(currency.counted_cash, currency) },
        { label: `${currency.currency_code} variance`, value: currency.variance === null ? "Open" : shiftMoney(currency.variance, currency) },
      ]),
    ];
    const snapshot: ReceiptSnapshot = {
      id: shift.id, receipt_number: shift.shift_number, company_id: shift.company_id,
      business_name: businessSettings?.name || "ApexRetail POS", shop_name: shift.shop_name,
      branch_name: shift.branch_name, pos_name: shift.register_name,
      created_at: new Date().toISOString(), cashier_name: shift.cashier_name || cashier?.name || null,
      total_amount: "0", amount_received: "0", change_due: "0",
      payment_method: "shift_summary", status: "informational", items: [],
      document_type: "shift_summary", shift_summary_lines: lines,
      receipt_footer: "SHIFT SUMMARY - NOT A SALES RECEIPT",
    };
    if (authoritativeHtml) {
      await sendReceiptToPrinter({
        config: printerConfig,
        html: authoritativeHtml,
        rawDataBase64: encodeBase64(buildEscPosPayload(snapshot, printerConfig)),
        jobName: `Z Report ${shift.shift_number}`,
      });
    } else {
      await printReceiptSnapshot(snapshot);
    }
    setPrinterNotice(`Printed shift summary ${shift.shift_number}`);
  }

  async function handlePrintZReport(shift: ShiftRecord) {
    const response = await api.get<string>(`/shifts/${shift.id}/z-report/thermal`, {
      params: { paper_width: printerConfig.paperWidth },
      responseType: "text",
    });
    await handlePrintShiftSummary(shift, response.data);
  }

  async function archiveAndMaybePrintReceipt(
    snapshot: ReceiptSnapshot,
  ) {
    try {
      await archiveReceiptSnapshot(snapshot);

      if (!printerConfig.enabled || !printerConfig.autoPrint) {
        return;
      }

      await printReceiptSnapshot(snapshot);
      setPrinterNotice(`Printed ${snapshot.receipt_number}`);
    } catch (error) {
      setPrinterNotice(
        getApiErrorMessage(
          error,
          "Sale completed, but printing failed.",
        ),
      );
    }
  }

  async function handlePrintCurrentReceipt() {
    if (!receipt) {
      return;
    }

    const snapshot = buildReceiptSnapshot(
      receipt,
      receiptItems.map((item) => ({
        product_id: item.id,
        name: item.name,
        quantity: item.quantity,
        selling_unit: item.selling_unit,
        unit_price: item.selling_price,
        line_total: item.line_total,
        line_discount_amount: item.line_discount_amount,
      })),
    );

    try {
      await printReceiptSnapshot(snapshot);
      setPrinterNotice(
        `Printed ${snapshot.receipt_number}`,
      );
    } catch (error) {
      setPrinterNotice(
        getApiErrorMessage(
          error,
          "Printing failed.",
        ),
      );
    }
  }

  const handleTestPrint = useCallback(async (
    currentConfig: PrinterConfig,
  ) => {
    console.info("[printer] test click", {
      connectionType: currentConfig.connectionType,
      selectedPrinterId: currentConfig.selectedPrinterId,
    });
    setIsTestingPrinter(true);
    setPrinterNotice("");
    setPrinterTestError("");

    try {
      if (
        currentConfig.connectionType === "usb" &&
        currentConfig.selectedPrinterId
      ) {
        const permissionResult =
          await requestUsbPermission(
            currentConfig.selectedPrinterId,
          );

        if (!permissionResult.granted) {
          throw new Error(
            "USB permission denied for the selected printer.",
          );
        }
      }

      await printReceiptSnapshot(
        createTestReceiptSnapshot(
          companyId,
          getBranchName(),
          cashier?.name || "Cashier",
        ),
        currentConfig,
      );
      setPrinterNotice(
        currentConfig.connectionType === "system"
          ? "Print dialog opened"
          : "Test print sent successfully",
      );
    } catch (error) {
      const fallbackMessage = getApiErrorMessage(
        error,
        "Check the printer, paper, or selection.",
      );
      logPrinterDiagnostic("test print", error);
      const errorCode = getPrinterErrorCode(error);
      if (
        currentConfig.connectionType === "bluetooth" &&
        (errorCode === "bluetooth_io_error" ||
          errorCode === "bluetooth_printer_unavailable")
      ) {
        setPrinterTestError(
          "Test print failed: This printer may require System Printer.",
        );
        setPrinterNotice(
          "Test print failed: This printer may require System Printer.",
        );
      } else {
        setPrinterTestError(`Test print failed: ${fallbackMessage}`);
        setPrinterNotice(
          `Test print failed: ${fallbackMessage}`,
        );
      }
    } finally {
      setIsTestingPrinter(false);
    }
  }, [cashier?.name, companyId]);

  async function handleReprintSale(
    saleId: string,
    receiptNumber?: string,
  ) {
    try {
      const archivedReceipt =
        await getArchivedReceiptSnapshot(
          saleId,
          receiptNumber,
        );

      if (archivedReceipt) {
        await printReceiptSnapshot({
          ...archivedReceipt,
          is_duplicate: true,
          original_receipt_number: archivedReceipt.receipt_number,
          original_sale_time: archivedReceipt.created_at,
          reprint_at: new Date().toISOString(),
          reprint_count: (archivedReceipt.reprint_count || 0) + 1,
        });
        setPrinterNotice(
          `Reprinted ${archivedReceipt.receipt_number}`,
        );
        return;
      }

      const response = await api.get(
        `/sales/receipt/${companyId}/${saleId}`,
        { params: { mark_reprint: true } },
      );

      const sale = response.data as SaleReceiptResponse;
      const snapshot = buildReceiptSnapshot(
        sale,
        sale.items.map((item) => ({
          product_id: item.product_id,
          name: item.product_name,
          quantity: item.quantity,
          selling_unit: item.selling_unit,
          unit_price: item.unit_price,
          line_total: item.line_total,
          line_discount_amount: item.line_discount_amount,
        })),
        sale.cashier_name,
      );
      snapshot.is_duplicate = true;
      snapshot.original_receipt_number = sale.receipt_number;
      snapshot.original_sale_time = sale.created_at;
      snapshot.reprint_at = sale.last_reprinted_at || new Date().toISOString();
      snapshot.reprint_count = sale.reprint_count || 1;

      await archiveReceiptSnapshot(snapshot);
      await printReceiptSnapshot(snapshot);
      setPrinterNotice(
        `Reprinted ${snapshot.receipt_number}`,
      );
    } catch (error) {
      setPrinterNotice(
        getApiErrorMessage(
          error,
          "Reprint failed. If the sale is offline and has not been archived on this device, reconnect and try again.",
        ),
      );
    }
  }

  const enabledPaymentMethods = useMemo(() => {
    const methods = (
      businessSettings?.payment_methods || []
    )
      .map((method) =>
        String(method).trim().toLowerCase(),
      )
      .filter(Boolean);

    return methods.length
      ? methods
      : ["cash", "card", "mobile", "credit"];
  }, [businessSettings]);

  async function loadProducts(
    id = companyId,
    selectedBranchId = branchId,
  ) {
    if (!id) return;

    try {
      const [productResponse,variantResponse,priceResponse]=await Promise.all([api.get(`/products/${id}`),api.get(`/products/variants/${id}`,{params:{branch_id:selectedBranchId||undefined}}),api.get(`/products/price-levels/${id}`)]);

      let loadedProducts = productResponse.data.map((product:Product)=>{const variants=variantResponse.data.filter((v:any)=>v.product_id===product.id&&v.active),price_levels=priceResponse.data.filter((v:any)=>v.product_id===product.id&&v.active);return {...product,variants,price_levels,stock_qty:variants.length?String(variants.reduce((n:number,v:any)=>n+Number(v.stock_qty||0),0)):product.stock_qty};});

      if (selectedBranchId) {
        const balanceResponse = await api.get(
          `/inventory/branch-overview/${id}`,
          {
            params: {
              branch_id: selectedBranchId,
            },
          },
        );

        const balances = new Map<string, string>(
          balanceResponse.data.map((balance: any) => [
            balance.product_id,
            balance.quantity,
          ]),
        );

        loadedProducts = loadedProducts.map(
          (product: Product) => ({
            ...product,
            stock_qty:
              product.variants?.length
                ? product.stock_qty
                : balances.get(product.id) || "0",
          }),
        );
      }

      setProducts(loadedProducts);
    } catch (error) {
      console.error(error);
      setMessage("Failed to load branch products");
    }
  }

  async function completeAuthentication(data: any) {
    const nextCompanyId = String(
      data?.company_id || data?.company?.id || "",
    );

    if (!data?.token || !nextCompanyId) {
      throw new Error(
        "Authentication response did not contain a token and company",
      );
    }

    const previousCompanyId =
      localStorage.getItem("device_company_id") ||
      localStorage.getItem("company_id");

    if (
      previousCompanyId &&
      previousCompanyId !== nextCompanyId
    ) {
      localStorage.removeItem("device_key");
      localStorage.removeItem("device_id");
      localStorage.removeItem("branch_id");
      localStorage.removeItem("branch_name");
      localStorage.removeItem("shop_id");
      localStorage.removeItem("shop_name");
      localStorage.removeItem("pos_name");
      localStorage.removeItem("pos_number");
      localStorage.removeItem("shop_address_snapshot");
    }

    const authenticatedDeviceKey = String(
      data?.device?.device_key || "",
    ).trim();
    const authenticatedDeviceId = String(
      data?.device?.id || data?.device_id || "",
    ).trim();
    if (authenticatedDeviceKey) {
      rememberDeviceIdentity(
        nextCompanyId,
        authenticatedDeviceKey,
        authenticatedDeviceId || undefined,
      );
    } else {
      getOrCreateDeviceKey(nextCompanyId);
    }

    localStorage.setItem("token", String(data.token));
    localStorage.setItem("company_id", nextCompanyId);

    const shopId = String(
      data?.shop?.id || data?.shop_id || "",
    );

    const shopName = String(
      data?.shop?.name || data?.shop_name || "",
    );

    const nextBranchId = String(
      data?.branch?.id || data?.branch_id || "",
    );

    const branchName = String(
      data?.branch?.name || data?.branch_name || "",
    );

    const employeeId = String(
      data?.employee?.id ||
      data?.employee_id ||
      "",
    );

    const deviceKey = String(
      data?.device?.device_key ||
      data?.device_key ||
      "",
    );

    if (shopId) {
      localStorage.setItem("shop_id", shopId);
    }

    if (shopName) {
      localStorage.setItem("shop_name", shopName);
    }

    if (nextBranchId) {
      localStorage.setItem("branch_id", nextBranchId);
      const assignmentRevision =
        data?.assignment_revision ?? data?.device?.assignment_revision;
      if (assignmentRevision != null) {
        localStorage.setItem(
          "device_assignment_revision",
          String(assignmentRevision),
        );
      }
    }

    if (branchName) {
      localStorage.setItem("branch_name", branchName);
    }

    if (employeeId) {
      localStorage.setItem("employee_id", employeeId);
    }

    if (data?.employee?.access_token) {
      localStorage.setItem(
        "employee_token",
        String(data.employee.access_token),
      );
    } else {
      localStorage.removeItem("employee_token");
    }

    if (deviceKey) {
      rememberDeviceIdentity(
        nextCompanyId,
        deviceKey,
        String(data?.device?.id || data?.device_id || "") || undefined,
      );
    }

    if (data?.device?.id || data?.device_id) {
      localStorage.setItem(
        "device_id",
        String(data?.device?.id || data?.device_id),
      );
    }

    setCompanyId(nextCompanyId);
    setBranchId(nextBranchId);
    setLoggedIn(true);

    if (data?.employee && nextBranchId) {
      setCashier({
        id: employeeId,
        name: data.employee.name || ownerName || "Owner",
        role: data.employee.role || "owner",
        branch_id: nextBranchId,
        permissions: data.employee.permissions || {},
        access_token: data.employee.access_token || "",
      });
    } else {
      localStorage.removeItem("employee_id");
      localStorage.removeItem("employee_token");
      setCashier(null);
    }

    await loadProducts(
      nextCompanyId,
      nextBranchId || undefined,
    );

    await loadBusinessSettings(nextCompanyId);
    await loadSubscriptionSnapshot(nextCompanyId);
  }

  async function login() {
    try {
      setAuthLoading(true);
      setMessage("");

      if (!email.trim() || !password) {
        throw new Error(
          "Enter your email address and password",
        );
      }

      const response = await api.post("/auth/login", {
        email: email.trim().toLowerCase(),
        password,
      });

      await completeAuthentication(response.data);
    } catch (error: any) {
      setMessage(
        getApiErrorMessage(error, "Login failed"),
      );
    } finally {
      setAuthLoading(false);
    }
  }

  async function registerBusiness() {
    try {
      setAuthLoading(true);
      setMessage("");
      const payload = validateRegistrationForm();

      const response = await api.post(
        "/auth/register",
        {
          ...payload,
          device_key: getOrCreateDeviceKey(),
        },
      );

      await completeAuthentication(response.data);
    } catch (error: any) {
      setMessage(
        getApiErrorMessage(
          error,
          "Business registration failed",
        ),
      );
    } finally {
      setAuthLoading(false);
    }
  }

  async function loginWithEmployeePin(selection?: {shop_id: string; device_id: string; takeover?: boolean}) {
    if (!companyId) {
      setPinMessage("Business session is not available");
      return;
    }

    if (!branchId) {
      setPinMessage("This POS device is not assigned to a branch");
      return;
    }

    const enteredPin = cashierPin.trim();

    if (!/^\d{4}$/.test(enteredPin)) {
      setPinMessage("Enter your four-digit employee PIN");
      return;
    }

    const storedIdentity = getPinLoginDeviceIdentity(companyId);
    const attemptedSelection = {
      shop_id: selection?.shop_id || localStorage.getItem("shop_id") || "",
      device_id: selection?.device_id || storedIdentity.device_id || "",
    };

    try {
      setPinLoading(true);
      setPinMessage("");

      const online = await isDeviceOnline();

      if (!online) {
        const cachedCashier =
          await authenticateOfflineCashier(
            companyId,
            branchId,
            enteredPin,
          );

        if (!cachedCashier) {
          setPinMessage(
            "This PIN is not available offline yet. Connect to the internet and sign in with this PIN once.",
          );
          return;
        }

        if (cachedCashier.permissions?.sales === false) {
          setPinMessage(
            "This employee does not have permission to make sales",
          );
          return;
        }

        setCashier({
          id: cachedCashier.employee_id,
          name: cachedCashier.name || "Employee",
          role: cachedCashier.role || "cashier",
          branch_id: cachedCashier.branch_id || branchId,
          permissions: cachedCashier.permissions || {},
          access_token: cachedCashier.access_token || "",
        });
        localStorage.setItem(
          "employee_id",
          cachedCashier.employee_id,
        );
        if (cachedCashier.access_token) {
          localStorage.setItem(
            "employee_token",
            cachedCashier.access_token,
          );
        } else {
          localStorage.removeItem("employee_token");
        }

        setCashierPin("");
        setMessage(
          "Offline mode — sales will be saved on this device and synchronized when internet returns",
        );

        return;
      }

      try {
        const response = await api.post(
          "/employees/pin-login",
          {
            company_id: companyId,
            branch_id: branchId,
            shop_id: localStorage.getItem("shop_id") || undefined,
            pin: enteredPin,
            ...storedIdentity,
            ...(selection || {}),
          },
        );

        const result =
          response.data?.employee || response.data;

        if (result.selection_required) {
          setPinSelection({ shops: result.shops || [], terminals: result.terminals || [], pin: enteredPin });
          setSelectedShopId(result.shops?.[0]?.id || "");
          setSelectedTerminalId(result.terminals?.[0]?.id || "");
          return;
        }

        const employeeId =
          result?.id || result?.employee_id || "";

        if (!employeeId) {
          throw new Error(
            "Employee login response has no employee ID",
          );
        }

        if (result.permissions?.sales === false) {
          setPinMessage(
            "This employee does not have permission to make sales",
          );
          return;
        }

        const authenticatedCashier = {
          id: employeeId,
          name: result.name || "Employee",
          role: result.role || "cashier",
          branch_id: result.branch_id || branchId,
          permissions: result.permissions || {},
          access_token: result.access_token || "",
        };

        setCashier(authenticatedCashier);
        setPinSelection(null);
        setTakeoverPrompt(false);
        setTakeoverSelection(null);
        if (result.device_id) {
          rememberDeviceIdentity(
            companyId,
            String(result.device_key || storedIdentity.device_key),
            String(result.device_id),
          );
        }
        localStorage.setItem("employee_id", employeeId);
        if (result.access_token) {
          localStorage.setItem(
            "employee_token",
            String(result.access_token),
          );
        } else {
          localStorage.removeItem("employee_token");
        }

        await cacheOfflineCashier(
          companyId,
          branchId,
          enteredPin,
          authenticatedCashier,
        );

        setCashierPin("");
        setMessage("");
      } catch (networkError: any) {
        if (networkError?.response?.status === 409) {
          throw networkError;
        }
        /*
         * Internet can disappear between Network.getStatus()
         * and the API request. In that case, try the local PIN.
         */
        const cachedCashier =
          await authenticateOfflineCashier(
            companyId,
            branchId,
            enteredPin,
          );

        if (cachedCashier) {
          if (cachedCashier.permissions?.sales === false) {
            setPinMessage(
              "This employee does not have permission to make sales",
            );
            return;
          }

          setCashier({
            id: cachedCashier.employee_id,
            name: cachedCashier.name || "Employee",
            role: cachedCashier.role || "cashier",
            branch_id: cachedCashier.branch_id || branchId,
            permissions: cachedCashier.permissions || {},
            access_token: cachedCashier.access_token || "",
          });
          localStorage.setItem(
            "employee_id",
            cachedCashier.employee_id,
          );
          if (cachedCashier.access_token) {
            localStorage.setItem(
              "employee_token",
              cachedCashier.access_token,
            );
          } else {
            localStorage.removeItem("employee_token");
          }

          setCashierPin("");
          setMessage(
            "Offline mode — sales will synchronize when internet returns",
          );

          return;
        }

        setPinMessage(
          getApiErrorMessage(
            networkError,
            "Employee PIN login failed",
          ),
        );
      }
    } catch (error: any) {
      const detail = getApiErrorMessage(error, "Employee PIN login failed");
      if (detail.toLowerCase().includes("already signed in") || detail.toLowerCase().includes("already in use")) {
        setTakeoverPrompt(true);
        setTakeoverSelection(
          attemptedSelection.shop_id && attemptedSelection.device_id
            ? attemptedSelection
            : null,
        );
      } else {
        setPinMessage(detail);
      }
    } finally {
      setPinLoading(false);
    }
  }

  function switchCashier() {
    void api.post("/employees/session/logout").catch(() => undefined);
    localStorage.removeItem("employee_id");
    localStorage.removeItem("employee_token");
    setCashier(null);
    setCurrentShift(null);
    setShiftPromptDismissed(false);
    setCashierPin("");
    setPinMessage("");
    setCart([]);
    setSaleDiscount("0");
    setShowTender(false);
    setAmountReceived("");
    setReceipt(null);
    setReceiptItems([]);
    setMessage("");
    nonCreditSaleIdentityRef.current = null;
  }



  function levelPrice(product:Product,quantity:string,base:string){const name=pricingCustomer?.price_level_name?.toLowerCase();return (product.price_levels||[]).filter(p=>p.name.toLowerCase()===name&&Number(p.minimum_quantity)<=Number(quantity)).sort((a,b)=>Number(b.minimum_quantity)-Number(a.minimum_quantity))[0]?.price||base;}
  function choosePricingCustomer(id:string){const customer=creditCustomers.find(c=>c.id===id)||null;setPricingCustomer(customer);setCart(current=>current.map(item=>{const name=customer?.price_level_name?.toLowerCase();const price=(item.price_levels||[]).filter(p=>p.name.toLowerCase()===name&&Number(p.minimum_quantity)<=Number(item.quantity)).sort((a,b)=>Number(b.minimum_quantity)-Number(a.minimum_quantity))[0]?.price||item.base_selling_price;return {...item,selling_price:price,line_total:multiplyPriceByQuantity(price,item.quantity)}}));}
  function addToCart(product: Product) {
    if(product.variants?.length){setVariantProduct(product);return;}
    const availableStock = parseQuantityToMillis(
      product.stock_qty,
    );

    if (availableStock <= 0n) {
      setMessage(`${product.name} is out of stock`);
      return;
    }

    if (product.unit && product.unit !== "each") {
      setWeightedProduct(product);
      setWeightedQuantity("0.250");
      setWeightedAmount(
        multiplyPriceByQuantity(
          product.selling_price,
          "0.250",
        ),
      );
      return;
    }

    setCart((currentCart) => {
      const existing = currentCart.find(
        (item) => item.cart_key === product.id,
      );

      if (existing) {
        const nextQuantity =
          parseQuantityToMillis(existing.quantity) +
          1000n;
        if (nextQuantity > availableStock) {
          setMessage(
            `Only ${formatQuantity(
              product.stock_qty,
              product.unit,
            )} available`,
          );
          return currentCart;
        }

        return currentCart.map((item) =>
          item.cart_key === product.id
            ? {
                ...item,
                quantity: formatMillis(nextQuantity, false),
                line_total: multiplyPriceByQuantity(
                  item.selling_price,
                  formatMillis(nextQuantity, false),
                ),
              }
            : item
        );
      }

      return [
        ...currentCart,
        {
          ...product,
          cart_key:product.id,
          base_selling_price:product.selling_price,
          quantity: "1.000",
          selling_unit: product.unit || "each", selling_price:levelPrice(product,"1.000",product.selling_price),
          line_total: multiplyPriceByQuantity(
            levelPrice(product,"1.000",product.selling_price),
            "1.000",
          ),
        },
      ];
    });
  }

  function addVariant(product:Product,variant:NonNullable<Product["variants"]>[number]){
    if(Number(variant.stock_qty)<=0){setMessage(`${product.name} — ${variant.name} is out of stock`);return;}
    const key=`${product.id}:${variant.id}`,base=String(variant.selling_price??product.selling_price),price=levelPrice(product,"1.000",base);
    setCart(current=>{const existing=current.find(i=>i.cart_key===key);if(existing){const q=Number(existing.quantity)+1;if(q>Number(variant.stock_qty))return current;return current.map(i=>i.cart_key===key?{...i,quantity:q.toFixed(3),line_total:multiplyPriceByQuantity(price,q.toFixed(3))}:i)}return [...current,{...product,cart_key:key,base_selling_price:price,variant_id:variant.id,variant_name:variant.name,stock_qty:variant.stock_qty,selling_price:price,quantity:"1.000",selling_unit:product.unit||"each",line_total:multiplyPriceByQuantity(price,"1.000")}];});setVariantProduct(null);
  }

  function handleSalesBarcode(rawBarcode: string) {
    const code=rawBarcode.trim().toLowerCase();
    for(const product of products){const variant=product.variants?.find(v=>(v.barcode||"").trim().toLowerCase()===code);if(variant){addVariant(product,variant);setSalesScannerOpen(false);return;}}
    const resolution = resolveBarcodeProduct(products, rawBarcode);
    if (resolution.status === "not_found") {
      setMessage(`Product Not Found: ${resolution.barcode}`);
      return;
    }
    if (resolution.status === "ambiguous") {
      setMessage(
        `Barcode ${resolution.barcode} is assigned to multiple products. Contact a manager.`,
      );
      return;
    }
    setMessage("");
    setSalesScannerOpen(false);
    addToCart(resolution.product);
  }

  function handleSalesSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    const barcode = salesSearchWedgeRef.current.feed({
      key: event.key,
      timestamp: event.timeStamp,
      modifier: event.altKey || event.ctrlKey || event.metaKey,
      repeat: event.repeat,
      composing: event.nativeEvent.isComposing,
    });
    if (barcode) {
      event.preventDefault();
      setSearch("");
      handleSalesBarcode(barcode);
    }
  }

  function changeQty(id: string, difference: number) {
    setCart((currentCart) =>
      currentCart.map((item) => {
        if (item.cart_key !== id) return item;
        if (item.selling_unit !== "each") {
          return item;
        }

        const availableStock = parseQuantityToMillis(
          item.stock_qty,
        );
        const nextQty =
          parseQuantityToMillis(item.quantity) +
          BigInt(difference) * 1000n;
        const clamped = nextQty < 1000n ? 1000n : nextQty > availableStock ? availableStock : nextQty;

        return {
          ...item,
          quantity: formatMillis(clamped, false),
          line_total: multiplyPriceByQuantity(
            item.selling_price,
            formatMillis(clamped, false),
          ),
        };
      })
    );
  }

  function addWeightedProductToCart() {
    if (!weightedProduct) {
      return;
    }
    const quantityMillis = parseQuantityToMillis(
      weightedQuantity,
    );
    const availableMillis = parseQuantityToMillis(
      weightedProduct.stock_qty,
    );
    if (quantityMillis <= 0n) {
      setMessage("Enter a quantity greater than zero");
      return;
    }
    if (quantityMillis > availableMillis) {
      setMessage(
        `Only ${formatQuantity(
          weightedProduct.stock_qty,
          weightedProduct.unit,
        )} available`,
      );
      return;
    }
    const lineTotal = multiplyPriceByQuantity(
      weightedProduct.selling_price,
      weightedQuantity,
    );
    setCart((currentCart) => [
      ...currentCart,
      {
        ...weightedProduct,
        cart_key:weightedProduct.id,
        base_selling_price:weightedProduct.selling_price,
        quantity: formatMillis(quantityMillis, false),
        selling_unit: weightedProduct.unit || "kg",
        line_total: lineTotal,
      },
    ]);
    setWeightedProduct(null);
    setMessage("");
  }

  function removeFromCart(id: string) {
    setCart((currentCart) =>
      currentCart.filter((item) => item.cart_key !== id)
    );
  }

  async function loadCreditCustomers(query = creditCustomerSearch) {
    try {
      setCreditCustomersLoading(true);
      setCreditDialogMessage("");
      const customers = await searchCustomers(companyId, query, {
        activeOnly: true,
        limit: 100,
      });
      setCreditCustomers(customers);
      if (
        selectedCreditCustomer &&
        !customers.some((customer: CreditCustomer) =>
          customer.id === selectedCreditCustomer.id)
      ) {
        setSelectedCreditCustomer(null);
      }
    } catch (error) {
      setCreditCustomers([]);
      setCreditDialogMessage(
        getApiErrorMessage(error, "Unable to load customers"),
      );
    } finally {
      setCreditCustomersLoading(false);
    }
  }

  async function openCreditSaleDialog() {
    if (!(await isDeviceOnline())) {
      setMessage("Credit sales require an online connection. Reconnect and try again.");
      return;
    }
    if (cashier?.permissions?.credit_sales === false) {
      setMessage("This cashier does not have permission to create credit sales.");
      return;
    }

    setCreditCustomerSearch("");
    setSelectedCreditCustomer(null);
    setCreditDialogMessage("");
    creditClientSaleIdRef.current = createClientSaleId();
    setShowCreditSale(true);
    await loadCreditCustomers("");
  }

  function closeCreditSaleDialog() {
    if (processing) return;
    setShowCreditSale(false);
    setSelectedCreditCustomer(null);
    setCreditDialogMessage("");
    creditClientSaleIdRef.current = null;
  }

  async function startPayment() {
    setMessage("");
    if (discountError) { setMessage(discountError); return; }

    if (!cart.length) {
      setMessage("Add at least one product to the cart");
      return;
    }

    if (paymentMethod === "credit") {
      await openCreditSaleDialog();
      return;
    }

    try {
      const response = await api.get(`/currencies/${companyId}/pos-config`);
      const config = response.data as PosCurrencyConfig;
      if (config.company_id !== companyId || !config.base_currency_code || !Array.isArray(config.currencies)) {
        throw new Error("Company payment currency configuration is invalid");
      }
      const method = paymentMethod.trim().toLowerCase();
      if (!("cash card mobile".split(" ").includes(method))) {
        throw new Error("This payment method is not available for multi-currency checkout");
      }
      const eligible = config.currencies.filter((currency) => currency.active && (
        method === "cash" ? currency.cash_accepted
          : method === "card" ? currency.card_accepted
            : currency.mobile_accepted
      ) && (currency.is_base || config.multi_currency_enabled));
      const base = eligible.find((currency) => currency.code === config.base_currency_code && currency.is_base);
      if (!base) throw new Error("The company base currency is not enabled for this payment method");
      setCurrencyConfig(config);
      const previous = eligible.find((currency) => currency.code === selectedPaymentCurrencyCode);
      const selected = previous || base;
      setSelectedPaymentCurrencyCode(selected.code);
      setCurrencyQuoteError("");
      setAmountReceived(paymentMethod === "cash" ? convertBaseToForeign(
        total.toFixed(base.decimal_places), base.decimal_places,
        selected.current_rate == null ? "1" : String(selected.current_rate), selected.decimal_places,
      ) : "");
      setShowTender(true);
    } catch (error) {
      if (
        isAndroidNativeApp() && isNetworkFailure(error)
        && businessSettings?.currency_code
        && await canCreateOfflineSale()
      ) {
        const offlineBase: PosCurrency = {
          code: businessSettings.currency_code,
          display_name: businessSettings.currency_code,
          symbol: businessSettings.currency_symbol || businessSettings.currency_code,
          decimal_places: businessSettings.decimal_places ?? 2,
          active: true, is_base: true,
          cash_accepted: true, card_accepted: true, mobile_accepted: true,
          current_rate: "1", current_rate_id: null, rate_effective_at: null,
        };
        const offlineConfig: PosCurrencyConfig = {
          company_id: companyId, version: 1, generated_at: new Date().toISOString(),
          multi_currency_enabled: false, base_currency_code: offlineBase.code,
          currencies: [offlineBase],
        };
        setCurrencyConfig(offlineConfig);
        setSelectedPaymentCurrencyCode(offlineBase.code);
        setCurrencyQuoteError("");
        setAmountReceived(paymentMethod === "cash" ? total.toFixed(offlineBase.decimal_places) : "");
        setShowTender(true);
        setMessage("Offline mode: only the previously loaded base currency is available.");
        return;
      }
      setCurrencyQuoteError(getApiErrorMessage(error, "Unable to load accepted payment currencies"));
      setMessage(getApiErrorMessage(error, "Unable to load accepted payment currencies"));
    }
  }

  async function submitSale(
    cashAmount?: string | number,
    creditCustomer?: CreditCustomer,
  ) {
    if (discountError) { setMessage(discountError); return; }
    if (!cart.length || processing || saleSubmissionInFlightRef.current) {
      return;
    }

    if (!cashier) {
      setMessage("Cashier PIN is required");
      return;
    }

    if (paymentMethod === "credit") {
      if (!(await isDeviceOnline())) {
        setCreditDialogMessage(
          "Credit sales require an online connection. Reconnect and try again.",
        );
        return;
      }
      const projection = projectCreditSale(creditCustomer || null, total);
      if (projection.error) {
        setCreditDialogMessage(projection.error);
        return;
      }
    }

    const paymentCurrency = currencyConfig?.currencies.find(
      (currency) => currency.code === selectedPaymentCurrencyCode,
    );
    const baseCurrency = currencyConfig?.currencies.find((currency) => currency.is_base);
    if (paymentMethod !== "credit") {
      if (!currencyConfig || currencyConfig.company_id !== companyId || !paymentCurrency || !paymentCurrency.active) {
        setMessage("Reload the payment currency configuration before completing this sale.");
        return;
      }
      const accepted = paymentMethod === "cash" ? paymentCurrency.cash_accepted
        : paymentMethod === "card" ? paymentCurrency.card_accepted
          : paymentMethod === "mobile" ? paymentCurrency.mobile_accepted : false;
      if (!accepted || (!paymentCurrency.is_base && !currencyConfig.multi_currency_enabled)) {
        setMessage("This currency is not accepted for the selected payment method.");
        return;
      }
      if (!paymentCurrency.is_base && (
        !paymentCurrency.current_rate_id || !paymentCurrency.current_rate
        || !/^\d+(?:\.\d+)?$/.test(String(paymentCurrency.current_rate))
        || !isCurrencyAmountAtLeast(String(paymentCurrency.current_rate), "0.0000000001", 10)
      )) {
        setMessage("No valid current exchange rate is available for this currency.");
        return;
      }
      if (!paymentCurrency.is_base && !(await isDeviceOnline())) {
        setMessage("Foreign-currency payments are online-only. Reconnect before taking this payment.");
        return;
      }
    }

    if (saleSubmissionInFlightRef.current) {
      return;
    }
    saleSubmissionInFlightRef.current = true;
    setProcessing(true);
    setMessage("");
    setCreditDialogMessage("");

    const completedItems = discounted.items;
    const saleCustomer=paymentMethod==="credit"?(creditCustomer||null):pricingCustomer;
    // Capture the original transaction time before the first submission. It
    // is attached only if this transaction has to be persisted offline.
    // Online requests deliberately omit both offline-only fields so the
    // backend validates them against the cashier's currently open shift.
    const offlineClientCreatedAt = new Date().toISOString();
    let clientSaleId = paymentMethod === "credit"
      ? creditClientSaleIdRef.current || createClientSaleId()
      : createClientSaleId();

    if (paymentMethod === "credit") {
      creditClientSaleIdRef.current = clientSaleId;
    }

    const payload: OfflineSalePayload & { customer_id?: string | null } = {
      client_sale_id: clientSaleId,
      company_id: companyId,
      branch_id: branchId || null,
      employee_id: cashier.id,
      customer_id:
        saleCustomer?.id || null,
      device_id:
        localStorage.getItem("device_id") || null,
      device_key:
        localStorage.getItem("device_key") || null,
      assignment_revision: Number(
        localStorage.getItem("device_assignment_revision") || "1",
      ),
      payment_method: paymentMethod,
      shift_id: currentShift?.id || null,
      discount_amount: discounted.discount_amount,
      sale_discount_amount: discounted.sale_discount_amount,
      items: completedItems.map((item) => ({
        product_id: item.id,
        variant_id:item.variant_id||null,
        quantity: item.quantity,
        selling_unit: item.selling_unit,
        unit_price: item.selling_price,
        line_total: item.line_total,
        line_discount_amount: item.line_discount_amount,
      })),
    };

    if (paymentMethod !== "credit" && paymentCurrency && currencyConfig) {
      payload.payment_currency_code = paymentCurrency.code;
      payload.exchange_rate_id = paymentCurrency.current_rate_id || null;
      payload.currency_config_version = currencyConfig.version;
    }

    let receivedForReceipt = total;
    let tenderedReceiptText: string | null = null;
    let changeReceiptText = "0";

    if (paymentMethod === "cash") {
      const receivedText = String(cashAmount ?? amountReceived).trim();
      const basePlaces = baseCurrency?.decimal_places ?? decimalPlaces;
      const requiredPayment = paymentCurrency ? convertBaseToForeign(
        total.toFixed(basePlaces), basePlaces,
        String(paymentCurrency.current_rate || "1"), paymentCurrency.decimal_places,
      ) : total.toFixed(basePlaces);
      let sufficient = false;
      try {
        sufficient = Boolean(paymentCurrency) && isCurrencyAmountAtLeast(receivedText, requiredPayment, paymentCurrency!.decimal_places);
      } catch {
        sufficient = false;
      }
      if (!sufficient) {
        setMessage(
          "Tendered amount is invalid or less than the amount due",
        );
        setProcessing(false);
        return;
      }
      payload.tendered_amount_original = receivedText;
      if (paymentCurrency?.is_base) payload.amount_received = receivedText;
      receivedForReceipt = paymentCurrency?.is_base ? Number(receivedText) : total;
      tenderedReceiptText = receivedText;
      changeReceiptText = subtractCurrencyAmounts(receivedText, requiredPayment, paymentCurrency!.decimal_places);
    } else if (paymentMethod === "credit") {
      receivedForReceipt = 0;
    }

    if (paymentMethod !== "credit") {
      const fingerprint = JSON.stringify({
        ...payload,
        client_sale_id: null,
      });
      const pendingIdentity = nonCreditSaleIdentityRef.current;
      clientSaleId = pendingIdentity?.fingerprint === fingerprint
        ? pendingIdentity.clientSaleId
        : createClientSaleId();
      nonCreditSaleIdentityRef.current = {
        fingerprint,
        clientSaleId,
      };
      payload.client_sale_id = clientSaleId;
    }

    const completeOfflineSale = async () => {
      if (paymentMethod === "credit") {
        throw new Error("Credit sales are online-only and cannot be queued.");
      }
      if(saleCustomer) throw new Error("Customer price levels require an online connection.");
      if (paymentCurrency && !paymentCurrency.is_base) {
        throw new Error("Foreign-currency payments cannot be queued offline. Reconnect and retry the payment.");
      }
      if (!(await canCreateOfflineSale())) {
        setMessage(
          entitlementVerificationMessage || entitlementSnapshot?.message ||
            "Offline authorization has expired. Reconnect to renew this POS subscription.",
        );
        return;
      }

      // New queues retain the signed original shift identity. Installations
      // with older queued rows remain compatible and are never rewritten.
      const queuedPayload = {
        ...payload,
        offline_shift_token: currentShift?.offline_shift_token || null,
        // A base-currency offline sale remains compatible with the existing
        // queue and is valued from authoritative company settings at sync.
        currency_config_version: undefined,
        exchange_rate_id: undefined,
        client_created_at: offlineClientCreatedAt,
      };
      await queueOfflineSale(queuedPayload);
      nonCreditSaleIdentityRef.current = null;

      const rate = Math.max(0, configuredTaxRate);
      const offlineTaxAmount = productTaxRules
        ? roundMoneyValue(discounted.items.reduce((sum, item) => {
            const itemRate = item.tax_exempt
              ? 0
              : Number(item.tax_rate ?? configuredTaxRate);
            const line = Number(item.line_total);
            if (itemRate <= 0) return sum;
            return sum + (taxInclusive
              ? line * itemRate / (100 + itemRate)
              : line * itemRate / 100);
          }, 0))
        : rate > 0
          ? taxInclusive
            ? total - total / (1 + rate / 100)
            : Math.max(0, total - cartAmount)
          : 0;

      const offlineSubtotal =
        taxInclusive
          ? total - offlineTaxAmount
          : cartAmount;

      setProducts((currentProducts) =>
        currentProducts.map((product) => {
        const soldItem = completedItems.find(
          (item) => item.id === product.id,
        );

          if (!soldItem) {
            return product;
          }

          return {
            ...product,
            stock_qty: subtractQuantities(
              product.stock_qty || "0",
              soldItem.quantity,
            ),
          };
        }),
      );

      const offlineReceipt = {
        id: clientSaleId,
        receipt_number:
          `OFF-${clientSaleId
            .slice(0, 8)
            .toUpperCase()}`,
        subtotal_amount:
          offlineSubtotal.toFixed(2),
        tax_name:
          rate > 0 ? taxName : null,
        tax_rate:
          rate.toFixed(3),
        tax_amount:
          offlineTaxAmount.toFixed(2),
        tax_inclusive: taxInclusive,
        total_amount:
          total.toFixed(2),
        base_currency_code: baseCurrency?.code || businessSettings?.currency_code || null,
        payment_currency_code: baseCurrency?.code || businessSettings?.currency_code || null,
        exchange_rate_snapshot: "1",
        payment_amount_original: total.toFixed(baseCurrency?.decimal_places ?? decimalPlaces),
        tendered_amount_original: tenderedReceiptText,
        change_amount_original: changeReceiptText,
        cashier_name: cashier?.name || null,
        amount_received:
          receivedForReceipt.toFixed(2),
        change_due:
          paymentMethod === "cash"
            ? changeReceiptText
            : "0.00",
        payment_method: paymentMethod,
        discount_amount: payload.discount_amount,
        sale_discount_amount: payload.sale_discount_amount,
        status: "offline_pending",
        created_at:
          new Date().toISOString(),
      } as Receipt;

      setReceipt(offlineReceipt);

      setReceiptItems(completedItems);
      setShowTender(false);
      setCart([]);
      setSaleDiscount("0");
      setAmountReceived("");

      setMessage(
        "Sale completed offline — it will sync automatically when internet returns",
      );

      await archiveAndMaybePrintReceipt(
        buildReceiptSnapshot(
          offlineReceipt,
          completedItems.map((item) => ({
            product_id: item.id,
            name: item.name,
            quantity: item.quantity,
            selling_unit: item.selling_unit,
            unit_price: item.selling_price,
            line_total: item.line_total,
            line_discount_amount: item.line_discount_amount,
          })),
        ),
      );
    };

    const acceptOnlineSale = async (savedReceipt: Receipt) => {
      const completedReceipt = paymentMethod === "credit" && creditCustomer
        ? {
            ...savedReceipt,
            customer_id: savedReceipt.customer_id || creditCustomer.id,
            customer_name_snapshot:
              savedReceipt.customer_name_snapshot || creditCustomer.name,
            customer_code_snapshot:
              savedReceipt.customer_code_snapshot || creditCustomer.customer_code,
            credit_due_date: creditProjection.dueDate,
            credit_outstanding_balance: total.toFixed(2),
          }
        : savedReceipt;

      setReceipt(completedReceipt);
      setReceiptItems(completedItems);
      setShowTender(false);
      setShowCreditSale(false);
      setCart([]);
      setSaleDiscount("0");
      setAmountReceived("");
      setMessage("Sale completed successfully");

      await archiveAndMaybePrintReceipt(
        buildReceiptSnapshot(
          completedReceipt,
          completedItems.map((item) => ({
            product_id: item.id,
            name: item.name,
            quantity: item.quantity,
            selling_unit: item.selling_unit,
            unit_price: item.selling_price,
            line_total: item.line_total,
            line_discount_amount: item.line_discount_amount,
          })),
        ),
      );

      await loadProducts(companyId, branchId || undefined);
      creditClientSaleIdRef.current = null;
      nonCreditSaleIdentityRef.current = null;
    };

    let savedOnlineReceipt: Receipt | null = null;
    try {
      try {
        const response =
          await api.post("/sales", payload);
        savedOnlineReceipt = response.data as Receipt;
      } catch (error: any) {
        /*
         * Only network failures are converted into
         * offline transactions.
         *
         * Validation errors from the backend are NOT
         * queued, because they need to be corrected.
         */
        if (isNetworkFailure(error)) {
          try {
            const reconciliation = await api.get<Receipt>(
              `/sales/by-client-id/${companyId}/${clientSaleId}`,
            );
            await acceptOnlineSale(reconciliation.data);
            return;
          } catch (reconciliationError: any) {
            if (
              reconciliationError?.response?.status !== 404 &&
              !isNetworkFailure(reconciliationError)
            ) {
              throw reconciliationError;
            }
          }
        }

        if (
          paymentMethod !== "credit" &&
          isAndroidNativeApp() &&
          isNetworkFailure(error)
        ) {
          if (!(await canCreateOfflineSale())) {
            throw new Error(
              entitlementVerificationMessage || entitlementSnapshot?.message ||
                "Offline authorization has expired. Reconnect to renew this POS subscription.",
            );
          }
          await completeOfflineSale();
          return;
        }

        if (isNetworkFailure(error)) {
          throw new Error(
            "Sale status could not be confirmed. Reconnect and retry without changing the cart; ApexPOS will reuse the same transaction reference and cannot deduct stock twice.",
          );
        }

        throw error;
      }
      if (savedOnlineReceipt) {
        await acceptOnlineSale(savedOnlineReceipt);
      }
    } catch (error: any) {
      const failureMessage = getApiErrorMessage(error, "Sale failed");
      if (paymentMethod === "credit") {
        setCreditDialogMessage(failureMessage);
      } else {
        setMessage(failureMessage);
      }
    } finally {
      saleSubmissionInFlightRef.current = false;
      setProcessing(false);
    }
  }

  function printReceipt() {
    void handlePrintCurrentReceipt();
  }

  function newSale() {
    setReceipt(null);
    setReceiptItems([]);
    setPaymentMethod("cash");
    setSelectedCreditCustomer(null);
    setCreditCustomers([]);
    setCreditDialogMessage("");
    creditClientSaleIdRef.current = null;
    nonCreditSaleIdentityRef.current = null;
    setMessage("");
    setSearch("");
  }

  function showPosModule(
    moduleName: PosModuleName,
    feature?: string,
  ) {
    setActivePosModule(moduleName);
    const url = new URL(window.location.href);
    url.searchParams.set("module", moduleName);
    if (feature) url.searchParams.set("feature", feature);
    else url.searchParams.delete("feature");
    window.history.pushState(null, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
    if (!window.matchMedia("(min-width: 1024px)").matches) {
      setMenuOpen(false);
    }
    setMessage("");
  }

  function openBackoffice() {
    if (!window.matchMedia("(min-width: 1024px)").matches) {
      setMenuOpen(false);
    }

    window.open(
      "https://backoffice.apexpos.cloud",
      "_blank",
      "noopener,noreferrer",
    );
  }

  function logout() {
    clearAuthenticationPreservingDeviceIdentity();

    setBranchId("");
    setCashier(null);
    setCurrentShift(null);
    setShiftPromptDismissed(false);
    setCashierPin("");
    setPinMessage("");
    setLoggedIn(false);
    setProducts([]);
    setCart([]);
    setSaleDiscount("0");
    setReceipt(null);
    setReceiptItems([]);
    setBusinessSettings(null);
    setCompanyId("");
    setMessage("");
    setShowTender(false);
    setShowCreditSale(false);
    setSelectedCreditCustomer(null);
    setCreditCustomers([]);
    setCreditDialogMessage("");
    creditClientSaleIdRef.current = null;
    nonCreditSaleIdentityRef.current = null;
    setAmountReceived("");
    setAuthMode("login");
  }

  useEffect(() => {
    if (!companyId) {
      setEntitlementSnapshot(null);
      setEntitlementVerificationMessage("");
      setEntitlementRefreshNotice("");
      return;
    }

    let cancelled = false;
    const cached = loadEntitlementSnapshot(companyId);
    setEntitlementRefreshNotice("");
    if (!cached) {
      setEntitlementSnapshot(null);
      setEntitlementVerificationMessage("");
      return;
    }
    void verifyEntitlementSnapshotDetailed(cached).then((verification) => {
      if (cancelled) return;
      if (verification.ok) {
        setEntitlementSnapshot(cached);
        setEntitlementVerificationMessage("");
      } else {
        setEntitlementSnapshot(null);
        setEntitlementVerificationMessage(
          entitlementReconnectMessage(verification.category),
        );
      }
    });

    return () => {
      cancelled = true;
    };
  }, [companyId]);

  useEffect(() => {
    if (!loggedIn || !companyId) return;

    const refreshAfterReconnect = () => {
      void loadSubscriptionSnapshot(companyId).catch((error) => {
        console.warn("[entitlement] refresh after reconnect failed", {
          category: classifyEntitlementRefreshFailure(error).category,
        });
      });
    };
    window.addEventListener("online", refreshAfterReconnect);
    return () => window.removeEventListener("online", refreshAfterReconnect);
  }, [loggedIn, companyId]);

  useEffect(() => {
    if (!loggedIn || !companyId) {
      return;
    }

    let cancelled = false;

    async function synchronizeDevice() {
      try {
        const response =
          await registerCurrentDevice(companyId);

        const device =
          response?.device || response || {};

        const synchronizedBranchId = String(
          device?.branch_id ||
          device?.branch?.id ||
          response?.branch_id ||
          response?.branch?.id ||
          localStorage.getItem("branch_id") ||
          "",
        );

        const synchronizedBranchName = String(
          device?.branch_name ||
          device?.branch?.name ||
          response?.branch_name ||
          response?.branch?.name ||
          localStorage.getItem("branch_name") ||
          "",
        );

        if (!synchronizedBranchId) {
          throw new Error(
            "This POS device has not been assigned to a branch",
          );
        }

        if (cancelled) {
          return;
        }

        localStorage.setItem(
          "branch_id",
          synchronizedBranchId,
        );

        const synchronizedShopId = String(
          device?.shop_id ||
          device?.shop?.id ||
          response?.shop_id ||
          response?.shop?.id ||
          "",
        );

        if (synchronizedShopId) {
          localStorage.setItem("shop_id", synchronizedShopId);
        }

        if (synchronizedBranchName) {
          localStorage.setItem(
            "branch_name",
            synchronizedBranchName,
          );
        }

        if (device?.shop_name) {
          localStorage.setItem(
            "shop_name",
            String(device.shop_name),
          );
        }

        if (device?.friendly_name || device?.name) {
          localStorage.setItem(
            "pos_name",
            String(device.friendly_name || device.name),
          );
        }

        if (device?.pos_number != null) {
          localStorage.setItem(
            "pos_number",
            String(device.pos_number),
          );
        }

        setBranchId(synchronizedBranchId);

        await loadProducts(
          companyId,
          synchronizedBranchId,
        );

        await loadBusinessSettings(companyId);
        await loadSubscriptionSnapshot(companyId);

        if (!cancelled) {
          setMessage("");
        }
      } catch (error: any) {
        if (!cancelled) {
          setMessage(
            getApiErrorMessage(
              error,
              "POS device synchronization failed",
            ),
          );
        }
      }
    }

    void synchronizeDevice();

    return () => {
      cancelled = true;
    };
  }, [loggedIn, companyId]);

  useEffect(() => {
    if (!cashier || !companyId) {
      setCurrentShift(null);
      setShiftLoading(false);
      return;
    }
    let cancelled = false;
    const deviceId = localStorage.getItem("device_id") || "unknown";
    const cacheKey = `apex_shift_${companyId}_${cashier.id}_${deviceId}`;
    async function loadShift() {
      setShiftLoading(true);
      setShiftPromptDismissed(false);
      try {
        if (!(await isDeviceOnline())) {
          const cached = localStorage.getItem(cacheKey);
          const parsed = cached ? JSON.parse(cached) as (ShiftRecord & { offline_shift_token?: string | null }) : null;
          if (!cancelled) setCurrentShift(parsed?.status === "open" ? parsed : null);
          return;
        }
        const response = await api.get("/shifts/current");
        if (!cancelled) {
          const loaded = response.data as (ShiftRecord & { offline_shift_token?: string | null }) | null;
          setCurrentShift(loaded);
          if (loaded) localStorage.setItem(cacheKey, JSON.stringify(loaded));
          else localStorage.removeItem(cacheKey);
        }
      } catch (error) {
        if (!cancelled) {
          setCurrentShift(null);
          setMessage(getApiErrorMessage(error, "Unable to check the current shift"));
        }
      } finally {
        if (!cancelled) setShiftLoading(false);
      }
    }
    void loadShift();
    return () => { cancelled = true; };
  }, [cashier, companyId]);

  useEffect(() => {
    if (!loggedIn || !companyId) {
      return;
    }

    async function sendHeartbeat() {
      try {
        await api.post("/devices/heartbeat", {
          company_id: companyId,
          device_id:
            localStorage.getItem("device_id") || null,
          device_key:
            localStorage.getItem("device_key") || null,
          platform: "web",
          app_version: "1.0.0",
        });
      } catch (error) {
        console.debug("Device heartbeat failed", error);
      }
    }

    void sendHeartbeat();
    const intervalId = window.setInterval(() => {
      void sendHeartbeat();
    }, 60000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [loggedIn, companyId]);

  if (!loggedIn) {
    return (
      <div style={pageCenter} className="pos-auth-page">
        <div
          className={`pos-auth-card ${authMode === "register" ? "pos-auth-card-wide" : ""}`}
          style={{
            ...loginCard,
            width: authMode === "register" ? 760 : 430,
          }}
        >
          <div className="pos-auth-logo" aria-hidden="true">A</div>
          <h1 style={brand} className="pos-auth-title">ApexRetail POS</h1>

          <p
            style={{
              textAlign: "center",
              color: "#667085",
              marginBottom: 22,
            }}
          >
            Sign in to your business or register a new one.
          </p>

          <div
            className="pos-auth-tabs"
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 8,
              marginBottom: 20,
            }}
          >
            <button
              type="button"
              style={
                authMode === "login"
                  ? activePaymentButton
                  : secondaryButton
              }
              onClick={() => {
                setAuthMode("login");
                setMessage("");
              }}
            >
              Sign in
            </button>

            <button
              type="button"
              style={
                authMode === "register"
                  ? activePaymentButton
                  : secondaryButton
              }
              onClick={() => {
                setAuthMode("register");
                setMessage("");
              }}
            >
              Register business
            </button>
          </div>

          {authMode === "login" ? (
            <>
              <label style={modalLabel}>
                Email address
                <input
                  style={input}
                  type="email"
                  autoComplete="email"
                  value={email}
                  placeholder="owner@business.com"
                  onChange={(event) =>
                    setEmail(event.target.value)
                  }
                />
              </label>

              <label style={modalLabel}>
                Password
                <span style={{ display: "flex", gap: 8 }}>
                  <input
                    style={{ ...input, flex: 1 }}
                    type={passwordVisible ? "text" : "password"}
                    autoComplete="current-password"
                    value={password}
                    placeholder="Password"
                    onChange={(event) => setPassword(event.target.value)}
                  />
                  <button type="button" aria-label={passwordVisible ? "Hide password" : "Show password"} onClick={() => setPasswordVisible((value) => !value)}>{passwordVisible ? "Hide" : "Show"}</button>
                </span>
              </label>

              <button
                type="button"
                style={primaryButton}
                disabled={authLoading}
                onClick={() => void login()}
              >
                {authLoading
                  ? "Signing in..."
                  : "Sign in"}
              </button>
            </>
          ) : (
            <>
              <div
                className="pos-auth-form-grid"
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fit, minmax(220px, 1fr))",
                  columnGap: 16,
                }}
              >
                <label style={modalLabel}>
                  Owner name
                  <input
                    style={input}
                    value={ownerName}
                    placeholder="Full name"
                    onChange={(event) =>
                      setOwnerName(event.target.value)
                    }
                  />
                </label>

                <label style={modalLabel}>
                  Owner PIN
                  <input
                    style={input}
                    value={ownerPin}
                    inputMode="numeric"
                    maxLength={4}
                    placeholder="4-digit PIN"
                    onChange={(event) =>
                      setOwnerPin(
                        event.target.value
                          .replace(/\D/g, "")
                          .slice(0, 4),
                      )
                    }
                  />
                </label>

                <label style={modalLabel}>
                  Business name
                  <input
                    style={input}
                    value={businessName}
                    placeholder="Business name"
                    onChange={(event) =>
                      setBusinessName(event.target.value)
                    }
                  />
                </label>

                <label style={modalLabel}>
                  Business type
                  <select
                    style={input}
                    value={businessType}
                    onChange={(event) =>
                      setBusinessType(event.target.value)
                    }
                  >
                    <option value="Retail">Retail</option>
                    <option value="Restaurant">
                      Restaurant
                    </option>
                    <option value="Wholesale">
                      Wholesale
                    </option>
                    <option value="Pharmacy">
                      Pharmacy
                    </option>
                    <option value="Services">
                      Services
                    </option>
                    <option value="Other">Other</option>
                  </select>
                </label>

                <label style={modalLabel}>
                  Country
                  <input
                    style={input}
                    value={country}
                    placeholder="Country"
                    onChange={(event) =>
                      setCountry(event.target.value)
                    }
                  />
                </label>

                <label style={modalLabel}>
                  Phone number
                  <input
                    style={input}
                    value={phone}
                    placeholder="Phone number"
                    onChange={(event) =>
                      setPhone(event.target.value)
                    }
                  />
                </label>

                <label style={modalLabel}>
                  Base currency
                  <select
                    style={input}
                    value={baseCurrencyCode}
                    disabled={registrationCurrenciesLoading}
                    onChange={(event) => setBaseCurrencyCode(event.target.value)}
                  >
                    <option value="">
                      {registrationCurrenciesLoading
                        ? "Loading currencies..."
                        : "Select base currency"}
                    </option>
                    {registrationCurrencies.map((currency) => (
                      <option key={currency.code} value={currency.code}>
                        {currency.code} — {currency.display_name} ({currency.symbol}, {currency.decimal_places} decimals)
                      </option>
                    ))}
                  </select>
                  <span style={{ display: "block", marginTop: 7, fontSize: 12, fontWeight: 500 }}>
                    This is your accounting currency and cannot be changed after financial activity begins.
                  </span>
                </label>

                <label style={modalLabel}>
                  Email address
                  <input
                    style={input}
                    type="email"
                    autoComplete="email"
                    value={email}
                    placeholder="owner@business.com"
                    onChange={(event) =>
                      setEmail(event.target.value)
                    }
                  />
                </label>

                <label style={modalLabel}>
                  Password
                  <input
                    style={input}
                    type="password"
                    autoComplete="new-password"
                    value={password}
                    placeholder="At least 8 characters"
                    onChange={(event) =>
                      setPassword(event.target.value)
                    }
                  />
                </label>

                <label style={modalLabel}>
                  Confirm password
                  <input
                    style={input}
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    placeholder="Repeat password"
                    onChange={(event) =>
                      setConfirmPassword(
                        event.target.value,
                      )
                    }
                  />
                </label>
              </div>

              {registrationCurrenciesError && (
                <p style={errorText}>{registrationCurrenciesError}</p>
              )}

              <button
                type="button"
                style={primaryButton}
                disabled={authLoading || registrationCurrenciesLoading || Boolean(registrationCurrenciesError)}
                onClick={() => void registerBusiness()}
              >
                {authLoading
                  ? "Creating business..."
                  : "Create business and open POS"}
              </button>
            </>
          )}

          {message && (
            <p style={errorText}>{message}</p>
          )}

          <p
            style={{
              textAlign: "center",
              color: "#667085",
              fontSize: 13,
              marginTop: 18,
              marginBottom: 0,
            }}
          >
            The same email and password are used for
            Backoffice.
          </p>
        </div>
      </div>
    );
  }

  if (loggedIn && !branchId) {
    return (
      <div style={pageCenter} className="pos-auth-page">
        <div style={loginCard} className="pos-auth-card">
          <div className="pos-auth-logo" aria-hidden="true">A</div>
          <h1 style={brand} className="pos-auth-title">Preparing POS</h1>

          <p style={{ textAlign: "center" }}>
            Synchronizing this device with its assigned branch.
          </p>

          {message && (
            <p style={{ textAlign: "center", color: "#b42318" }}>
              {message}
            </p>
          )}

          <button
            type="button"
            style={secondaryButton}
            onClick={logout}
          >
            Full Logout
          </button>
        </div>
      </div>
    );
  }

  if (loggedIn && !cashier) {
    if (pinSelection) {
      const terminals = pinSelection.terminals.filter((item) => !selectedShopId || item.shop_id === selectedShopId);
      return (
        <div style={pageCenter} className="pos-auth-page"><div style={loginCard} className="pos-auth-card">
          <div className="pos-auth-logo" aria-hidden="true">A</div>
          <h1 style={brand} className="pos-auth-title">Choose POS location</h1>
          <p>Select an authorised shop and available terminal. New sign-in requires an internet connection.</p>
          {!pinSelection.shops.length ? <p style={errorText}>No authorised shops are available.</p> : <>
            <label style={modalLabel}>Shop<select style={input} value={selectedShopId} onChange={(e) => { setSelectedShopId(e.target.value); setSelectedTerminalId(""); }}><option value="">Select shop</option>{pinSelection.shops.map((shop) => <option key={shop.id} value={shop.id}>{shop.name}</option>)}</select></label>
            <label style={modalLabel}>Terminal<select style={input} value={selectedTerminalId} onChange={(e) => setSelectedTerminalId(e.target.value)}><option value="">Select terminal</option>{terminals.map((terminal) => <option key={terminal.id} value={terminal.id}>{terminal.name}{terminal.pos_number ? ` (#${terminal.pos_number})` : ""}</option>)}</select></label>
            {!terminals.length && selectedShopId && <p style={errorText}>No available active terminals in this shop.</p>}
            <button type="button" style={primaryButton} disabled={!selectedShopId || !selectedTerminalId || pinLoading} onClick={() => void loginWithEmployeePin({shop_id: selectedShopId, device_id: selectedTerminalId})}>{pinLoading ? "Signing in..." : "Enter POS"}</button>
            <button type="button" style={secondaryButton} onClick={() => { setPinSelection(null); setSelectedShopId(""); setSelectedTerminalId(""); }}>Cancel</button>
            {takeoverPrompt && <div role="alert" style={{ marginTop: 12, border: "1px solid #f59e0b", padding: 12 }}><p>You are already signed in elsewhere. Taking over will immediately sign out that device.</p><button type="button" style={secondaryButton} onClick={() => { setTakeoverPrompt(false); setTakeoverSelection(null); }}>Cancel</button><button type="button" style={primaryButton} onClick={() => { setTakeoverPrompt(false); void loginWithEmployeePin({ shop_id: selectedShopId, device_id: selectedTerminalId, takeover: true }); }}>Take over this session</button></div>}
          </>}
          {pinMessage && <p style={errorText}>{pinMessage}</p>}
        </div></div>
      );
    }
    return (
      <div style={pageCenter} className="pos-auth-page">
        <div style={loginCard} className="pos-auth-card pos-pin-card">
          <div className="pos-auth-logo pos-auth-logo-pin" aria-hidden="true">••••</div>
          <h1 style={brand} className="pos-auth-title">Cashier Sign In</h1>

          <p style={{ textAlign: "center" }}>
            Enter your four-digit employee PIN
          </p>

          <p
            style={{
              textAlign: "center",
              margin: "6px 0 18px",
              color: "#667085",
            }}
          >
            {localStorage.getItem("branch_name") ||
              "Assigned branch"}
          </p>

          <input
            className="pos-pin-input"
            style={{
              ...input,
              textAlign: "center",
              fontSize: 28,
              letterSpacing: 12,
            }}
            type="password"
            inputMode="numeric"
            autoFocus
            maxLength={4}
            value={cashierPin}
            placeholder="••••"
            onChange={(event) =>
              setCashierPin(
                event.target.value
                  .replace(/\D/g, "")
                  .slice(0, 4),
              )
            }
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void loginWithEmployeePin();
              }
            }}
          />

          <button
            type="button"
            style={primaryButton}
            disabled={pinLoading}
            onClick={() => void loginWithEmployeePin()}
          >
            {pinLoading ? "Signing in..." : "Open POS"}
          </button>

          {pinMessage && (
            <p
              style={{
                textAlign: "center",
                color: "#b42318",
                fontWeight: 700,
              }}
            >
              {pinMessage}
            </p>
          )}
          {takeoverPrompt && <div role="alert" style={{ marginTop: 12, border: "1px solid #f59e0b", padding: 12 }}><p>You are already signed in elsewhere. Taking over will immediately sign out that device.</p><button type="button" style={secondaryButton} onClick={() => { setTakeoverPrompt(false); setTakeoverSelection(null); }}>Cancel</button>{takeoverSelection ? <button type="button" style={primaryButton} onClick={() => { const target = takeoverSelection; setTakeoverPrompt(false); void loginWithEmployeePin({ ...target, takeover: true }); }}>Take over this session</button> : null}</div>}

          <button
            type="button"
            style={secondaryButton}
            onClick={logout}
          >
            Use Email Login
          </button>
        </div>
      </div>
    );
  }

  if (cashier && activePosModule === "Sales" && !shiftPromptDismissed && (shiftLoading || !currentShift)) {
    if (shiftLoading) {
      return <main className="pos-shift-page"><section className="pos-shift-panel"><p>Checking the current cashier shift…</p></section></main>;
    }
    return <ShiftManagementPage
      companyId={companyId}
      branchId={branchId}
      cashier={cashier}
      onBackToSales={() => {
        if (!businessSettings?.shift_enforcement_enabled) setShiftPromptDismissed(true);
      }}
      onPrintShiftSummary={handlePrintShiftSummary}
      onPrintZReport={handlePrintZReport}
      onShiftChanged={(shift) => {
        setCurrentShift(shift);
        const deviceId = localStorage.getItem("device_id") || "unknown";
        const cacheKey = `apex_shift_${companyId}_${cashier.id}_${deviceId}`;
        if (shift) localStorage.setItem(cacheKey, JSON.stringify(shift));
        else localStorage.removeItem(cacheKey);
      }}
    />;
  }

  const canManageProducts =
    cashier?.role === "owner" ||
    Boolean(cashier?.permissions?.manage_products);
  const canManageInventory =
    cashier?.role === "owner" ||
    Boolean(cashier?.permissions?.manage_inventory);

  return (
    <div style={appShell} className={`pos-sales-shell ${menuOpen ? "pos-navigation-open" : ""}`}>
      <PosNavigation
        open={menuOpen}
        activeModule={activePosModule}
        cashierName={cashier?.name || "Cashier"}
        cashierRole={cashier?.role || "employee"}
        canManageProducts={canManageProducts}
        canManageInventory={canManageInventory}
        canManageExpenses={Boolean(cashier?.role === "owner" || cashier?.role === "administrator" || cashier?.permissions?.expenses_create)}
        canManageCredit={Boolean(cashier?.role === "owner" || cashier?.role === "administrator" || cashier?.permissions?.credit_settlements)}
        onToggle={() => setMenuOpen((current) => !current)}
        onClose={() => setMenuOpen(false)}
        onNavigate={showPosModule}
        onBackoffice={openBackoffice}
        onLogout={logout}
      />

      {activePosModule !== "Sales" && (
        <PosModulePage
          activeModule={activePosModule}
          companyId={companyId}
          branchId={branchId}
          cashier={cashier}
          shiftStatus={currentShift?.status || "closed"}
          currencySymbol={currencySymbol}
          decimalPlaces={decimalPlaces}
          printerConfig={printerConfig}
          printerConfigLoaded={printerConfigLoaded}
          bluetoothStatus={bluetoothStatus}
          bluetoothPrinters={bluetoothPrinterDevices}
          usbPrinters={usbPrinterDevices}
          isDiscoveringDevices={isDiscoveringDevices}
          isSavingPrinter={isSavingPrinter}
          isTestingPrinter={isTestingPrinter}
          printerNotice={printerNotice}
          printerDiscoveryError={printerDiscoveryError}
          printerSaveError={printerSaveError}
          printerTestError={printerTestError}
          bluetoothPermissionDenied={bluetoothPermissionDenied}
          printerRefreshSignal={printerRefreshSignal}
          onSavePrinterConfig={persistPrinterConfig}
          onRefreshPrinterDevices={refreshPrinterDevices}
          onOpenBluetoothSettings={handleOpenBluetoothSettings}
          onOpenAppSettings={handleOpenAppSettings}
          onOpenPrintSettings={handleOpenPrintSettings}
          onTestPrint={handleTestPrint}
          onReprintSale={handleReprintSale}
          onPrintShiftSummary={handlePrintShiftSummary}
          onPrintZReport={handlePrintZReport}
          onShiftChanged={(shift) => {
            setCurrentShift(shift);
            const deviceId = localStorage.getItem("device_id") || "unknown";
            const cacheKey = `apex_shift_${companyId}_${cashier?.id || "unknown"}_${deviceId}`;
            if (shift) localStorage.setItem(cacheKey, JSON.stringify(shift));
            else {
              localStorage.removeItem(cacheKey);
              setShiftPromptDismissed(false);
            }
          }}
          onProductsChanged={() =>
            void loadProducts(
              companyId,
              branchId || undefined,
            )
          }
          onBackToSales={() => {
            showPosModule("Sales");
          }}
        />
      )}

      <main style={mainArea} className="pos-sales-main">
        <PosSessionHeader
          eyebrow="Checkout"
          title="Sales"
          cashierName={cashier?.name || "Employee"}
          shopName={localStorage.getItem("shop_name") || "Current shop"}
          branchName={localStorage.getItem("branch_name") || "Assigned branch"}
          shiftStatus={currentShift?.status || "closed"}
          actions={<>
            <button className="pos-topbar-action" type="button" onClick={switchCashier}>
              <UsersIcon aria-hidden="true" /> Switch cashier
            </button>
            <button className="pos-topbar-action" type="button" onClick={logout}>
              <ArrowRightStartOnRectangleIcon aria-hidden="true" /> Log out
            </button>
          </>}
        />

        {entitlementSnapshot && !entitlementSnapshot.writes_allowed && (
          <div className="subscription-banner subscription-banner-error" role="alert">
            Subscription: {entitlementSnapshot.status.replace(/_/g, " ")}
          </div>
        )}
        {entitlementVerificationMessage && (
          <div className="subscription-banner subscription-banner-error" role="alert">{entitlementVerificationMessage}</div>
        )}
        {entitlementRefreshNotice && (
          <div className="subscription-banner" role="status">{entitlementRefreshNotice}</div>
        )}

        {quarantinedSales.length > 0 && (
          <section
            role="alert"
            aria-label="Quarantined offline sales"
            style={{
              border: "2px solid #b42318",
              background: "#fff1f0",
              borderRadius: 12,
              padding: 16,
              marginBottom: 18,
            }}
          >
            <h2 style={{ margin: "0 0 8px", fontSize: 20 }}>
              Offline sales need operator recovery
            </h2>
            <p style={{ margin: "0 0 10px" }}>
              {quarantinedSales.length} unsynchronized sale{quarantinedSales.length === 1 ? "" : "s"}{" "}
              were rejected because this terminal was deleted, decommissioned, or reassigned.
              They are preserved on this device and will not retry automatically.
            </p>
            <ul>
              {quarantinedSales.map((sale) => (
                <li key={sale.client_sale_id}>
                  <code>{sale.client_sale_id}</code>: {sale.last_error}
                </li>
              ))}
            </ul>
            <button
              type="button"
              style={secondaryButton}
              onClick={() => void exportOfflineQuarantine()}
            >
              Export recovery file
            </button>
          </section>
        )}

        <div className="pos-sales-search-row">
          <input
            className="pos-sales-search"
            style={searchBox}
            placeholder="Search product by name, SKU or barcode..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={handleSalesSearchKeyDown}
          />
          <button
            type="button"
            className="pos-scan-barcode-button"
            onClick={() => setSalesScannerOpen(true)}
          >
            <QrCodeIcon aria-hidden="true" /> Scan Barcode
          </button>
        </div>

        <div style={productGrid} className="pos-sales-product-grid">
          {filteredProducts.map((product) => (
            <button
              key={product.id}
              onClick={() => addToCart(product)}
              style={productCard}
              className="pos-product-card"
              disabled={Number(product.stock_qty) <= 0}
            >
              <span className="pos-product-visual" aria-hidden="true">
                {product.name.trim().slice(0, 2).toUpperCase() || "AP"}
              </span>
              <h3>{product.name}</h3>
              <p>SKU: {product.sku || "-"}</p>
              <p>
                Stock: {formatQuantity(product.stock_qty, product.unit)}
              </p>
              <h2>
                {formatMoney(product.selling_price)}
                {product.unit && product.unit !== "each"
                  ? `/${product.unit}`
                  : ""}
              </h2>
            </button>
          ))}
        </div>

        {!filteredProducts.length && (
          <p>No matching products found.</p>
        )}
      </main>

      <aside style={cartPanel} className="pos-sales-cart">
        <h2 style={{ marginTop: 0 }}>Current Sale</h2>
        <label className="pos-pricing-customer">Customer pricing<select value={pricingCustomer?.id||""} onFocus={()=>{if(!creditCustomers.length)void loadCreditCustomers("")}} onChange={event=>choosePricingCustomer(event.target.value)}><option value="">Retail / standard</option>{creditCustomers.map(customer=><option key={customer.id} value={customer.id}>{customer.name}{customer.price_level_name?` — ${customer.price_level_name}`:""}</option>)}</select></label>

        <div style={cartItemsArea}>
          {!cart.length && (
            <p style={{ color: "#6b7280" }}>
              Select a product to begin.
            </p>
          )}

          {cart.map((item, cartIndex) => (
            <div key={item.cart_key} style={cartRow} className="pos-cart-row">
              <div className="pos-cart-item-summary">
                <strong>{item.name}</strong>
                {item.variant_name&&<small>{item.variant_name}</small>}
                <p style={{ margin: "5px 0 0" }}>
                  {formatQuantity(
                    item.quantity,
                    item.selling_unit,
                  )}{" "}
                  x {formatMoney(item.selling_price)}
                  {item.selling_unit !== "each"
                    ? `/${item.selling_unit}`
                    : ""}
                </p>
                <p style={{ margin: "5px 0 0", fontWeight: 700 }}>
                  Item total: {formatMoney(discounted.items[cartIndex]?.line_total || item.line_total)}
                </p>
              </div>

              <div style={quantityBox} className="pos-quantity-control" aria-label={`Quantity for ${item.name}`}>
                <button
                  style={quantityButton}
                  onClick={() => changeQty(item.cart_key, -1)}
                  disabled={item.selling_unit !== "each"}
                >
                  −
                </button>

                <strong>
                  {formatQuantity(
                    item.quantity,
                    item.selling_unit,
                  )}
                </strong>

                <button
                  style={quantityButton}
                  onClick={() => changeQty(item.cart_key, 1)}
                  disabled={item.selling_unit !== "each"}
                >
                  +
                </button>
              </div>

              <button
                style={removeButton}
                className="pos-remove-item"
                aria-label={`Remove ${item.name}`}
                onClick={() => removeFromCart(item.cart_key)}
              >
                ×
              </button>
            </div>
          ))}
        </div>

        {cashier?.permissions?.discounts && <label className="pos-whole-sale-discount-field"><span>Sale discount</span>
          <input aria-label="Sale discount" inputMode="decimal" value={saleDiscount} disabled={processing}
            onChange={(event) => setSaleDiscount(event.target.value)} />
        </label>}
        {discountError && <p role="alert">{discountError}</p>}
        {Number(discounted.sale_discount_amount) > 0 && (
          <p className="pos-discount-applied">Sale discount applied: −{formatMoney(discounted.sale_discount_amount)}</p>
        )}
        <div data-tax-summary="true"
          style={{
            marginTop: 22,
            marginBottom: 20,
            display: "grid",
            gap: 9,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 18,
            }}
          >
            <span>{Number(discounted.discount_amount) > 0 ? "Subtotal after discounts" : "Subtotal"}</span>
            <strong>{formatMoney(subtotal)}</strong>
          </div>

          {configuredTaxRate > 0 && (
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 18,
              }}
            >
              <span>
                {taxName} ({configuredTaxRate}%)
                {taxInclusive ? " included" : ""}
              </span>
              <strong>{formatMoney(taxAmount)}</strong>
            </div>
          )}

          <h1
            style={{
              fontSize: 42,
              margin: "10px 0 0",
              display: "flex",
              justifyContent: "space-between",
            }}
          >
            <span>Total:</span>
            <span>{formatMoney(total)}</span>
          </h1>
        </div>

        <div style={paymentGrid} className="pos-payment-grid">
          {enabledPaymentMethods.map((method) => (
            <button
              key={method}
              onClick={() => setPaymentMethod(method)}
              style={
                paymentMethod === method
                  ? activePaymentButton
                  : secondaryButton
              }
            >
              {method.toUpperCase()}
            </button>
          ))}
        </div>

        <button
          style={primaryButton}
          onClick={() => void startPayment()}
          disabled={processing || !cart.length}
        >
          {processing ? "Processing..." : "Complete Sale"}
        </button>

        <button
          style={secondaryButton}
          onClick={() => setCart([])}
          disabled={!cart.length}
        >
          Clear Cart
        </button>

        <p style={messageText}>{message}</p>
      </aside>

      {salesScannerOpen && (
        <BarcodeScannerDialog
          title="Scan product barcode"
          onScan={handleSalesBarcode}
          onClose={() => setSalesScannerOpen(false)}
        />
      )}

      {showCreditSale && (
        <div style={overlay} className="pos-credit-overlay">
          <div style={modalCard} className="pos-credit-dialog" role="dialog" aria-modal="true" aria-labelledby="credit-sale-title">
            <h2 id="credit-sale-title" style={{ marginTop: 0 }}>Credit Sale</h2>
            <p className="pos-credit-online-notice">Online validation is required before this sale can be posted.</p>

            <form
              className="pos-credit-search"
              onSubmit={(event) => {
                event.preventDefault();
                void loadCreditCustomers();
              }}
            >
              <label htmlFor="credit-customer-search">Search active customers</label>
              <div>
                <input
                  id="credit-customer-search"
                  value={creditCustomerSearch}
                  placeholder="Name, phone or customer code"
                  onChange={(event) => setCreditCustomerSearch(event.target.value)}
                />
                <button type="submit" style={secondaryButton} disabled={creditCustomersLoading}>
                  {creditCustomersLoading ? "Searching..." : "Search"}
                </button>
              </div>
            </form>

            <div className="pos-credit-customer-list" aria-label="Active customers">
              {!creditCustomersLoading && !creditCustomers.length && (
                <p>No active customers found.</p>
              )}
              {creditCustomers.map((customer) => (
                <button
                  type="button"
                  key={customer.id}
                  className={selectedCreditCustomer?.id === customer.id ? "selected" : ""}
                  onClick={() => {
                    setSelectedCreditCustomer(customer);
                    setCreditDialogMessage("");
                  }}
                >
                  <strong>{customer.name}</strong>
                  <span>{customer.customer_code}</span>
                  <small>
                    Balance {formatMoney(customer.outstanding_balance)} · {customer.credit_enabled ? "Credit enabled" : "Credit disabled"}
                  </small>
                </button>
              ))}
            </div>

            <section className="pos-credit-summary" aria-label="Credit sale summary">
              <div><span>Customer</span><strong>{selectedCreditCustomer ? `${selectedCreditCustomer.name} (${selectedCreditCustomer.customer_code})` : "Not selected"}</strong></div>
              <div><span>Credit status</span><strong>{selectedCreditCustomer?.credit_enabled ? "Enabled" : "Disabled"}</strong></div>
              <div><span>Current outstanding</span><strong>{formatMoney(creditProjection.outstandingBalance)}</strong></div>
              <div><span>Credit limit</span><strong>{selectedCreditCustomer?.unlimited_credit ? "Explicit unlimited credit" : selectedCreditCustomer?.credit_limit != null ? formatMoney(selectedCreditCustomer.credit_limit) : "Not configured"}</strong></div>
              <div><span>Available credit</span><strong>{selectedCreditCustomer?.unlimited_credit ? "Unlimited" : creditProjection.availableCredit == null ? "Not available" : formatMoney(creditProjection.availableCredit)}</strong></div>
              <div><span>Sale total</span><strong>{formatMoney(total)}</strong></div>
              <div><span>Projected balance</span><strong>{formatMoney(creditProjection.projectedBalance)}</strong></div>
              <div><span>Credit terms</span><strong>{selectedCreditCustomer ? `${selectedCreditCustomer.credit_terms_days} days` : "—"}</strong></div>
              <div><span>Due date</span><strong>{creditProjection.dueDate || "—"}</strong></div>
            </section>

            {(creditProjection.error || creditDialogMessage) && (
              <p role="alert" className="pos-credit-error">
                {creditDialogMessage || creditProjection.error}
              </p>
            )}

            <div className="pos-credit-actions">
              <button
                type="button"
                style={primaryButton}
                disabled={processing || Boolean(creditProjection.error)}
                onClick={() => void submitSale(undefined, selectedCreditCustomer || undefined)}
              >
                {processing ? "Posting credit sale..." : "Confirm Credit Sale"}
              </button>
              <button type="button" style={secondaryButton} disabled={processing} onClick={closeCreditSaleDialog}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {showTender && (
        <div style={overlay}>
          <div style={modalCard} className="pos-payment-dialog" role="dialog" aria-modal="true" aria-labelledby="pos-payment-title">
            <h2 style={{ marginTop: 0 }} id="pos-payment-title">{paymentMethod.toUpperCase()} Payment</h2>
            <p style={modalLabel}>Base currency: {basePosCurrency?.code || currencyConfig?.base_currency_code || "Unavailable"}</p>
            <label style={modalLabel} htmlFor="payment-currency">Payment currency</label>
            <select
              id="payment-currency"
              value={selectedPaymentCurrencyCode}
              style={tenderInput}
              onChange={(event) => {
                const nextCode = event.target.value;
                const next = acceptedPaymentCurrencies.find((currency) => currency.code === nextCode);
                if (!next || !basePosCurrency) return;
                setSelectedPaymentCurrencyCode(next.code);
                setCurrencyQuoteError("");
                try {
                  setAmountReceived(paymentMethod === "cash" ? convertBaseToForeign(
                    total.toFixed(basePosCurrency.decimal_places), basePosCurrency.decimal_places,
                    String(next.current_rate ?? "1"), next.decimal_places,
                  ) : "");
                } catch (error) {
                  setCurrencyQuoteError(error instanceof Error ? error.message : "Invalid exchange rate");
                }
              }}
            >
              {acceptedPaymentCurrencies.map((currency) => (
                <option key={currency.code} value={currency.code}>
                  {currency.code} — {currency.display_name}
                </option>
              ))}
            </select>

            {activePaymentCurrency && basePosCurrency && (
              <section className="pos-payment-conversion" aria-label="Payment conversion" style={{ ...changeBox, display: "grid", gap: 8, textAlign: "left" }}>
                <div>Amount due: {currencySymbol}{total.toFixed(basePosCurrency.decimal_places)} {basePosCurrency.code}</div>
                {!activePaymentCurrency.is_base && (
                  <div>Rate: 1 {basePosCurrency.code} = {activePaymentCurrency.current_rate || "Unavailable"} {activePaymentCurrency.code}</div>
                )}
                <strong>Pay: {activePaymentCurrency.symbol}{paymentDueText || "Rate unavailable"} {activePaymentCurrency.code}</strong>
                {activePaymentCurrency.rate_effective_at && !activePaymentCurrency.is_base && (
                  <small>Rate effective {new Date(activePaymentCurrency.rate_effective_at).toLocaleString()}</small>
                )}
              </section>
            )}

            {paymentMethod === "cash" ? (
              <>
                <label style={modalLabel} htmlFor="payment-tendered">Amount tendered ({activePaymentCurrency?.code || ""})</label>
                <input
                  autoFocus
                  id="payment-tendered"
                  type="text"
                  inputMode="decimal"
                  value={amountReceived}
                  style={tenderInput}
                  onChange={(event) => setAmountReceived(event.target.value)}
                  onKeyDown={(event) => { if (event.key === "Enter") void submitSale(amountReceived); }}
                />
                <button
                  className="pos-exact-payment-button"
                  style={secondaryButton}
                  onClick={() => setAmountReceived(paymentDueText)}
                  disabled={!paymentDueText}
                >Exact amount</button>
                <div style={changeBox} className="pos-payment-change">
                  <span>Change due ({activePaymentCurrency?.code || ""})</span>
                  <strong>{activePaymentCurrency?.symbol}{paymentChangeText || "—"}</strong>
                </div>
              </>
            ) : (
              <p style={modalLabel}>Charge exactly {activePaymentCurrency?.symbol}{paymentDueText} {activePaymentCurrency?.code} using the selected terminal/provider.</p>
            )}

            {currencyQuoteError && <p role="alert" style={errorText}>{currencyQuoteError}</p>}

            <button
              className="pos-confirm-payment"
              style={primaryButton}
              disabled={processing || !activePaymentCurrency || !paymentDueText || Boolean(currencyQuoteError)}
              onClick={() => void submitSale(paymentMethod === "cash" ? amountReceived : undefined)}
            >
              {processing ? "Processing..." : "Confirm Payment"}
            </button>

            <button
              className="pos-cancel-payment"
              style={secondaryButton}
              onClick={() => {
                setShowTender(false);
                setAmountReceived("");
              }}
            >
              Cancel
            </button>

            <p style={errorText}>{message}</p>
          </div>
        </div>
      )}

      {variantProduct&&<div style={overlay}><div style={modalCard} className="pos-variant-dialog" role="dialog"><h2>Choose {variantProduct.name}</h2><div className="pos-variant-options">{variantProduct.variants?.map(variant=><button key={variant.id} disabled={Number(variant.stock_qty)<=0} onClick={()=>addVariant(variantProduct,variant)}><strong>{variant.name}</strong><span>{formatMoney(variant.selling_price??variantProduct.selling_price)} · {variant.stock_qty} available</span></button>)}</div><button style={secondaryButton} onClick={()=>setVariantProduct(null)}>Cancel</button></div></div>}

      {weightedProduct && (
        <div style={overlay}>
          <div style={modalCard}>
            <h2 style={{ marginTop: 0 }}>{weightedProduct.name}</h2>
            <p style={{ color: "#667085", marginTop: 0 }}>
              Unit price: {formatMoney(weightedProduct.selling_price)}
              /{weightedProduct.unit}
            </p>

            <label style={modalLabel}>
              {["kg", "litre"].includes(
                weightedProduct.unit || "",
              )
                ? weightedProduct.unit === "litre"
                  ? "Volume (litre)"
                  : "Weight (kg)"
                : "Quantity"}
            </label>
            <input
              autoFocus
              type="number"
              min="0.001"
              step="0.001"
              value={weightedQuantity}
              style={tenderInput}
              onChange={(event) => {
                const nextQuantity = event.target.value;
                setWeightedQuantity(nextQuantity);
                setWeightedAmount(
                  multiplyPriceByQuantity(
                    weightedProduct.selling_price,
                    nextQuantity || "0",
                  ),
                );
              }}
            />

            {["kg", "litre"].includes(
              weightedProduct.unit || "",
            ) && (
              <>
                <label style={modalLabel}>Required value</label>
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={weightedAmount}
                  style={tenderInput}
                  onChange={(event) => {
                    const nextAmount = event.target.value;
                    setWeightedAmount(nextAmount);
                    setWeightedQuantity(
                      quantityFromAmount(
                        nextAmount || "0",
                        weightedProduct.selling_price,
                      ),
                    );
                  }}
                />
              </>
            )}

            <div style={changeBox}>
              <span>
                {formatQuantity(
                  weightedQuantity,
                  weightedProduct.unit,
                )}{" "}
                x {formatMoney(weightedProduct.selling_price)}
                /{weightedProduct.unit}
              </span>
              <strong>
                {formatMoney(
                  multiplyPriceByQuantity(
                    weightedProduct.selling_price,
                    weightedQuantity,
                  ),
                )}
              </strong>
            </div>

            <button
              style={primaryButton}
              type="button"
              onClick={addWeightedProductToCart}
            >
              Add to Cart
            </button>
            <button
              style={secondaryButton}
              type="button"
              onClick={() => setWeightedProduct(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {receipt && (
        <div style={overlay}>
          <div style={modalCard}>
            <div style={successMark}>✓</div>
            <h2 style={{ textAlign: "center" }}>
              Sale Completed
            </h2>

            <p style={{ textAlign: "center" }}>
              Receipt {receipt.receipt_number}
            </p>

            <div style={receiptSummary}>
              {receipt.discount_amount && Number(receipt.discount_amount) > 0 && (
                <div>
                  <span>
                    {receipt.sale_discount_amount != null
                      ? "Line / sale-wide discounts"
                      : "Discount (combined)"}
                  </span>
                  <strong>
                    {receipt.sale_discount_amount != null
                      ? `${formatMoney(Number(receipt.discount_amount) - Number(receipt.sale_discount_amount))} / ${formatMoney(receipt.sale_discount_amount)}`
                      : formatMoney(receipt.discount_amount)}
                  </strong>
                </div>
              )}
              <div>
                <span>Total</span>
                <strong>
                  ${Number(receipt.total_amount).toFixed(2)}
                </strong>
              </div>

              <div>
                <span>Amount received</span>
                <strong>
                  ${Number(receipt.amount_received).toFixed(2)}
                </strong>
              </div>

              <div>
                <span>Change due</span>
                <strong>
                  ${Number(receipt.change_due).toFixed(2)}
                </strong>
              </div>

              <div>
                <span>Payment method</span>
                <strong>
                  {receipt.payment_method.toUpperCase()}
                </strong>
              </div>
              {receipt.payment_method === "credit" && (
                <>
                  <div>
                    <span>Customer</span>
                    <strong>
                      {receipt.customer_name_snapshot || "Customer"}
                      {receipt.customer_code_snapshot ? ` (${receipt.customer_code_snapshot})` : ""}
                    </strong>
                  </div>
                  <div>
                    <span>This credit sale outstanding</span>
                    <strong>{formatMoney(receipt.credit_outstanding_balance || receipt.total_amount)}</strong>
                  </div>
                  <div>
                    <span>Due date</span>
                    <strong>{receipt.credit_due_date || "See customer account"}</strong>
                  </div>
                </>
              )}
            </div>

            <button style={primaryButton} onClick={printReceipt}>
              Print Receipt
            </button>

            <button style={secondaryButton} onClick={newSale}>
              New Sale
            </button>

            {printerNotice && (
              <p style={messageText}>{printerNotice}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const pageCenter: CSSProperties = {
  minHeight: "100vh",
  display: "grid",
  placeItems: "center",
  background: "#f3f7f4",
};

const loginCard: CSSProperties = {
  width: 400,
  maxWidth: "calc(100vw - 32px)",
  background: "white",
  padding: 34,
  borderRadius: 22,
  boxShadow: "0 12px 35px #0002",
};

const brand: CSSProperties = {
  textAlign: "center",
  fontSize: 34,
  fontWeight: 900,
};

const input: CSSProperties = {
  width: "100%",
  padding: 14,
  marginTop: 14,
  borderRadius: 10,
  border: "1px solid #d1d5db",
};

const appShell: CSSProperties = {
  minHeight: "100vh",
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) 420px",
  background: "#f3f7f4",
};

const mainArea: CSSProperties = {
  minWidth: 0,
  padding: 28,
};

const searchBox: CSSProperties = {
  width: "100%",
  padding: 16,
  borderRadius: 14,
  border: "1px solid #d1d5db",
  marginBottom: 22,
};

const productGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns:
    "repeat(auto-fill, minmax(190px, 1fr))",
  gap: 18,
};

const productCard: CSSProperties = {
  background: "white",
  border: 0,
  borderRadius: 18,
  padding: 24,
  textAlign: "left",
  boxShadow: "0 8px 22px #0001",
  cursor: "pointer",
};

const cartPanel: CSSProperties = {
  background: "white",
  padding: 26,
  boxShadow: "-6px 0 24px #0001",
  display: "flex",
  flexDirection: "column",
};

const cartItemsArea: CSSProperties = {
  flex: 1,
  minHeight: 250,
  maxHeight: "50vh",
  overflowY: "auto",
};

const cartRow: CSSProperties = {
  borderBottom: "1px solid #eee",
  padding: "12px 0",
};

const quantityBox: CSSProperties = {
  display: "flex",
  gap: 8,
  alignItems: "center",
  justifyContent: "center",
};

const quantityButton: CSSProperties = {
  width: 30,
  height: 30,
  border: 0,
  borderRadius: 7,
  background: "#e5e7eb",
  fontWeight: 800,
};

const removeButton: CSSProperties = {
  width: 30,
  height: 30,
  border: 0,
  borderRadius: 7,
  background: "#fee2e2",
  color: "#b91c1c",
  fontWeight: 900,
};

const paymentGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 10,
};

const primaryButton: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: 15,
  marginTop: 16,
  background: "#07583B",
  color: "white",
  border: 0,
  borderRadius: 12,
  fontWeight: 800,
};

const secondaryButton: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: 13,
  marginTop: 10,
  background: "#ffffff",
  color: "#17212B",
  border: "1px solid #dfe7e1",
  borderRadius: 12,
  fontWeight: 700,
};

const activePaymentButton: CSSProperties = {
  ...secondaryButton,
  background: "#07583B",
  color: "white",
  border: "1px solid #06452F",
};

const overlay: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 1000,
  background: "rgba(15, 23, 42, 0.62)",
  display: "grid",
  placeItems: "center",
  padding: "clamp(8px, 3vw, 20px)",
  boxSizing: "border-box",
  overflow: "hidden",
};

const modalCard: CSSProperties = {
  width: "min(460px, 100%)",
  maxWidth: "100%",
  maxHeight: "calc(100dvh - 16px)",
  boxSizing: "border-box",
  overflowY: "auto",
  overflowX: "hidden",
  background: "white",
  borderRadius: 22,
  padding: "clamp(16px, 5vw, 30px)",
  boxShadow: "0 24px 70px rgba(0, 0, 0, 0.3)",
};

const modalLabel: CSSProperties = {
  display: "block",
  color: "#6b7280",
  fontWeight: 700,
  marginBottom: 7,
};

const tenderInput: CSSProperties = {
  width: "100%",
  maxWidth: "100%",
  minWidth: 0,
  boxSizing: "border-box",
  padding: "clamp(12px, 4vw, 18px)",
  border: "2px solid #111827",
  borderRadius: 12,
  fontSize: "clamp(20px, 7vw, 28px)",
  fontWeight: 800,
};

const changeBox: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  flexWrap: "wrap",
  minWidth: 0,
  maxWidth: "100%",
  boxSizing: "border-box",
  gap: 8,
  marginTop: 20,
  padding: "clamp(12px, 4vw, 18px)",
  borderRadius: 12,
  background: "#f3f4f6",
  fontSize: "clamp(17px, 5.5vw, 22px)",
  overflowWrap: "anywhere",
};

const successMark: CSSProperties = {
  width: 70,
  height: 70,
  display: "grid",
  placeItems: "center",
  margin: "0 auto",
  borderRadius: "50%",
  background: "#dcfce7",
  color: "#15803d",
  fontSize: 38,
  fontWeight: 900,
};

const receiptSummary: CSSProperties = {
  display: "grid",
  gap: 12,
  padding: 18,
  borderRadius: 14,
  background: "#f3f4f6",
};

const messageText: CSSProperties = {
  minHeight: 24,
  marginTop: 14,
  color: "#374151",
  fontWeight: 700,
};

const errorText: CSSProperties = {
  minHeight: 24,
  color: "crimson",
  textAlign: "center",
};

export default App;
