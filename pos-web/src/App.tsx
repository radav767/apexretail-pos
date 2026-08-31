import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  api,
  getApiErrorMessage,
} from "./api/client";
import PosModulePage, { type PosModuleName } from "./PosModulePage";
import { getOrCreateDeviceKey, registerCurrentDevice } from "./device";
import {
  authenticateOfflineCashier,
  cacheOfflineCashier,
  isDeviceOnline,
} from "./offline/offlineAuth";

import {
  createClientSaleId,
  archiveReceiptSnapshot,
  getArchivedReceiptSnapshot,
  isAndroidNativeApp,
  isNetworkFailure,
  queueOfflineSale,
  startAutomaticOfflineSaleSync,
  type OfflineSalePayload,
} from "./offline/offlineSales";
import {
  formatCents,
  formatMillis,
  multiplyPriceByQuantity,
  parseMoneyToCents,
  parseQuantityToMillis,
  quantityFromAmount,
  subtractQuantities,
} from "./decimal";
import {
  isEntitlementSnapshotUsable,
  loadEntitlementSnapshot,
  saveEntitlementSnapshot,
  verifyEntitlementSnapshot,
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
};

type CartItem = Product & {
  quantity: string;
  selling_unit: string;
  line_total: string;
};

type Receipt = {
  id: string;
  receipt_number: string;
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
  subtotal_amount?: string;
  tax_name?: string | null;
  tax_rate?: string;
  tax_amount?: string;
  tax_inclusive?: boolean;
  total_amount: string;
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

type SaleReceiptResponse = Receipt & {
  items: Array<{
    product_id?: string;
    product_name: string;
    quantity: string;
    selling_unit?: string;
    unit_price: string;
    line_total: string;
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
  const [authLoading, setAuthLoading] = useState(false);


  const [products, setProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [search, setSearch] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [message, setMessage] = useState("");
  const [processing, setProcessing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activePosModule, setActivePosModule] = useState<PosModuleName>("Sales");

  const [showTender, setShowTender] = useState(false);
  const [amountReceived, setAmountReceived] = useState("");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [receiptItems, setReceiptItems] = useState<CartItem[]>([]);
  const [businessSettings, setBusinessSettings] =
    useState<BusinessSettings | null>(null);
  const [entitlementSnapshot, setEntitlementSnapshot] =
    useState<CachedEntitlementSnapshot | null>(null);
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
  const [cashierPin, setCashierPin] = useState("");
  const [pinLoading, setPinLoading] = useState(false);
  const [pinMessage, setPinMessage] = useState("");
  const [pinSelection, setPinSelection] = useState<{shops: Array<{id:string;name:string}>; terminals: Array<{id:string;shop_id:string;branch_id:string;name:string;pos_number?:number|null}>; pin:string} | null>(null);
  const [selectedShopId, setSelectedShopId] = useState("");
  const [selectedTerminalId, setSelectedTerminalId] = useState("");
  const [takeoverPrompt, setTakeoverPrompt] = useState(false);
  const latestDiscoveryRequestIdRef = useRef(0);
  const activeDiscoveryScopeRef = useRef<string | null>(null);

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
    };
  }

  useEffect(() => {
    const onInvalidated = () => {
      setCashier(null);
      setPinMessage("This POS session was ended on another device. Please sign in again.");
      setCart([]);
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

  useEffect(() => {
    if (!companyId) {
      return;
    }
    setEntitlementSnapshot(
      loadEntitlementSnapshot(companyId),
    );
  }, [companyId]);

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
              } else if (result.pending > 0) {
                setMessage(
                  `${result.pending} offline sale${
                    result.pending === 1 ? "" : "s"
                  } waiting to sync`,
                );
              }
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

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();

    return products.filter((product) =>
      product.name.toLowerCase().includes(query) ||
      (product.sku || "").toLowerCase().includes(query) ||
      (product.barcode || "").toLowerCase().includes(query)
    );
  }, [products, search]);

  const cartAmountCents = cart.reduce(
    (sum, item) => sum + parseMoneyToCents(item.line_total),
    0n,
  );
  const cartAmount = Number(formatCents(cartAmountCents));

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

  if (configuredTaxRate > 0) {
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

  const numericAmountReceived = Number(amountReceived || 0);
  const previewChange = Math.max(0, numericAmountReceived - total);

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
      saveEntitlementSnapshot(cached);
      setEntitlementSnapshot(
        (await verifyEntitlementSnapshot(cached))
          ? cached
          : null,
      );
    } catch (error) {
      const cached =
        loadEntitlementSnapshot(selectedCompanyId);
      setEntitlementSnapshot(cached);
      if (!cached) {
        throw error;
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
    return await isEntitlementSnapshotUsable(
      entitlementSnapshot,
    );
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
      cashier_name: cashierName || cashier?.name || null,
      subtotal_amount: sale.subtotal_amount,
      tax_name: sale.tax_name || null,
      tax_rate: sale.tax_rate,
      tax_amount: sale.tax_amount,
      tax_inclusive: sale.tax_inclusive,
      total_amount: sale.total_amount,
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
      const productResponse = await api.get(
        `/products/${id}`,
      );

      let loadedProducts = productResponse.data;

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
              balances.get(product.id) || "0",
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
    const authenticatedDeviceKey = String(
      data?.device?.device_key || "",
    ).trim();

    if (authenticatedDeviceKey) {
      localStorage.setItem("device_key", authenticatedDeviceKey);
    }

    const nextCompanyId = String(
      data?.company_id || data?.company?.id || "",
    );

    if (!data?.token || !nextCompanyId) {
      throw new Error(
        "Authentication response did not contain a token and company",
      );
    }

    const previousCompanyId =
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
      localStorage.setItem("device_key", deviceKey);
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
            pin: enteredPin,
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
        if (result.device_id) localStorage.setItem("device_id", String(result.device_id));
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
    setCashierPin("");
    setPinMessage("");
    setCart([]);
    setShowTender(false);
    setAmountReceived("");
    setReceipt(null);
    setReceiptItems([]);
    setMessage("");
  }



  function addToCart(product: Product) {
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
        (item) => item.id === product.id,
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
          item.id === product.id
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
          quantity: "1.000",
          selling_unit: product.unit || "each",
          line_total: multiplyPriceByQuantity(
            product.selling_price,
            "1.000",
          ),
        },
      ];
    });
  }

  function changeQty(id: string, difference: number) {
    setCart((currentCart) =>
      currentCart.map((item) => {
        if (item.id !== id) return item;
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
      currentCart.filter((item) => item.id !== id)
    );
  }

  function startPayment() {
    setMessage("");

    if (!cart.length) {
      setMessage("Add at least one product to the cart");
      return;
    }

    if (paymentMethod === "cash") {
      setAmountReceived(total.toFixed(2));
      setShowTender(true);
      return;
    }

    void submitSale();
  }

  async function submitSale(cashAmount?: number) {
    if (!cart.length || processing) {
      return;
    }

    if (!cashier) {
      setMessage("Cashier PIN is required");
      return;
    }

    setProcessing(true);
    setMessage("");

    const completedItems = [...cart];
    const clientSaleId = createClientSaleId();

    const payload: OfflineSalePayload = {
      client_sale_id: clientSaleId,
      company_id: companyId,
      branch_id: branchId || null,
      employee_id: cashier.id,
      device_id:
        localStorage.getItem("device_id") || null,
      device_key:
        localStorage.getItem("device_key") || null,
      payment_method: paymentMethod,
      items: cart.map((item) => ({
        product_id: item.id,
        quantity: item.quantity,
        selling_unit: item.selling_unit,
        unit_price: item.selling_price,
        line_total: item.line_total,
      })),
    };

    let receivedForReceipt = total;

    if (paymentMethod === "cash") {
      const numericAmountReceived =
        Number(amountReceived);

      const received =
        cashAmount ?? numericAmountReceived;

      if (
        !Number.isFinite(received) ||
        received < total
      ) {
        setMessage(
          "Amount received is less than the total",
        );
        setProcessing(false);
        return;
      }

      payload.amount_received =
        received.toFixed(2);

      receivedForReceipt = received;
    } else if (paymentMethod === "credit") {
      receivedForReceipt = 0;
    }

    const completeOfflineSale = async () => {
      if (!(await canCreateOfflineSale())) {
        setMessage(
          entitlementSnapshot?.message ||
            "Offline authorization has expired. Reconnect to renew this POS subscription.",
        );
        return;
      }

      await queueOfflineSale(payload);

      const rate =
        Math.max(0, configuredTaxRate);

      let offlineTaxAmount = 0;

      if (rate > 0) {
        if (taxInclusive) {
          offlineTaxAmount =
            total -
            total / (1 + rate / 100);
        } else {
          offlineTaxAmount =
            Math.max(0, total - cartAmount);
        }
      }

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
        amount_received:
          receivedForReceipt.toFixed(2),
        change_due:
          paymentMethod === "cash"
            ? Math.max(
                0,
                receivedForReceipt - total,
              ).toFixed(2)
            : "0.00",
        payment_method: paymentMethod,
        status: "offline_pending",
        created_at:
          new Date().toISOString(),
      } as Receipt;

      setReceipt(offlineReceipt);

      setReceiptItems(completedItems);
      setShowTender(false);
      setCart([]);
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
          })),
        ),
      );
    };

    try {
      try {
        const response =
          await api.post("/sales", payload);

        const savedReceipt = response.data as Receipt;

        setReceipt(savedReceipt);
        setReceiptItems(completedItems);
        setShowTender(false);
        setCart([]);
        setAmountReceived("");
        setMessage(
          "Sale completed successfully",
        );

        await archiveAndMaybePrintReceipt(
          buildReceiptSnapshot(
            savedReceipt,
            completedItems.map((item) => ({
              product_id: item.id,
              name: item.name,
              quantity: item.quantity,
              selling_unit: item.selling_unit,
              unit_price: item.selling_price,
              line_total: item.line_total,
            })),
          ),
        );

        await loadProducts(
          companyId,
          branchId || undefined,
        );
      } catch (error: any) {
        /*
         * Only network failures are converted into
         * offline transactions.
         *
         * Validation errors from the backend are NOT
         * queued, because they need to be corrected.
         */
        if (
          isAndroidNativeApp() &&
          isNetworkFailure(error)
        ) {
          if (!(await canCreateOfflineSale())) {
            throw new Error(
              entitlementSnapshot?.message ||
                "Offline authorization has expired. Reconnect to renew this POS subscription.",
            );
          }
          await completeOfflineSale();
          return;
        }

        throw error;
      }
    } catch (error: any) {
      setMessage(
        getApiErrorMessage(error, "Sale failed"),
      );
    } finally {
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
    setMessage("");
    setSearch("");
  }

  function showPosModule(
    moduleName: PosModuleName,
  ) {
    setActivePosModule(moduleName);
    setMenuOpen(false);
    setMessage("");
  }

  function openBackoffice() {
    setMenuOpen(false);

    window.open(
      "https://backoffice.apexpos.cloud",
      "_blank",
      "noopener,noreferrer",
    );
  }

  function logout() {
    localStorage.clear();

    setBranchId("");
    setCashier(null);
    setCashierPin("");
    setPinMessage("");
    setLoggedIn(false);
    setProducts([]);
    setCart([]);
    setReceipt(null);
    setReceiptItems([]);
    setBusinessSettings(null);
    setCompanyId("");
    setMessage("");
    setShowTender(false);
    setAmountReceived("");
    setAuthMode("login");
  }

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
      <div style={pageCenter}>
        <div
          style={{
            ...loginCard,
            width: authMode === "register" ? 760 : 430,
          }}
        >
          <h1 style={brand}>ApexRetail POS</h1>

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

              <button
                type="button"
                style={primaryButton}
                disabled={authLoading}
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
      <div style={pageCenter}>
        <div style={loginCard}>
          <h1 style={brand}>Preparing POS</h1>

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
        <div style={pageCenter}><div style={loginCard}>
          <h1 style={brand}>Choose POS location</h1>
          <p>Select an authorised shop and available terminal. New sign-in requires an internet connection.</p>
          {!pinSelection.shops.length ? <p style={errorText}>No authorised shops are available.</p> : <>
            <label style={modalLabel}>Shop<select style={input} value={selectedShopId} onChange={(e) => { setSelectedShopId(e.target.value); setSelectedTerminalId(""); }}><option value="">Select shop</option>{pinSelection.shops.map((shop) => <option key={shop.id} value={shop.id}>{shop.name}</option>)}</select></label>
            <label style={modalLabel}>Terminal<select style={input} value={selectedTerminalId} onChange={(e) => setSelectedTerminalId(e.target.value)}><option value="">Select terminal</option>{terminals.map((terminal) => <option key={terminal.id} value={terminal.id}>{terminal.name}{terminal.pos_number ? ` (#${terminal.pos_number})` : ""}</option>)}</select></label>
            {!terminals.length && selectedShopId && <p style={errorText}>No available active terminals in this shop.</p>}
            <button type="button" style={primaryButton} disabled={!selectedShopId || !selectedTerminalId || pinLoading} onClick={() => void loginWithEmployeePin({shop_id: selectedShopId, device_id: selectedTerminalId})}>{pinLoading ? "Signing in..." : "Enter POS"}</button>
            <button type="button" style={secondaryButton} onClick={() => { setPinSelection(null); setSelectedShopId(""); setSelectedTerminalId(""); }}>Cancel</button>
            {takeoverPrompt && <div role="alert" style={{ marginTop: 12, border: "1px solid #f59e0b", padding: 12 }}><p>You are already signed in elsewhere. Taking over will immediately sign out that device.</p><button type="button" style={secondaryButton} onClick={() => setTakeoverPrompt(false)}>Cancel</button><button type="button" style={primaryButton} onClick={() => { setTakeoverPrompt(false); void loginWithEmployeePin({ shop_id: selectedShopId, device_id: selectedTerminalId, takeover: true }); }}>Take over this session</button></div>}
          </>}
          {pinMessage && <p style={errorText}>{pinMessage}</p>}
        </div></div>
      );
    }
    return (
      <div style={pageCenter}>
        <div style={loginCard}>
          <h1 style={brand}>Cashier Sign In</h1>

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
          {takeoverPrompt && <div role="alert" style={{ marginTop: 12, border: "1px solid #f59e0b", padding: 12 }}><p>You are already signed in elsewhere. Taking over will immediately sign out that device.</p><button type="button" style={secondaryButton} onClick={() => setTakeoverPrompt(false)}>Cancel</button>{pinSelection ? <button type="button" style={primaryButton} onClick={() => { setTakeoverPrompt(false); void loginWithEmployeePin({ shop_id: selectedShopId, device_id: selectedTerminalId, takeover: true }); }}>Take over this session</button> : null}</div>}

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

  const canManageProducts =
    cashier?.role === "owner" ||
    Boolean(cashier?.permissions?.manage_products);
  const canManageInventory =
    cashier?.role === "owner" ||
    Boolean(cashier?.permissions?.manage_inventory);

  return (
    <div style={appShell} className="pos-sales-shell">
      <button

                  type="button"

                  aria-label="Open POS menu"

                  aria-expanded={menuOpen}

                  style={posMenuTrigger}

                  onClick={() => setMenuOpen((current) => !current)}

                >

                  ☰

                </button>


                {menuOpen && (

                  <>

                    <button

                      type="button"

                      aria-label="Close POS menu"

                      style={posMenuOverlay}

                      onClick={() => setMenuOpen(false)}

                    />


                    <aside style={posMenuPanel}>

                      <div style={posMenuHeader}>

                        <strong style={posMenuBrand}>ApexRetail POS</strong>

                        <span style={posMenuSubtitle}>Point of Sale Menu</span>

                      </div>


                      <div style={posMenuSession}>

                        <strong>{cashier?.name || "Cashier"}</strong>

                        <span>{cashier?.role || "employee"}</span>

                      </div>


                      <nav style={posMenuNavigation}>

                        <button

                          type="button"

                          style={{ ...posMenuButton, ...posMenuActiveButton }}

                          onClick={() => showPosModule("Sales")}

                        >

                          Sales

                        </button>


                        <button

                          type="button"

                          style={posMenuButton}

                          onClick={() => showPosModule("Sales Management")}

                        >

                          Sales Management

                        </button>

                        {canManageProducts && (
                          <button
                            type="button"
                            style={posMenuButton}
                            onClick={() => showPosModule("Products")}
                          >
                            Products
                          </button>
                        )}

                        {canManageInventory && (
                          <button
                            type="button"
                            style={posMenuButton}
                            onClick={() => showPosModule("Inventory")}
                          >
                            Inventory
                          </button>
                        )}


                        <button

                          type="button"

                          style={posMenuButton}

                          onClick={() => showPosModule("Reports")}

                        >

                          Reports

                        </button>


                        <button

                          type="button"

                          style={posMenuButton}

                          onClick={() => showPosModule("Settings")}

                        >

                          Settings

                        </button>


                        <button

                          type="button"

                          style={{ ...posMenuButton, ...posMenuBackofficeButton }}

                          onClick={openBackoffice}

                        >

                          Backoffice

                        </button>

                      </nav>


                      <button

                        type="button"

                        style={posMenuLogoutButton}

                        onClick={() => {

                          setMenuOpen(false);

                          logout();

                        }}

                      >

                        Log out

                      </button>

                    </aside>

                  </>

                )}

      {activePosModule !== "Sales" && (
        <PosModulePage
          activeModule={activePosModule}
          companyId={companyId}
          branchId={branchId}
          cashier={cashier}
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
          onProductsChanged={() =>
            void loadProducts(
              companyId,
              branchId || undefined,
            )
          }
          onBackToSales={() => {
            setActivePosModule("Sales");
            setMessage("");
          }}
        />
      )}

      <main style={mainArea} className="pos-sales-main">
        <div style={topBar} className="pos-sales-topbar">
          <div>
            <h1 style={{ margin: 0, fontSize: 32 }}>
              ApexRetail POS
            </h1>
            <p style={{ margin: "4px 0 0" }}>
            Sales screen
          </p>
          <p
            style={{
              margin: "5px 0 0",
              color: "#667085",
              fontSize: 14,
            }}
          >
            Cashier: <strong>{cashier?.name || "Employee"}</strong>
            {" · "}
            {localStorage.getItem("branch_name") ||
              "Assigned branch"}
          </p>
          {entitlementSnapshot && (
            <p
              style={{
                margin: "5px 0 0",
                color:
                  entitlementSnapshot.writes_allowed
                    ? "#15803d"
                    : "#b42318",
                fontSize: 13,
              }}
            >
              Subscription: {entitlementSnapshot.status.replace(/_/g, " ")}
            </p>
          )}
          </div>

          <button
          type="button"
          onClick={switchCashier}
          style={{
            ...secondaryButton,
            width: 150,
            marginTop: 0,
          }}
        >
          Switch Cashier
        </button>

        <button
            onClick={logout}
            style={{
              ...secondaryButton,
              width: 120,
              marginTop: 0,
            }}
          >
            Logout
          </button>
        </div>

        <input
          className="pos-sales-search"
          style={searchBox}
          placeholder="Search product by name, SKU or barcode..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />

        <div style={productGrid} className="pos-sales-product-grid">
          {filteredProducts.map((product) => (
            <button
              key={product.id}
              onClick={() => addToCart(product)}
              style={productCard}
              className="pos-product-card"
              disabled={Number(product.stock_qty) <= 0}
            >
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

        <div style={cartItemsArea}>
          {!cart.length && (
            <p style={{ color: "#6b7280" }}>
              Select a product to begin.
            </p>
          )}

          {cart.map((item) => (
            <div key={item.id} style={cartRow}>
              <div>
                <strong>{item.name}</strong>
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
                  {formatMoney(item.line_total)}
                </p>
              </div>

              <div style={quantityBox}>
                <button
                  style={quantityButton}
                  onClick={() => changeQty(item.id, -1)}
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
                  onClick={() => changeQty(item.id, 1)}
                  disabled={item.selling_unit !== "each"}
                >
                  +
                </button>
              </div>

              <button
                style={removeButton}
                onClick={() => removeFromCart(item.id)}
              >
                ×
              </button>
            </div>
          ))}
        </div>

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
            <span>Subtotal</span>
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
          onClick={startPayment}
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

      {showTender && (
        <div style={overlay}>
          <div style={modalCard}>
            <h2 style={{ marginTop: 0 }}>Cash Tender</h2>

            <p style={modalLabel}>Amount due</p>
            <h1 style={modalTotal}>${total.toFixed(2)}</h1>

            <label style={modalLabel}>Amount received</label>
            <input
              autoFocus
              type="number"
              min={total}
              step="0.01"
              value={amountReceived}
              style={tenderInput}
              onChange={(event) =>
                setAmountReceived(event.target.value)
              }
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void submitSale(numericAmountReceived);
                }
              }}
            />

            <div style={quickAmountGrid}>
              <button
                style={secondaryButton}
                onClick={() => setAmountReceived(total.toFixed(2))}
              >
                Exact
              </button>

              {[5, 10, 20].map((increment) => (
                <button
                  key={increment}
                  style={secondaryButton}
                  onClick={() =>
                    setAmountReceived(
                      (Math.ceil(total / increment) * increment).toFixed(2),
                    )
                  }
                >
                  Next ${increment}
                </button>
              ))}
            </div>

            <div style={changeBox}>
              <span>Change due</span>
              <strong>${previewChange.toFixed(2)}</strong>
            </div>

            <button
              style={primaryButton}
              disabled={
                processing ||
                !Number.isFinite(numericAmountReceived) ||
                numericAmountReceived < total
              }
              onClick={() =>
                void submitSale(numericAmountReceived)
              }
            >
              {processing ? "Processing..." : "Confirm Payment"}
            </button>

            <button
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
  background: "#eef2f7",
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
  background: "#eef2f7",
};

const mainArea: CSSProperties = {
  minWidth: 0,
  padding: 28,
};

const topBar: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 20,
  marginBottom: 20,
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
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) 105px 34px",
  gap: 8,
  alignItems: "center",
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
  padding: 15,
  marginTop: 16,
  background: "#111827",
  color: "white",
  border: 0,
  borderRadius: 12,
  fontWeight: 800,
};

const secondaryButton: CSSProperties = {
  width: "100%",
  padding: 13,
  marginTop: 10,
  background: "#e5e7eb",
  color: "#111827",
  border: 0,
  borderRadius: 12,
  fontWeight: 700,
};

const activePaymentButton: CSSProperties = {
  ...secondaryButton,
  background: "#111827",
  color: "white",
};

const overlay: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 1000,
  background: "rgba(15, 23, 42, 0.62)",
  display: "grid",
  placeItems: "center",
  padding: 20,
};

const modalCard: CSSProperties = {
  width: 460,
  maxWidth: "100%",
  maxHeight: "calc(100vh - 40px)",
  overflowY: "auto",
  background: "white",
  borderRadius: 22,
  padding: 30,
  boxShadow: "0 24px 70px rgba(0, 0, 0, 0.3)",
};

const modalLabel: CSSProperties = {
  display: "block",
  color: "#6b7280",
  fontWeight: 700,
  marginBottom: 7,
};

const modalTotal: CSSProperties = {
  fontSize: 48,
  margin: "0 0 25px",
};

const tenderInput: CSSProperties = {
  width: "100%",
  padding: 18,
  border: "2px solid #111827",
  borderRadius: 12,
  fontSize: 28,
  fontWeight: 800,
};

const quickAmountGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 9,
  marginTop: 8,
};

const changeBox: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  marginTop: 20,
  padding: 18,
  borderRadius: 12,
  background: "#f3f4f6",
  fontSize: 22,
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


const posMenuTrigger: CSSProperties = {
  position: "fixed",
  top: 24,
  left: 24,
  width: 46,
  height: 46,
  border: "none",
  borderRadius: 10,
  background: "#0f172a",
  color: "#ffffff",
  fontSize: 25,
  fontWeight: 700,
  cursor: "pointer",
  zIndex: 1102,
  boxShadow: "0 8px 24px rgba(15, 23, 42, 0.22)",
};

const posMenuOverlay: CSSProperties = {
  position: "fixed",
  inset: 0,
  border: "none",
  padding: 0,
  background: "rgba(15, 23, 42, 0.54)",
  cursor: "default",
  zIndex: 1100,
};

const posMenuPanel: CSSProperties = {
  position: "fixed",
  top: 0,
  left: 0,
  width: "min(340px, 88vw)",
  height: "100vh",
  padding: "28px 22px",
  boxSizing: "border-box",
  background: "#ffffff",
  zIndex: 1101,
  display: "flex",
  flexDirection: "column",
  boxShadow: "18px 0 50px rgba(15, 23, 42, 0.24)",
  overflowY: "auto",
};

const posMenuHeader: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 3,
  paddingLeft: 58,
  minHeight: 50,
  justifyContent: "center",
  marginBottom: 22,
};

const posMenuBrand: CSSProperties = {
  fontSize: 22,
  color: "#0f172a",
};

const posMenuSubtitle: CSSProperties = {
  fontSize: 13,
  color: "#64748b",
};

const posMenuSession: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 3,
  padding: 14,
  marginBottom: 18,
  borderRadius: 10,
  background: "#f1f5f9",
  color: "#0f172a",
};

const posMenuNavigation: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const posMenuButton: CSSProperties = {
  width: "100%",
  minHeight: 46,
  padding: "11px 14px",
  border: "1px solid #dbe3ec",
  borderRadius: 9,
  background: "#ffffff",
  color: "#172033",
  fontSize: 15,
  fontWeight: 650,
  textAlign: "left",
  cursor: "pointer",
};

const posMenuActiveButton: CSSProperties = {
  background: "#0f172a",
  borderColor: "#0f172a",
  color: "#ffffff",
};

const posMenuBackofficeButton: CSSProperties = {
  marginTop: 8,
  borderColor: "#0f172a",
  color: "#0f172a",
};

const posMenuLogoutButton: CSSProperties = {
  width: "100%",
  minHeight: 48,
  marginTop: "auto",
  padding: "12px 14px",
  border: "1px solid #fecaca",
  borderRadius: 9,
  background: "#fff1f2",
  color: "#b42318",
  fontSize: 15,
  fontWeight: 700,
  cursor: "pointer",
};
