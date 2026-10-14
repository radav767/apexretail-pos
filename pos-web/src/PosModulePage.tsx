import { useEffect, useMemo, useRef, useState } from "react";

import { api, getApiErrorMessage } from "./api/client";
import { isDeviceOnline } from "./offline/offlineAuth";
import BarcodeScannerDialog from "./barcode/BarcodeScannerDialog";
import {
  normalizeBarcode,
  resolveBarcodeProduct,
} from "./barcode/barcode";
import { useKeyboardWedge } from "./barcode/useKeyboardWedge";
import { KeyboardWedgeDetector } from "./barcode/keyboardWedge";
import FinancialModules, { type FinancialModuleName } from "./FinancialModules";
import ShiftManagementPage, { type ShiftRecord } from "./ShiftManagementPage";
import {
  canRefundSale,
  canViewSaleReceipt,
  isRefundableSale,
  saleStatusLabel,
  validateRefundQuantity,
} from "./salesHistory";
import type {
  BluetoothStatus,
  PrinterConfig,
  PrinterConnectionType,
  PrinterDevice,
} from "./printing/types";
import "./pos-modules.css";

export type PosModuleName =
  | "Sales"
  | "Sales Management"
  | "Products"
  | "Inventory"
  | FinancialModuleName
  | "Shift Management"
  | "Reports"
  | "Settings";

type CashierSession = {
  id: string;
  name: string;
  role: string;
  branch_id: string;
  permissions?: Record<string, boolean>;
};

type Sale = {
  id: string;
  original_sale_id?: string | null;
  receipt_number?: string;
  cashier_name?: string | null;
  payment_method?: string;
  total_amount?: string | number;
  status?: string;
  created_at?: string;
};

type SaleReceiptItem = {
  id: string;
  product_id: string;
  product_name: string;
  quantity: string | number;
  refunded_quantity: string | number;
  refundable_quantity: string | number;
  selling_unit?: string;
  unit_price: string | number;
  line_total: string | number;
  line_discount_amount?: string | number | null;
};

type SaleReceipt = Sale & {
  subtotal_amount?: string | number;
  tax_amount?: string | number;
  amount_received?: string | number;
  change_due?: string | number;
  discount_amount?: string | number | null;
  sale_discount_amount?: string | number | null;
  items: SaleReceiptItem[];
};

type Category = {
  id: string;
  name: string;
  active: boolean;
};

type Product = {
  id: string;
  name: string;
  category_id?: string | null;
  sku?: string | null;
  barcode?: string | null;
  unit?: string;
  selling_price?: string | number | null;
  cost_price?: string | number | null;
  stock_qty?: string | number;
  reorder_level?: string | number;
  active?: boolean;
};

type Branch = {
  id: string;
  shop_id: string;
  shop_name: string;
  name: string;
};

type BranchInventoryRow = {
  branch_id: string;
  product_id: string;
  product_name: string;
  sku?: string | null;
  barcode?: string | null;
  unit?: string;
  quantity: string | number;
  reorder_level: string | number;
  cost_price: string | number;
  stock_value: string | number;
  low_stock: boolean;
};

type Movement = {
  id: string;
  product_name: string;
  movement_type: string;
  quantity: string | number;
  before_qty: string | number;
  after_qty: string | number;
  reason?: string | null;
  reference?: string | null;
  notes?: string | null;
  created_at: string;
};

type DashboardSummary = {
  today_sales?: string | number;
  today_transactions?: number;
  total_products?: number;
  low_stock_products?: number;
};

type BusinessSettings = {
  name?: string;
  owner_name?: string | null;
  owner_email?: string;
  business_type?: string;
  country?: string | null;
  phone?: string | null;
  address?: string | null;
  contact_email?: string | null;
  currency_code?: string;
  currency_symbol?: string;
  decimal_places?: number;
  tax_name?: string;
  tax_rate?: string | number;
  tax_inclusive?: boolean;
  receipt_header?: string | null;
  receipt_footer?: string | null;
  paper_size?: string;
  auto_print?: boolean;
  payment_methods?: string[];
};

type Props = {
  activeModule: PosModuleName;
  companyId: string;
  branchId: string;
  cashier: CashierSession | null;
  currencySymbol: string;
  decimalPlaces: number;
  printerConfig: PrinterConfig;
  printerConfigLoaded: boolean;
  bluetoothStatus: BluetoothStatus;
  bluetoothPrinters: PrinterDevice[];
  usbPrinters: PrinterDevice[];
  isDiscoveringDevices: boolean;
  isSavingPrinter: boolean;
  isTestingPrinter: boolean;
  printerNotice: string;
  printerDiscoveryError: string;
  printerSaveError: string;
  printerTestError: string;
  bluetoothPermissionDenied: boolean;
  printerRefreshSignal: number;
  onSavePrinterConfig: (config: PrinterConfig) => Promise<void>;
  onRefreshPrinterDevices: (connectionType?: PrinterConnectionType) => Promise<void>;
  onOpenBluetoothSettings: () => Promise<void>;
  onOpenAppSettings: () => Promise<void>;
  onOpenPrintSettings: () => Promise<void>;
  onTestPrint: (config: PrinterConfig) => Promise<void>;
  onReprintSale: (saleId: string, receiptNumber?: string) => Promise<void>;
  onPrintShiftSummary: (shift: ShiftRecord) => Promise<void>;
  onProductsChanged?: () => void;
  onBackToSales: () => void;
};

type ProductForm = {
  branch_id: string;
  create_request_key: string;
  category_id: string;
  name: string;
  sku: string;
  barcode: string;
  unit: string;
  cost_price: string;
  selling_price: string;
  stock_qty: string;
  reorder_level: string;
};

type InventoryReceiveForm = {
  product_id: string;
  quantity: string;
  reason: string;
  unit_cost: string;
  reference: string;
  supplier: string;
  notes: string;
};

type InventoryAdjustmentForm = {
  product_id: string;
  adjustment_type: "add" | "remove" | "set";
  quantity: string;
  reason: string;
  reference: string;
  notes: string;
};

type SettingsPageKey =
  | "home"
  | "printer"
  | "business"
  | "tax"
  | "receipt";

const emptyProductForm: ProductForm = {
  branch_id: "",
  create_request_key: "",
  category_id: "",
  name: "",
  sku: "",
  barcode: "",
  unit: "each",
  cost_price: "",
  selling_price: "",
  stock_qty: "0",
  reorder_level: "0",
};

const emptyReceiveForm: InventoryReceiveForm = {
  product_id: "",
  quantity: "",
  reason: "",
  unit_cost: "",
  reference: "",
  supplier: "",
  notes: "",
};

const emptyAdjustmentForm: InventoryAdjustmentForm = {
  product_id: "",
  adjustment_type: "add",
  quantity: "",
  reason: "",
  reference: "",
  notes: "",
};

function extractRows<T>(value: unknown): T[] {
  if (Array.isArray(value)) {
    return value as T[];
  }

  if (
    value &&
    typeof value === "object" &&
    "items" in value &&
    Array.isArray((value as { items?: unknown[] }).items)
  ) {
    return (value as { items: T[] }).items;
  }

  return [];
}

function harareDateValue(date: Date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Harare",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);

  const year =
    parts.find((part) => part.type === "year")?.value || "";
  const month =
    parts.find((part) => part.type === "month")?.value || "";
  const day =
    parts.find((part) => part.type === "day")?.value || "";

  return `${year}-${month}-${day}`;
}

function localDateValue(date: Date = new Date()) {
  const timezoneOffset = date.getTimezoneOffset() * 60_000;

  return new Date(date.getTime() - timezoneOffset)
    .toISOString()
    .slice(0, 10);
}

export default function PosModulePage({
  activeModule,
  companyId,
  branchId,
  cashier,
  currencySymbol,
  decimalPlaces,
  printerConfig,
  printerConfigLoaded,
  bluetoothPrinters,
  usbPrinters,
  isDiscoveringDevices,
  isSavingPrinter,
  isTestingPrinter,
  printerNotice,
  printerDiscoveryError,
  printerSaveError,
  printerTestError,
  bluetoothPermissionDenied,
  printerRefreshSignal,
  onSavePrinterConfig,
  onRefreshPrinterDevices,
  onOpenBluetoothSettings,
  onOpenAppSettings,
  onOpenPrintSettings,
  onTestPrint,
  onReprintSale,
  onPrintShiftSummary,
  onProductsChanged,
  onBackToSales,
}: Props) {
  const [sales, setSales] = useState<Sale[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [branchInventory, setBranchInventory] = useState<
    BranchInventoryRow[]
  >([]);
  const [movements, setMovements] = useState<Movement[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [settings, setSettings] = useState<BusinessSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [salesDate, setSalesDate] = useState(() => harareDateValue());
  const [salesRefreshSignal, setSalesRefreshSignal] = useState(0);
  const [receiptDialog, setReceiptDialog] = useState<{
    mode: "view" | "refund";
    receipt: SaleReceipt;
  } | null>(null);
  const [refundQuantities, setRefundQuantities] = useState<
    Record<string, string>
  >({});
  const [refundReason, setRefundReason] = useState("");
  const [selectedBranchId, setSelectedBranchId] = useState(branchId);
  const [editingProductId, setEditingProductId] = useState("");
  const [productForm, setProductForm] =
    useState<ProductForm>(emptyProductForm);
  const [receiveForm, setReceiveForm] =
    useState<InventoryReceiveForm>(emptyReceiveForm);
  const [adjustmentForm, setAdjustmentForm] =
    useState<InventoryAdjustmentForm>(emptyAdjustmentForm);
  const [barcodeScannerTarget, setBarcodeScannerTarget] = useState<
    "product" | "inventory" | null
  >(null);
  const [inventoryBarcodeSearch, setInventoryBarcodeSearch] = useState("");
  const [printerDraft, setPrinterDraft] =
    useState<PrinterConfig>(printerConfig);
  const [printerSaveStatus, setPrinterSaveStatus] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const [printerSaveMessage, setPrinterSaveMessage] = useState("");
  const [activeSettingsPage, setActiveSettingsPage] =
    useState<SettingsPageKey>("home");
  const [printerSettingsAction, setPrinterSettingsAction] = useState<
    "" | "bluetooth" | "app" | "print"
  >("");
  const [printerSettingsError, setPrinterSettingsError] = useState("");
  const hasHydratedPrinterDraftRef = useRef(false);
  const inventorySearchWedgeRef = useRef(new KeyboardWedgeDetector());

  const canManageProducts =
    cashier?.role === "owner" ||
    Boolean(cashier?.permissions?.manage_products);
  const canManageInventory =
    cashier?.role === "owner" ||
    Boolean(cashier?.permissions?.manage_inventory);
  const canManageSettings =
    cashier?.role === "owner" ||
    Boolean(cashier?.permissions?.settings);
  const canViewSalesReceipts = canViewSaleReceipt(cashier);
  const canCreateRefunds = canRefundSale(cashier);

  function money(value: string | number | undefined) {
    return `${currencySymbol}${Number(value || 0).toFixed(decimalPlaces)}`;
  }

  const inventoryProducts = useMemo(() => {
    const normalizedSearch = normalizeBarcode(inventoryBarcodeSearch);
    return [...branchInventory].filter((row) => {
      if (!normalizedSearch) return true;
      const product = products.find((item) => item.id === row.product_id);
      return (
        row.product_name.toLowerCase().includes(normalizedSearch.toLowerCase()) ||
        (row.sku || "").toLowerCase().includes(normalizedSearch.toLowerCase()) ||
        normalizeBarcode(product?.barcode || "") === normalizedSearch
      );
    }).sort(
      (first, second) =>
        Number(first.quantity || 0) -
        Number(second.quantity || 0),
    );
  }, [branchInventory, inventoryBarcodeSearch, products]);

  useKeyboardWedge(
    activeModule === "Inventory" && barcodeScannerTarget === null,
    handleInventoryBarcode,
  );

  const selectedBranchName =
    branches.find((branch) => branch.id === selectedBranchId)?.name ||
    "Assigned branch";

  const bluetoothNameCounts = useMemo(() => {
    const counts = new Map<string, number>();

    for (const device of bluetoothPrinters) {
      const key = device.name.trim().toLowerCase();
      counts.set(key, (counts.get(key) || 0) + 1);
    }

    return counts;
  }, [bluetoothPrinters]);

  function bluetoothDeviceLabel(device: PrinterDevice) {
    const key = device.name.trim().toLowerCase();
    const duplicateCount = bluetoothNameCounts.get(key) || 0;

    if (duplicateCount > 1 && device.name.trim()) {
      return device.name.trim();
    }

    return device.name.trim() || "Bluetooth printer";
  }

  function selectPrinterDevice(device: PrinterDevice) {
    console.info("[printer] dropdown change", {
      connectionType: device.transport || printerDraft.connectionType,
      selectedPrinterId: device.id,
      selectedPrinterName: device.name,
    });
    setPrinterDraft((current) => ({
      ...current,
      selectedPrinterId: device.id,
      selectedPrinterName: device.name,
    }));
  }

  function systemPrinterFallbackDraft() {
    setPrinterDraft((current) => ({
      ...current,
      connectionType: "system",
      selectedPrinterId: "",
      selectedPrinterName: "",
    }));
  }

  useEffect(() => {
    setSelectedBranchId(branchId);
  }, [branchId]);

  useEffect(() => {
    if (!printerConfigLoaded || hasHydratedPrinterDraftRef.current) {
      return;
    }

    setPrinterDraft(printerConfig);
    setPrinterSaveStatus("idle");
    setPrinterSaveMessage("");
    hasHydratedPrinterDraftRef.current = true;
  }, [printerConfig, printerConfigLoaded]);

  useEffect(() => {
    if (activeModule !== "Settings") {
      setActiveSettingsPage("home");
      return;
    }


    if (activeSettingsPage !== "printer") {
      return;
    }

    void onRefreshPrinterDevices(
      printerDraft.connectionType === "system"
        ? undefined
        : printerDraft.connectionType,
    ).catch((printerError) => {
      setError(
        getApiErrorMessage(
          printerError,
          "Failed to load printer devices.",
        ),
      );
    });
  }, [
    activeModule,
    activeSettingsPage,
    printerDraft.connectionType,
    printerRefreshSignal,
    onRefreshPrinterDevices,
  ]);

  async function handleSavePrinter() {
    console.info("[printer] save click", {
      connectionType: printerDraft.connectionType,
      selectedPrinterId: printerDraft.selectedPrinterId,
    });
    setPrinterSaveStatus("saving");
    setPrinterSaveMessage("Saving...");
    setPrinterSettingsError("");

    try {
      await onSavePrinterConfig(printerDraft);
      setPrinterSaveStatus("saved");
      setPrinterSaveMessage("Printer saved");
    } catch (printerError) {
      console.error("[printer] save printer", printerError);
      setPrinterSaveStatus("error");
      setPrinterSaveMessage("Save failed");
    }
  }

  const bluetoothOptions = useMemo(() => {
    const options = [...bluetoothPrinters];

    if (
      printerDraft.connectionType === "bluetooth" &&
      printerDraft.selectedPrinterId &&
      !options.some((device) => device.id === printerDraft.selectedPrinterId)
    ) {
      options.unshift({
        id: printerDraft.selectedPrinterId,
        name:
          printerDraft.selectedPrinterName ||
          "Saved Bluetooth printer",
        supported: true,
      });
    }

    return options;
  }, [
    bluetoothPrinters,
    printerDraft.connectionType,
    printerDraft.selectedPrinterId,
    printerDraft.selectedPrinterName,
  ]);

  const usbOptions = useMemo(() => {
    const options = [...usbPrinters];

    if (
      printerDraft.connectionType === "usb" &&
      printerDraft.selectedPrinterId &&
      !options.some((device) => device.id === printerDraft.selectedPrinterId)
    ) {
      options.unshift({
        id: printerDraft.selectedPrinterId,
        name: printerDraft.selectedPrinterName || "Saved USB printer",
        supported: true,
      });
    }

    return options;
  }, [
    printerDraft.connectionType,
    printerDraft.selectedPrinterId,
    printerDraft.selectedPrinterName,
    usbPrinters,
  ]);

  const selectedUsbPrinter = useMemo(
    () =>
      usbPrinters.find(
        (device) => device.id === printerDraft.selectedPrinterId,
      ) || null,
    [printerDraft.selectedPrinterId, usbPrinters],
  );

  const requiresPrinterSelection =
    printerDraft.enabled &&
    printerDraft.connectionType !== "system";
  const hasValidPrinterSelection =
    printerDraft.connectionType === "system" ||
    Boolean(printerDraft.selectedPrinterId);
  const canSavePrinter =
    canManageSettings &&
    !isSavingPrinter &&
    (!requiresPrinterSelection || hasValidPrinterSelection);
  const canTestPrint =
    !isTestingPrinter &&
    printerDraft.enabled &&
    (!requiresPrinterSelection || hasValidPrinterSelection);

  useEffect(() => {
    let cancelled = false;

    async function loadModuleData() {
      if (!companyId || activeModule === "Sales") {
        return;
      }

      setLoading(true);
      setError("");
      setNotice("");

      try {
        if (activeModule === "Sales Management") {
          const response = await api.get(`/sales/history/${companyId}`, {
            params: {
              limit: 100,
              branch_id: branchId || undefined,
              sale_date: salesDate,
            },
          });

          if (!cancelled) {
            setSales(extractRows<Sale>(response.data));
          }
        }

        if (
          activeModule === "Products" ||
          activeModule === "Inventory"
        ) {
          const [
            productsResponse,
            categoriesResponse,
            branchesResponse,
          ] = await Promise.all([
            api.get(`/products/${companyId}`),
            api.get(`/products/categories/${companyId}`),
            api.get(`/inventory/branches/${companyId}`),
          ]);

          const loadedProducts =
            extractRows<Product>(productsResponse.data);
          const loadedCategories =
            extractRows<Category>(categoriesResponse.data);
          const loadedBranches =
            extractRows<Branch>(branchesResponse.data);
          const nextBranchId =
            selectedBranchId ||
            loadedBranches[0]?.id ||
            "";

          const [balancesResponse, historyResponse] = await Promise.all([
            api.get(`/inventory/branch-overview/${companyId}`, {
              params: {
                branch_id: nextBranchId || undefined,
              },
            }),
            api.get(`/inventory/history/${companyId}`, {
              params: { limit: 50 },
            }),
          ]);

          if (!cancelled) {
            setProducts(loadedProducts);
            setCategories(loadedCategories);
            setBranches(loadedBranches);
            setSelectedBranchId(nextBranchId);
            setBranchInventory(
              extractRows<BranchInventoryRow>(
                balancesResponse.data,
              ),
            );
            setMovements(extractRows<Movement>(historyResponse.data));
            setProductForm((current) => ({
              ...current,
              branch_id:
                current.branch_id ||
                nextBranchId,
            }));
            setReceiveForm((current) => ({
              ...current,
              product_id:
                current.product_id ||
                loadedProducts[0]?.id ||
                "",
            }));
            setAdjustmentForm((current) => ({
              ...current,
              product_id:
                current.product_id ||
                loadedProducts[0]?.id ||
                "",
            }));
          }
        }

        if (activeModule === "Reports") {
          const response = await api.get(
            `/dashboard/summary/${companyId}`,
          );

          if (!cancelled) {
            setSummary(response.data as DashboardSummary);
          }
        }

        if (activeModule === "Settings") {
          const response = await api.get(`/settings/${companyId}`);

          if (!cancelled) {
            setSettings(response.data as BusinessSettings);
          }
        }
      } catch (requestError: unknown) {
        if (!cancelled) {
          setError(
            getApiErrorMessage(
              requestError,
              `Failed to load ${activeModule}`,
            ),
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadModuleData();

    return () => {
      cancelled = true;
    };
  }, [
    activeModule,
    branchId,
    companyId,
    salesDate,
    salesRefreshSignal,
    selectedBranchId,
  ]);

  useEffect(() => {
    if (!editingProductId) {
      return;
    }

    const product = products.find(
      (item) => item.id === editingProductId,
    );

    if (!product) {
      return;
    }

    setProductForm((current) => ({
      ...current,
      branch_id:
        current.branch_id ||
        selectedBranchId,
      category_id: product.category_id || "",
      name: product.name,
      sku: product.sku || "",
      barcode: product.barcode || "",
      unit: product.unit || "each",
      cost_price: product.cost_price == null ? "" : String(product.cost_price),
      selling_price: product.selling_price == null ? "" : String(product.selling_price),
      stock_qty: String(product.stock_qty || "0"),
      reorder_level: String(product.reorder_level || "0"),
    }));
  }, [
    editingProductId,
    products,
    selectedBranchId,
  ]);

  if (activeModule === "Sales") {
    return null;
  }

  if (
    activeModule === "Customers" ||
    activeModule === "Credit Settlements" ||
    activeModule === "Expenses"
  ) {
    return (
      <FinancialModules
        activeModule={activeModule}
        companyId={companyId}
        branchId={branchId}
        cashier={cashier}
        currencySymbol={currencySymbol}
        decimalPlaces={decimalPlaces}
        printerConfig={printerConfig}
        onBackToSales={onBackToSales}
      />
    );
  }

  if (activeModule === "Shift Management") {
    return <ShiftManagementPage
      companyId={companyId}
      branchId={branchId}
      cashier={cashier}
      onBackToSales={onBackToSales}
      onPrintShiftSummary={onPrintShiftSummary}
    />;
  }

  async function ensureOnline() {
    const online = await isDeviceOnline();

    if (!online) {
      setError(
        "Internet required to manage products or inventory.",
      );
      return false;
    }

    return true;
  }

  async function openSaleReceipt(
    sale: Sale,
    mode: "view" | "refund",
  ) {
    if (mode === "view" && !canViewSalesReceipts) {
      setError("Sales permission is required to view receipts.");
      return;
    }
    if (mode === "refund" && !canCreateRefunds) {
      setError("Refunds permission is required to refund a sale.");
      return;
    }
    if (mode === "refund" && !isRefundableSale(sale)) {
      setError("This sale has no remaining refundable amount.");
      return;
    }
    if (!(await isDeviceOnline())) {
      setError("Internet access is required to view or refund this sale.");
      return;
    }

    try {
      setSaving(true);
      setError("");
      const response = await api.get(
        `/sales/receipt/${companyId}/${sale.id}`,
        { params: { mark_reprint: false } },
      );
      const receipt = response.data as SaleReceipt;

      if (
        mode === "refund" &&
        !receipt.items.some(
          (item) => Number(item.refundable_quantity || 0) > 0,
        )
      ) {
        setError("This sale has been fully refunded.");
        setSalesRefreshSignal((current) => current + 1);
        return;
      }

      setRefundQuantities(
        Object.fromEntries(
          receipt.items.map((item) => [item.id, ""]),
        ),
      );
      setRefundReason("");
      setReceiptDialog({ mode, receipt });
    } catch (requestError: unknown) {
      setError(
        getApiErrorMessage(
          requestError,
          mode === "refund"
            ? "Failed to load refundable sale details."
            : "Failed to load receipt.",
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  async function submitPartialRefund() {
    if (!receiptDialog || receiptDialog.mode !== "refund") {
      return;
    }
    if (!canCreateRefunds) {
      setError("Refunds permission is required to refund a sale.");
      return;
    }
    if (!refundReason.trim()) {
      setError("Enter a refund reason.");
      return;
    }

    const selectedItems = receiptDialog.receipt.items
      .map((item) => ({
        item,
        quantity: refundQuantities[item.id]?.trim() || "",
      }))
      .filter(({ quantity }) => quantity !== "" && Number(quantity) > 0);

    if (!selectedItems.length) {
      setError("Enter a refund quantity for at least one item.");
      return;
    }

    for (const { item, quantity } of selectedItems) {
      const quantityError = validateRefundQuantity(
        quantity,
        item.refundable_quantity,
      );
      if (quantityError) {
        setError(`${item.product_name}: ${quantityError}`);
        return;
      }
    }

    try {
      setSaving(true);
      setError("");
      const response = await api.post("/sales/refunds", {
        company_id: companyId,
        original_sale_id: receiptDialog.receipt.id,
        branch_id: branchId || undefined,
        employee_id: cashier?.id || undefined,
        device_id: localStorage.getItem("device_id") || undefined,
        device_key: localStorage.getItem("device_key") || undefined,
        reason: refundReason.trim(),
        refund_method: receiptDialog.receipt.payment_method,
        items: selectedItems.map(({ item, quantity }) => ({
          sale_item_id: item.id,
          quantity,
        })),
      });

      setReceiptDialog(null);
      setNotice(
        `Refund ${String(response.data?.receipt_number || "")} completed.`.trim(),
      );
      setSalesRefreshSignal((current) => current + 1);
    } catch (requestError: unknown) {
      setError(
        getApiErrorMessage(requestError, "Refund failed."),
      );
    } finally {
      setSaving(false);
    }
  }

  async function refreshProductAndInventoryData() {
    const [productsResponse, balancesResponse, historyResponse] =
      await Promise.all([
        api.get(`/products/${companyId}`),
        api.get(`/inventory/branch-overview/${companyId}`, {
          params: {
            branch_id: selectedBranchId || undefined,
          },
        }),
        api.get(`/inventory/history/${companyId}`, {
          params: { limit: 50 },
        }),
      ]);

    setProducts(extractRows<Product>(productsResponse.data));
    setBranchInventory(
      extractRows<BranchInventoryRow>(balancesResponse.data),
    );
    setMovements(extractRows<Movement>(historyResponse.data));
    onProductsChanged?.();
  }

  function resetProductForm() {
    setEditingProductId("");
    setProductForm({
      ...emptyProductForm,
      branch_id: selectedBranchId || branches[0]?.id || "",
    });
  }

  function handleInventoryBarcode(rawBarcode: string) {
    const resolution = resolveBarcodeProduct(products, rawBarcode);
    if (resolution.status === "not_found") {
      setError(`Product Not Found: ${resolution.barcode}`);
      return;
    }
    if (resolution.status === "ambiguous") {
      setError(`Barcode ${resolution.barcode} is assigned to multiple products.`);
      return;
    }
    setError("");
    setNotice(`${resolution.product.name} selected. No stock was changed.`);
    setInventoryBarcodeSearch(resolution.barcode);
    setReceiveForm((current) => ({
      ...current,
      product_id: resolution.product.id,
    }));
    setAdjustmentForm((current) => ({
      ...current,
      product_id: resolution.product.id,
    }));
    setBarcodeScannerTarget(null);
  }

  function handleProductBarcode(rawBarcode: string) {
    setProductForm((current) => ({
      ...current,
      barcode: normalizeBarcode(rawBarcode),
    }));
    setBarcodeScannerTarget(null);
    setNotice("Barcode captured. Save the product to apply it.");
  }

  function handleInventorySearchKeyDown(
    event: React.KeyboardEvent<HTMLInputElement>,
  ) {
    const barcode = inventorySearchWedgeRef.current.feed({
      key: event.key,
      timestamp: event.timeStamp,
      modifier: event.altKey || event.ctrlKey || event.metaKey,
      repeat: event.repeat,
      composing: event.nativeEvent.isComposing,
    });
    if (barcode) {
      event.preventDefault();
      handleInventoryBarcode(barcode);
    }
  }

  async function saveProduct() {
    if (!(await ensureOnline())) {
      return;
    }

    if (!canManageProducts) {
      setError("You do not have permission to manage products.");
      return;
    }

    if (!productForm.name.trim()) {
      setError("Product name is required.");
      return;
    }

    if (!editingProductId && !productForm.branch_id) {
      setError("Select the branch for opening stock.");
      return;
    }

    try {
      setSaving(true);
      setError("");
      setNotice("");

      const payload = {
        category_id: productForm.category_id || null,
        name: productForm.name.trim(),
        sku: productForm.sku.trim() || null,
        barcode: productForm.barcode.trim() || null,
        unit: productForm.unit,
        cost_price: productForm.cost_price || null,
        selling_price: productForm.selling_price || null,
        reorder_level: productForm.reorder_level || "0",
      };

      if (editingProductId) {
        await api.patch(
          `/products/${companyId}/${editingProductId}`,
          payload,
        );
        setNotice("Product updated successfully.");
      } else {
        const createRequestKey =
          productForm.create_request_key ||
          globalThis.crypto?.randomUUID?.() ||
          `product-${Date.now()}-${Math.random()
            .toString(36)
            .slice(2)}`;

        if (
          createRequestKey !==
          productForm.create_request_key
        ) {
          setProductForm((current) => ({
            ...current,
            create_request_key: createRequestKey,
          }));
        }

        await api.post("/products", {
          company_id: companyId,
          branch_id: productForm.branch_id,
          create_request_key: createRequestKey,
          ...payload,
          stock_qty: productForm.stock_qty || "0",
        });
        setNotice("Product created successfully.");
      }

      resetProductForm();
      await refreshProductAndInventoryData();
    } catch (requestError: unknown) {
      setError(
        getApiErrorMessage(
          requestError,
          "Failed to save product.",
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveReceivedStock() {
    if (!(await ensureOnline())) {
      return;
    }

    if (!canManageInventory) {
      setError("You do not have permission to manage inventory.");
      return;
    }

    if (!receiveForm.product_id) {
      setError("Select a product.");
      return;
    }

    if (
      !receiveForm.reason.trim() ||
      Number(receiveForm.quantity) <= 0
    ) {
      setError(
        "Quantity and reason are required for stock receiving.",
      );
      return;
    }

    try {
      setSaving(true);
      setError("");
      setNotice("");

      await api.post("/inventory/grn", {
        company_id: companyId,
        branch_id: selectedBranchId || null,
        product_id: receiveForm.product_id,
        quantity: receiveForm.quantity,
        reason: receiveForm.reason.trim(),
        unit_cost: receiveForm.unit_cost || null,
        reference: receiveForm.reference.trim() || null,
        supplier: receiveForm.supplier.trim() || null,
        notes: receiveForm.notes.trim() || null,
      });

      setReceiveForm((current) => ({
        ...emptyReceiveForm,
        product_id: current.product_id,
      }));
      setNotice("Stock received successfully.");
      await refreshProductAndInventoryData();
    } catch (requestError: unknown) {
      setError(
        getApiErrorMessage(
          requestError,
          "Failed to receive stock.",
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveAdjustment() {
    if (!(await ensureOnline())) {
      return;
    }

    if (!canManageInventory) {
      setError("You do not have permission to manage inventory.");
      return;
    }

    if (!adjustmentForm.product_id) {
      setError("Select a product.");
      return;
    }

    if (
      !adjustmentForm.reason.trim() ||
      Number(adjustmentForm.quantity) < 0 ||
      (adjustmentForm.adjustment_type !== "set" &&
        Number(adjustmentForm.quantity) <= 0)
    ) {
      setError(
        "Adjustment quantity and reason are required.",
      );
      return;
    }

    try {
      setSaving(true);
      setError("");
      setNotice("");

      await api.post("/inventory/adjustments", {
        company_id: companyId,
        branch_id: selectedBranchId || null,
        product_id: adjustmentForm.product_id,
        adjustment_type: adjustmentForm.adjustment_type,
        quantity: adjustmentForm.quantity,
        reason: adjustmentForm.reason.trim(),
        reference: adjustmentForm.reference.trim() || null,
        notes: adjustmentForm.notes.trim() || null,
      });

      setAdjustmentForm((current) => ({
        ...emptyAdjustmentForm,
        product_id: current.product_id,
      }));
      setNotice("Inventory adjustment saved.");
      await refreshProductAndInventoryData();
    } catch (requestError: unknown) {
      setError(
        getApiErrorMessage(
          requestError,
          "Failed to adjust stock.",
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="pos-module-overlay">
      <div className="pos-module-container">
        <header className="pos-module-header">
          <div>
            <p className="pos-module-eyebrow">ApexRetail POS</p>
            <h1>{activeModule}</h1>
            <p>Live information for the currently selected business.</p>
          </div>

          <button
            type="button"
            className="pos-module-sales-button"
            onClick={onBackToSales}
          >
            Return to Sales
          </button>
        </header>

        {loading && (
          <div className="pos-module-notice">Loading {activeModule}…</div>
        )}

        {error && (
          <div className="pos-module-notice pos-module-error">{error}</div>
        )}

        {notice && !error && (
          <div className="pos-module-notice">{notice}</div>
        )}

        {!loading && activeModule === "Sales Management" && (
          <div className="pos-module-card">
            <div className="pos-module-card-heading">
              <div>
                <h2>Sales History</h2>
                <div className="pos-module-date-filter">
                  <label htmlFor="sales-history-date">
                    Transaction date
                  </label>

                  <div className="pos-module-date-actions">
                    <input
                      id="sales-history-date"
                      type="date"
                      value={salesDate}
                      max={localDateValue()}
                      onChange={(event) =>
                        setSalesDate(event.target.value)
                      }
                    />

                    <button
                      type="button"
                      onClick={() =>
                        setSalesDate(localDateValue())
                      }
                    >
                      Today
                    </button>
                  </div>
                </div>
                <p>{sales.length} transaction records for {salesDate}</p>
              </div>
            </div>

            <div className="pos-module-table-wrap pos-sales-history-table-wrap">
              <table className="pos-module-table pos-sales-history-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Receipt</th>
                    <th>Cashier</th>
                    <th>Payment</th>
                    <th>Status</th>
                    <th className="number">Total</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sales.map((sale) => (
                    <tr key={sale.id}>
                      <td data-label="Date">
                        {sale.created_at
                          ? new Date(sale.created_at).toLocaleString()
                          : "—"}
                      </td>
                      <td data-label="Receipt">{sale.receipt_number || "—"}</td>
                      <td data-label="Cashier">{sale.cashier_name || "Unassigned"}</td>
                      <td data-label="Payment">
                        {(sale.payment_method || "unknown").toUpperCase()}
                      </td>
                      <td data-label="Status">
                        <span className={`pos-sale-status pos-sale-status-${sale.status || "completed"}`}>
                          {saleStatusLabel(sale)}
                        </span>
                      </td>
                      <td data-label="Total" className="number">
                        {money(sale.total_amount)}
                      </td>
                      <td data-label="Actions" className="pos-sale-actions-cell">
                        <div className="pos-sale-actions">
                          {canViewSalesReceipts && (
                            <button
                              type="button"
                              className="pos-inline-button secondary"
                              disabled={saving}
                              onClick={() => void openSaleReceipt(sale, "view")}
                            >
                              View Receipt
                            </button>
                          )}
                          {canViewSalesReceipts && (
                            <button
                              type="button"
                              className="pos-inline-button secondary"
                              disabled={saving}
                              onClick={() => {
                                void onReprintSale(
                                  sale.id,
                                  sale.receipt_number,
                                ).catch((printerError) => {
                                  setError(
                                    getApiErrorMessage(
                                      printerError,
                                      "Reprint failed.",
                                    ),
                                  );
                                });
                              }}
                            >
                              Reprint
                            </button>
                          )}
                          {canCreateRefunds && isRefundableSale(sale) && (
                            <button
                              type="button"
                              className="pos-inline-button danger"
                              disabled={saving}
                              onClick={() => void openSaleReceipt(sale, "refund")}
                            >
                              Refund
                            </button>
                          )}
                          {!canViewSalesReceipts && !canCreateRefunds && (
                            <span className="pos-sale-no-actions">No permitted actions</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}

                  {!sales.length && (
                    <tr>
                      <td colSpan={7} className="empty">
                        No sales have been recorded.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeModule === "Sales Management" && receiptDialog && (
          <div className="pos-sale-dialog-backdrop" role="presentation">
            <section
              className="pos-sale-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="sale-dialog-title"
            >
              <header className="pos-sale-dialog-header">
                <div>
                  <p className="pos-module-eyebrow">
                    {receiptDialog.mode === "refund"
                      ? "Partial refund"
                      : "On-screen receipt"}
                  </p>
                  <h2 id="sale-dialog-title">
                    {receiptDialog.receipt.receipt_number || "Receipt"}
                  </h2>
                  <span className={`pos-sale-status pos-sale-status-${receiptDialog.receipt.status || "completed"}`}>
                    {saleStatusLabel(receiptDialog.receipt)}
                  </span>
                </div>
                <button
                  type="button"
                  className="pos-sale-dialog-close"
                  aria-label="Close receipt"
                  onClick={() => setReceiptDialog(null)}
                >
                  ×
                </button>
              </header>

              <div className="pos-sale-receipt-meta">
                <span>
                  {receiptDialog.receipt.created_at
                    ? new Date(receiptDialog.receipt.created_at).toLocaleString()
                    : "—"}
                </span>
                <span>{receiptDialog.receipt.cashier_name || "Unassigned cashier"}</span>
                <span>{String(receiptDialog.receipt.payment_method || "unknown").toUpperCase()}</span>
              </div>

              <div className="pos-sale-dialog-items">
                {receiptDialog.receipt.items.map((item) => {
                  const remaining = Number(item.refundable_quantity || 0);
                  const refunded = Number(item.refunded_quantity || 0);
                  return (
                    <article className="pos-refund-item" key={item.id}>
                      <div className="pos-refund-item-heading">
                        <strong>{item.product_name}</strong>
                        <span>{money(item.line_total)}</span>
                      </div>
                      <div className="pos-refund-item-state">
                        <span>Sold: {Number(item.quantity)} {item.selling_unit || "each"}</span>
                        {Number(item.line_discount_amount || 0) > 0 && (
                          <span>Line discount: {money(item.line_discount_amount || 0)}</span>
                        )}
                        <span>Refunded: {refunded}</span>
                        <span>Remaining: {remaining}</span>
                      </div>
                      {receiptDialog.mode === "refund" && remaining > 0 && (
                        <label>
                          Quantity to refund
                          <input
                            type="number"
                            min="0"
                            max={remaining}
                            step="0.001"
                            inputMode="decimal"
                            value={refundQuantities[item.id] || ""}
                            onChange={(event) =>
                              setRefundQuantities((current) => ({
                                ...current,
                                [item.id]: event.target.value,
                              }))
                            }
                          />
                        </label>
                      )}
                    </article>
                  );
                })}
              </div>

              <div className="pos-sale-receipt-total">
                <span>
                  {receiptDialog.receipt.discount_amount && Number(receiptDialog.receipt.discount_amount) > 0
                    ? receiptDialog.receipt.sale_discount_amount != null
                      ? Number(receiptDialog.receipt.sale_discount_amount) > 0
                        ? `Sale-wide discount: ${money(receiptDialog.receipt.sale_discount_amount)} · Total`
                        : "Total"
                      : `Discount: ${money(receiptDialog.receipt.discount_amount)} combined · Total`
                    : "Total"}
                </span>
                <strong>{money(receiptDialog.receipt.total_amount)}</strong>
              </div>

              {receiptDialog.mode === "refund" && (
                <label className="pos-refund-reason">
                  Refund reason
                  <textarea
                    value={refundReason}
                    maxLength={500}
                    placeholder="Required for the audit trail"
                    onChange={(event) => setRefundReason(event.target.value)}
                  />
                </label>
              )}

              <footer className="pos-sale-dialog-actions">
                <button
                  type="button"
                  className="pos-inline-button secondary"
                  onClick={() => setReceiptDialog(null)}
                >
                  Close
                </button>
                {receiptDialog.mode === "refund" && (
                  <button
                    type="button"
                    className="pos-inline-button danger"
                    disabled={saving}
                    onClick={() => void submitPartialRefund()}
                  >
                    {saving ? "Refunding…" : "Complete Refund"}
                  </button>
                )}
              </footer>
            </section>
          </div>
        )}

        {!loading && activeModule === "Products" && (
          <>
            <div className="pos-module-card">
              <div className="pos-module-card-heading">
                <div>
                  <h2>Product Management</h2>
                  <p>
                    {canManageProducts
                      ? "Create or edit products for this branch."
                      : "You can view products, but product changes require the manage_products permission."}
                  </p>
                </div>
              </div>

              {canManageProducts ? (
                <div className="pos-module-form-grid">
                  <label>
                    Opening stock branch
                    <select
                      value={productForm.branch_id}
                      onChange={(event) =>
                        setProductForm((current) => ({
                          ...current,
                          branch_id: event.target.value,
                        }))
                      }
                      disabled={Boolean(editingProductId)}
                    >
                      <option value="">Select branch</option>
                      {branches.map((branch) => (
                        <option key={branch.id} value={branch.id}>
                          {branch.shop_name} — {branch.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Product name
                    <input
                      value={productForm.name}
                      onChange={(event) =>
                        setProductForm((current) => ({
                          ...current,
                          name: event.target.value,
                        }))
                      }
                    />
                  </label>

                  <label>
                    Category
                    <select
                      value={productForm.category_id}
                      onChange={(event) =>
                        setProductForm((current) => ({
                          ...current,
                          category_id: event.target.value,
                        }))
                      }
                    >
                      <option value="">Uncategorized</option>
                      {categories
                        .filter((category) => category.active)
                        .map((category) => (
                          <option key={category.id} value={category.id}>
                            {category.name}
                          </option>
                        ))}
                    </select>
                  </label>

                  <label>
                    SKU
                    <input
                      value={productForm.sku}
                      onChange={(event) =>
                        setProductForm((current) => ({
                          ...current,
                          sku: event.target.value,
                        }))
                      }
                    />
                  </label>

                  <label className="pos-barcode-field">
                    Barcode
                    <span className="pos-barcode-input-row">
                      <input
                        data-barcode-input="true"
                        value={productForm.barcode}
                        onChange={(event) =>
                          setProductForm((current) => ({
                            ...current,
                            barcode: event.target.value,
                          }))
                        }
                      />
                      <button
                        type="button"
                        onClick={() => setBarcodeScannerTarget("product")}
                      >
                        Scan Barcode
                      </button>
                    </span>
                  </label>

                  <label>
                    Sold by
                    <select
                      value={productForm.unit}
                      onChange={(event) =>
                        setProductForm((current) => ({
                          ...current,
                          unit: event.target.value,
                        }))
                      }
                    >
                      <option value="each">Each</option>
                      <option value="kg">Kilogram</option>
                      <option value="g">Gram</option>
                      <option value="litre">Litre</option>
                      <option value="ml">Millilitre</option>
                    </select>
                  </label>

                  <label>
                    Cost price
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={productForm.cost_price}
                      onChange={(event) =>
                        setProductForm((current) => ({
                          ...current,
                          cost_price: event.target.value,
                        }))
                      }
                    />
                  </label>

                  <label>
                    Selling price
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={productForm.selling_price}
                      onChange={(event) =>
                        setProductForm((current) => ({
                          ...current,
                          selling_price: event.target.value,
                        }))
                      }
                    />
                    <small>
                      {productForm.unit === "kg"
                        ? "For kg items, this is the price per kilogram."
                        : "Selling price per unit."}
                    </small>
                  </label>

                  <label>
                    Opening stock
                    <input
                      type="number"
                      min="0"
                      step={productForm.unit === "each" ? "1" : "0.001"}
                      value={productForm.stock_qty}
                      disabled={Boolean(editingProductId)}
                      onChange={(event) =>
                        setProductForm((current) => ({
                          ...current,
                          stock_qty: event.target.value,
                        }))
                      }
                    />
                    {editingProductId && (
                      <small>
                        Use inventory management to change stock quantities.
                      </small>
                    )}
                  </label>

                  <label>
                    Reorder level
                    <input
                      type="number"
                      min="0"
                      step={productForm.unit === "each" ? "1" : "0.001"}
                      value={productForm.reorder_level}
                      onChange={(event) =>
                        setProductForm((current) => ({
                          ...current,
                          reorder_level: event.target.value,
                        }))
                      }
                    />
                  </label>

                  <div className="pos-module-form-actions">
                    <button
                      type="button"
                      onClick={() => void saveProduct()}
                      disabled={saving}
                    >
                      {saving
                        ? "Saving..."
                        : editingProductId
                          ? "Update Product"
                          : "Create Product"}
                    </button>

                    {editingProductId && (
                      <button
                        type="button"
                        className="secondary"
                        onClick={resetProductForm}
                        disabled={saving}
                      >
                        Cancel Edit
                      </button>
                    )}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="pos-module-card">
              <div className="pos-module-card-heading">
                <div>
                  <h2>Available Products</h2>
                  <p>{products.length} products available on this POS</p>
                </div>
              </div>

              <div className="pos-module-table-wrap">
                <table className="pos-module-table">
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th>SKU</th>
                      <th>Barcode</th>
                      <th className="number">Selling Price</th>
                      <th className="number">Branch Stock</th>
                      <th>Status</th>
                      {canManageProducts && <th>Actions</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {products.map((product) => {
                      const balance = branchInventory.find(
                        (row) => row.product_id === product.id,
                      );

                      return (
                        <tr key={product.id}>
                          <td>
                            <strong>{product.name}</strong>
                          </td>
                          <td>{product.sku || "—"}</td>
                          <td>{product.barcode || "—"}</td>
                          <td className="number">
                            {product.selling_price == null
                              ? "Unavailable"
                              : money(product.selling_price)}
                          </td>
                          <td className="number">
                            {Number(
                              balance?.quantity ?? product.stock_qty ?? 0,
                            ).toFixed(3)}
                          </td>
                          <td>
                            <span
                              className={
                                product.active === false
                                  ? "pos-status inactive"
                                  : "pos-status active"
                              }
                            >
                              {product.active === false
                                ? "Inactive"
                                : "Active"}
                            </span>
                          </td>
                          {canManageProducts && (
                            <td>
                              <button
                                type="button"
                                className="pos-inline-button"
                                onClick={() =>
                                  setEditingProductId(product.id)
                                }
                              >
                                Edit
                              </button>
                            </td>
                          )}
                        </tr>
                      );
                    })}

                    {!products.length && (
                      <tr>
                        <td
                          colSpan={canManageProducts ? 7 : 6}
                          className="empty"
                        >
                          No products are available.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {!loading && activeModule === "Inventory" && (
          <>
            <div className="pos-module-card">
              <div className="pos-module-card-heading">
                <div>
                  <h2>Inventory Management</h2>
                  <p>
                    {canManageInventory
                      ? "Receive stock or adjust branch quantities. Internet is required."
                      : "You can view branch inventory, but stock changes require the manage_inventory permission."}
                  </p>
                </div>

                <label className="pos-module-branch-picker">
                  Branch
                  <select
                    value={selectedBranchId}
                    onChange={(event) =>
                      setSelectedBranchId(event.target.value)
                    }
                  >
                    {branches.map((branch) => (
                      <option key={branch.id} value={branch.id}>
                        {branch.shop_name} — {branch.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {canManageInventory ? (
                <div className="pos-module-management-grid">
                  <section className="pos-module-subcard">
                    <h3>Receive / Add Stock</h3>
                    <p>{selectedBranchName}</p>

                    <div className="pos-module-form-grid">
                      <label>
                        Product
                        <select
                          value={receiveForm.product_id}
                          onChange={(event) =>
                            setReceiveForm((current) => ({
                              ...current,
                              product_id: event.target.value,
                            }))
                          }
                        >
                          <option value="">Select product</option>
                          {products.map((product) => (
                            <option key={product.id} value={product.id}>
                              {product.name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label>
                        Quantity
                        <input
                          type="number"
                          min="0.001"
                          step="0.001"
                          value={receiveForm.quantity}
                          onChange={(event) =>
                            setReceiveForm((current) => ({
                              ...current,
                              quantity: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <label>
                        Reason
                        <input
                          value={receiveForm.reason}
                          placeholder="Example: New supplier delivery"
                          onChange={(event) =>
                            setReceiveForm((current) => ({
                              ...current,
                              reason: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <label>
                        Unit cost
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={receiveForm.unit_cost}
                          onChange={(event) =>
                            setReceiveForm((current) => ({
                              ...current,
                              unit_cost: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <label>
                        Reference
                        <input
                          value={receiveForm.reference}
                          onChange={(event) =>
                            setReceiveForm((current) => ({
                              ...current,
                              reference: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <label>
                        Supplier
                        <input
                          value={receiveForm.supplier}
                          onChange={(event) =>
                            setReceiveForm((current) => ({
                              ...current,
                              supplier: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <label className="full">
                        Notes
                        <textarea
                          value={receiveForm.notes}
                          onChange={(event) =>
                            setReceiveForm((current) => ({
                              ...current,
                              notes: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <div className="pos-module-form-actions">
                        <button
                          type="button"
                          onClick={() => void saveReceivedStock()}
                          disabled={saving}
                        >
                          {saving ? "Saving..." : "Receive Stock"}
                        </button>
                      </div>
                    </div>
                  </section>

                  <section className="pos-module-subcard">
                    <h3>Stock Adjustment</h3>
                    <p>Use this for removals, corrections, or physical counts.</p>

                    <div className="pos-module-form-grid">
                      <label>
                        Product
                        <select
                          value={adjustmentForm.product_id}
                          onChange={(event) =>
                            setAdjustmentForm((current) => ({
                              ...current,
                              product_id: event.target.value,
                            }))
                          }
                        >
                          <option value="">Select product</option>
                          {products.map((product) => (
                            <option key={product.id} value={product.id}>
                              {product.name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label>
                        Adjustment type
                        <select
                          value={adjustmentForm.adjustment_type}
                          onChange={(event) =>
                            setAdjustmentForm((current) => ({
                              ...current,
                              adjustment_type: event.target
                                .value as InventoryAdjustmentForm["adjustment_type"],
                            }))
                          }
                        >
                          <option value="add">Add stock</option>
                          <option value="remove">Remove stock</option>
                          <option value="set">Set physical quantity</option>
                        </select>
                      </label>

                      <label>
                        Quantity
                        <input
                          type="number"
                          min="0"
                          step="0.001"
                          value={adjustmentForm.quantity}
                          onChange={(event) =>
                            setAdjustmentForm((current) => ({
                              ...current,
                              quantity: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <label>
                        Reason
                        <input
                          value={adjustmentForm.reason}
                          placeholder="Example: Damaged stock"
                          onChange={(event) =>
                            setAdjustmentForm((current) => ({
                              ...current,
                              reason: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <label>
                        Reference
                        <input
                          value={adjustmentForm.reference}
                          onChange={(event) =>
                            setAdjustmentForm((current) => ({
                              ...current,
                              reference: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <label className="full">
                        Notes
                        <textarea
                          value={adjustmentForm.notes}
                          onChange={(event) =>
                            setAdjustmentForm((current) => ({
                              ...current,
                              notes: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <div className="pos-module-form-actions">
                        <button
                          type="button"
                          onClick={() => void saveAdjustment()}
                          disabled={saving}
                        >
                          {saving ? "Saving..." : "Save Adjustment"}
                        </button>
                      </div>
                    </div>
                  </section>
                </div>
              ) : null}
            </div>

            <div className="pos-module-card">
              <div className="pos-module-card-heading">
                <div>
                  <h2>Branch Inventory Overview</h2>
                  <p>{selectedBranchName}</p>
                </div>
              </div>

              <div className="pos-inventory-barcode-tools">
                <label>
                  Find product by name, SKU or barcode
                  <input
                    value={inventoryBarcodeSearch}
                    onChange={(event) => setInventoryBarcodeSearch(event.target.value)}
                    onKeyDown={handleInventorySearchKeyDown}
                    placeholder="Scan or enter a barcode"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => setBarcodeScannerTarget("inventory")}
                >
                  Scan Barcode
                </button>
              </div>

              <div className="pos-module-table-wrap">
                <table className="pos-module-table">
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th>SKU</th>
                      <th className="number">Current Stock</th>
                      <th className="number">Reorder Level</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inventoryProducts.map((product) => {
                      const stock = Number(product.quantity || 0);
                      const reorderLevel = Number(
                        product.reorder_level || 0,
                      );
                      const lowStock =
                        stock <= reorderLevel || stock <= 0;

                      return (
                        <tr key={product.product_id}>
                          <td>
                            <strong>{product.product_name}</strong>
                          </td>
                          <td>{product.sku || "—"}</td>
                          <td className="number">{stock.toFixed(3)}</td>
                          <td className="number">
                            {reorderLevel.toFixed(3)}
                          </td>
                          <td>
                            <span
                              className={
                                lowStock
                                  ? "pos-status low"
                                  : "pos-status active"
                              }
                            >
                              {stock <= 0
                                ? "Out of stock"
                                : lowStock
                                  ? "Low stock"
                                  : "Available"}
                            </span>
                          </td>
                        </tr>
                      );
                    })}

                    {!inventoryProducts.length && (
                      <tr>
                        <td colSpan={6} className="empty">
                          No inventory records are available.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="pos-module-card">
              <div className="pos-module-card-heading">
                <div>
                  <h2>Recent Inventory Activity</h2>
                  <p>Auditable branch stock movements.</p>
                </div>
              </div>

              <div className="pos-module-table-wrap">
                <table className="pos-module-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Movement</th>
                      <th>Product</th>
                      <th className="number">Quantity</th>
                      <th className="number">Before</th>
                      <th className="number">After</th>
                      <th>Reason / Reference</th>
                    </tr>
                  </thead>
                  <tbody>
                    {movements.map((movement) => (
                      <tr key={movement.id}>
                        <td>
                          {new Date(
                            movement.created_at,
                          ).toLocaleString()}
                        </td>
                        <td>{movement.movement_type}</td>
                        <td>{movement.product_name}</td>
                        <td className="number">
                          {Number(movement.quantity || 0).toFixed(3)}
                        </td>
                        <td className="number">
                          {Number(movement.before_qty || 0).toFixed(3)}
                        </td>
                        <td className="number">
                          {Number(movement.after_qty || 0).toFixed(3)}
                        </td>
                        <td>
                          {movement.reason || movement.reference || "—"}
                        </td>
                      </tr>
                    ))}

                    {!movements.length && (
                      <tr>
                        <td colSpan={7} className="empty">
                          No inventory movements have been recorded yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {!loading && activeModule === "Reports" && (
          <>
            <div className="pos-report-grid">
              <ReportCard
                title="Today's Sales"
                value={money(summary?.today_sales)}
                detail="Completed transaction value"
              />
              <ReportCard
                title="Transactions"
                value={String(summary?.today_transactions || 0)}
                detail="Sales completed today"
              />
              <ReportCard
                title="Products"
                value={String(summary?.total_products || 0)}
                detail="Active product records"
              />
              <ReportCard
                title="Low Stock"
                value={String(summary?.low_stock_products || 0)}
                detail="Products requiring attention"
                warning
              />
            </div>
          </>
        )}

        {barcodeScannerTarget && (
          <BarcodeScannerDialog
            title={
              barcodeScannerTarget === "product"
                ? "Scan product barcode"
                : "Find inventory product"
            }
            onScan={
              barcodeScannerTarget === "product"
                ? handleProductBarcode
                : handleInventoryBarcode
            }
            onClose={() => setBarcodeScannerTarget(null)}
          />
        )}

        {!loading && activeModule === "Settings" && (
          <>
            {activeSettingsPage === "home" ? (
              <div className="pos-module-card">
                <div className="pos-module-card-heading">
                  <div>
                    <h2>Settings</h2>
                    <p>
                      Open one page at a time.
                    </p>
                  </div>
                </div>

                <div className="pos-settings-menu">
                  <button
                    type="button"
                    className="pos-settings-menu-item"
                    onClick={() => setActiveSettingsPage("printer")}
                  >
                    <strong>Printer</strong>
                    <span>
                      {printerConfig.selectedPrinterName ||
                        "Choose printer connection"}
                    </span>
                  </button>

                  <button
                    type="button"
                    className="pos-settings-menu-item"
                    onClick={() => setActiveSettingsPage("business")}
                  >
                    <strong>Business</strong>
                    <span>{settings?.name || "Business details"}</span>
                  </button>

                  <button
                    type="button"
                    className="pos-settings-menu-item"
                    onClick={() => setActiveSettingsPage("tax")}
                  >
                    <strong>Tax & Currency</strong>
                    <span>
                      {settings?.currency_code || "Currency"} ·{" "}
                      {settings?.tax_name || "Tax"}
                    </span>
                  </button>

                  <button
                    type="button"
                    className="pos-settings-menu-item"
                    onClick={() => setActiveSettingsPage("receipt")}
                  >
                    <strong>Receipt & Payments</strong>
                    <span>
                      {settings?.payment_methods?.length
                        ? settings.payment_methods.join(", ").toUpperCase()
                        : "Receipt setup"}
                    </span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="pos-module-card">
                <div className="pos-settings-page-header">
                  <button
                    type="button"
                    className="pos-inline-button secondary"
                    onClick={() => setActiveSettingsPage("home")}
                  >
                    Back to Settings
                  </button>
                  <div>
                    <h2>
                      {activeSettingsPage === "printer"
                        ? "Printer"
                        : activeSettingsPage === "business"
                          ? "Business"
                          : activeSettingsPage === "tax"
                            ? "Tax & Currency"
                            : "Receipt & Payments"}
                    </h2>
                  </div>
                </div>

                {activeSettingsPage === "printer" ? (
                  <>
                    {!canManageSettings && (
                      <div className="pos-module-notice">
                        Printer changes require settings permission or owner access.
                      </div>
                    )}

                    {(printerSaveMessage || printerSaveStatus === "saving") && (
                      <div className="pos-module-notice">
                        {printerSaveStatus === "saving"
                          ? "Saving..."
                          : printerSaveMessage}
                      </div>
                    )}

                    {printerDiscoveryError && (
                      <div className="pos-module-notice">
                        {printerDiscoveryError}
                      </div>
                    )}

                    {printerSaveError && (
                      <div className="pos-module-notice">
                        {printerSaveError}
                      </div>
                    )}

                    {printerTestError && (
                      <div className="pos-module-notice">
                        {printerTestError}
                      </div>
                    )}

                    {printerSettingsError && (
                      <div className="pos-module-notice">
                        {printerSettingsError}
                      </div>
                    )}

                    {printerNotice && (
                      <div className="pos-module-notice">{printerNotice}</div>
                    )}

                    {isDiscoveringDevices && (
                      <div className="pos-module-notice">
                        Refreshing available printers...
                      </div>
                    )}

                    <div className="pos-module-form-grid pos-printer-form-grid">
                      <label>
                        Printing
                        <select
                          value={printerDraft.enabled ? "yes" : "no"}
                          disabled={!canManageSettings || isSavingPrinter}
                          onChange={(event) =>
                            setPrinterDraft((current) => ({
                              ...current,
                              enabled: event.target.value === "yes",
                            }))
                          }
                        >
                          <option value="yes">Enabled</option>
                          <option value="no">Disabled</option>
                        </select>
                      </label>

                      <label>
                        Connection type
                        <select
                          value={printerDraft.connectionType}
                          disabled={!canManageSettings || isSavingPrinter}
                          onChange={(event) => {
                            const connectionType = event.target
                              .value as PrinterConnectionType;
                            console.info("[printer] dropdown change", {
                              connectionType,
                              selectedPrinterId: "",
                            });
                            setPrinterDraft((current) => ({
                              ...current,
                              connectionType,
                              selectedPrinterId: "",
                              selectedPrinterName: "",
                            }));
                          }}
                        >
                          <option value="bluetooth">Bluetooth</option>
                          <option value="usb">USB</option>
                          <option value="system">System Printer</option>
                        </select>
                      </label>

                      {printerDraft.connectionType === "bluetooth" && (
                        <label className="full">
                          Bluetooth printer
                          <select
                            value={printerDraft.selectedPrinterId}
                            disabled={!canManageSettings || isSavingPrinter}
                            onChange={(event) => {
                              const device = bluetoothOptions.find(
                                (item) => item.id === event.target.value,
                              );

                              if (!device) {
                                console.info("[printer] dropdown change", {
                                  connectionType: "bluetooth",
                                  selectedPrinterId: "",
                                });
                                setPrinterDraft((current) => ({
                                  ...current,
                                  selectedPrinterId: "",
                                  selectedPrinterName: "",
                                }));
                                return;
                              }

                              selectPrinterDevice(device);
                            }}
                          >
                            <option value="">Choose a paired printer</option>
                            {bluetoothOptions.map((device) => (
                              <option key={device.id} value={device.id}>
                                {bluetoothDeviceLabel(device)}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}

                      {printerDraft.connectionType === "usb" && (
                        <label className="full">
                          USB printer
                          <select
                            value={printerDraft.selectedPrinterId}
                            disabled={!canManageSettings || isSavingPrinter}
                            onChange={(event) => {
                              const device = usbOptions.find(
                                (item) => item.id === event.target.value,
                              );

                              if (!device) {
                                console.info("[printer] dropdown change", {
                                  connectionType: "usb",
                                  selectedPrinterId: "",
                                });
                                setPrinterDraft((current) => ({
                                  ...current,
                                  selectedPrinterId: "",
                                  selectedPrinterName: "",
                                }));
                                return;
                              }

                              selectPrinterDevice(device);
                            }}
                          >
                            <option value="">Choose a connected printer</option>
                            {usbOptions.map((device) => (
                              <option key={device.id} value={device.id}>
                                {device.name.trim() || "USB printer"}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}

                      {printerDraft.connectionType === "system" && (
                        <div className="full pos-printer-helper">
                          System Printer opens the Android print dialog.
                        </div>
                      )}

                      <label>
                        Paper width
                        <select
                          value={printerDraft.paperWidth}
                          disabled={!canManageSettings || isSavingPrinter}
                          onChange={(event) =>
                            setPrinterDraft((current) => ({
                              ...current,
                              paperWidth:
                                event.target.value === "58mm"
                                  ? "58mm"
                                  : "80mm",
                            }))
                          }
                        >
                          <option value="58mm">58 mm</option>
                          <option value="80mm">80 mm</option>
                        </select>
                      </label>

                      <label>
                        Copies
                        <input
                          type="number"
                          min="1"
                          max="5"
                          value={printerDraft.copies}
                          disabled={!canManageSettings || isSavingPrinter}
                          onChange={(event) =>
                            setPrinterDraft((current) => ({
                              ...current,
                              copies: Number(event.target.value || 1),
                            }))
                          }
                        />
                      </label>

                      <label>
                        Auto-print
                        <select
                          value={printerDraft.autoPrint ? "yes" : "no"}
                          disabled={!canManageSettings || isSavingPrinter}
                          onChange={(event) =>
                            setPrinterDraft((current) => ({
                              ...current,
                              autoPrint: event.target.value === "yes",
                            }))
                          }
                        >
                          <option value="yes">On</option>
                          <option value="no">Off</option>
                        </select>
                      </label>

                      <label>
                        Cut paper
                        <select
                          value={printerDraft.cutPaper ? "yes" : "no"}
                          disabled={
                            !canManageSettings ||
                            isSavingPrinter ||
                            printerDraft.connectionType === "system"
                          }
                          onChange={(event) =>
                            setPrinterDraft((current) => ({
                              ...current,
                              cutPaper: event.target.value === "yes",
                            }))
                          }
                        >
                          <option value="no">Off</option>
                          <option value="yes">On</option>
                        </select>
                      </label>

                      {printerDraft.connectionType === "bluetooth" && (
                        <div className="full pos-printer-actions-inline">
                          <button
                            type="button"
                            className="secondary"
                            disabled={printerSettingsAction === "bluetooth"}
                            onClick={() => {
                              setPrinterSettingsAction("bluetooth");
                              setPrinterSettingsError("");
                              void onOpenBluetoothSettings().catch(
                                (printerError) => {
                                  setPrinterSettingsError(
                                    getApiErrorMessage(
                                      printerError,
                                      "Failed to open Android Bluetooth settings.",
                                    ),
                                  );
                                },
                              ).finally(() => {
                                setPrinterSettingsAction("");
                              });
                            }}
                          >
                            {printerSettingsAction === "bluetooth"
                              ? "Opening Bluetooth settings..."
                              : "Add Bluetooth Printer"}
                          </button>

                          {bluetoothPermissionDenied && (
                            <button
                              type="button"
                              className="secondary"
                              disabled={printerSettingsAction === "app"}
                              onClick={() => {
                                setPrinterSettingsAction("app");
                                setPrinterSettingsError("");
                                void onOpenAppSettings().catch(
                                  (printerError) => {
                                    setPrinterSettingsError(
                                      getApiErrorMessage(
                                        printerError,
                                        "Failed to open app settings.",
                                      ),
                                    );
                                  },
                                ).finally(() => {
                                  setPrinterSettingsAction("");
                                });
                              }}
                            >
                              {printerSettingsAction === "app"
                                ? "Opening app settings..."
                                : "Open App Settings"}
                            </button>
                          )}
                        </div>
                      )}

                      {printerDraft.connectionType === "usb" && (
                        <div className="full pos-printer-actions-inline">
                          {selectedUsbPrinter &&
                            !selectedUsbPrinter.supported && (
                              <button
                                type="button"
                                className="secondary"
                                disabled={!canManageSettings || isSavingPrinter}
                                onClick={systemPrinterFallbackDraft}
                              >
                                Use System Printer
                              </button>
                            )}
                          <button
                            type="button"
                            className="secondary"
                            disabled={printerSettingsAction === "print"}
                            onClick={() => {
                              setPrinterSettingsAction("print");
                              setPrinterSettingsError("");
                              void onOpenPrintSettings().catch(
                                (printerError) => {
                                  setPrinterSettingsError(
                                    getApiErrorMessage(
                                      printerError,
                                      "Failed to open Android print settings.",
                                    ),
                                  );
                                },
                              ).finally(() => {
                                setPrinterSettingsAction("");
                              });
                            }}
                          >
                            {printerSettingsAction === "print"
                              ? "Opening print settings..."
                              : "Open Android Print Settings"}
                          </button>
                        </div>
                      )}

                      {printerDraft.connectionType === "system" && (
                        <div className="full pos-printer-actions-inline">
                          <button
                            type="button"
                            className="secondary"
                            disabled={printerSettingsAction === "print"}
                            onClick={() => {
                              setPrinterSettingsAction("print");
                              setPrinterSettingsError("");
                              void onOpenPrintSettings().catch(
                                (printerError) => {
                                  setPrinterSettingsError(
                                    getApiErrorMessage(
                                      printerError,
                                      "Failed to open Android print settings.",
                                    ),
                                  );
                                },
                              ).finally(() => {
                                setPrinterSettingsAction("");
                              });
                            }}
                          >
                            {printerSettingsAction === "print"
                              ? "Opening print settings..."
                              : "Open Android Print Settings"}
                          </button>
                        </div>
                      )}

                      <div className="pos-module-form-actions">
                        <button
                          type="button"
                          disabled={!canSavePrinter}
                          onClick={() => {
                            void handleSavePrinter();
                          }}
                        >
                          Save printer
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          disabled={!canTestPrint}
                          onClick={() => {
                            void onTestPrint(printerDraft).catch(
                              (printerError) => {
                                setError(
                                  getApiErrorMessage(
                                    printerError,
                                    "Test print failed.",
                                  ),
                                );
                              },
                            );
                          }}
                        >
                          {isTestingPrinter ? "Sending..." : "Test Print"}
                        </button>
                      </div>
                    </div>
                  </>
                ) : activeSettingsPage === "business" ? (
                  <SettingsCard
                    title="Business"
                    rows={[
                      ["Business name", settings?.name || "—"],
                      ["Owner", settings?.owner_name || "—"],
                      ["Business type", settings?.business_type || "—"],
                      ["Country", settings?.country || "—"],
                      ["Phone", settings?.phone || "—"],
                      [
                        "Email",
                        settings?.contact_email ||
                          settings?.owner_email ||
                          "—",
                      ],
                      ["Address", settings?.address || "—"],
                    ]}
                  />
                ) : activeSettingsPage === "tax" ? (
                  <SettingsCard
                    title="Tax & Currency"
                    rows={[
                      ["Currency", settings?.currency_code || "—"],
                      ["Symbol", settings?.currency_symbol || "—"],
                      [
                        "Decimal places",
                        String(settings?.decimal_places ?? 2),
                      ],
                      ["Tax name", settings?.tax_name || "—"],
                      ["Tax rate", `${Number(settings?.tax_rate || 0)}%`],
                      [
                        "Tax inclusive",
                        settings?.tax_inclusive ? "Yes" : "No",
                      ],
                    ]}
                  />
                ) : (
                  <SettingsCard
                    title="Receipt & Payments"
                    rows={[
                      ["Paper size", settings?.paper_size || "—"],
                      [
                        "Business auto print",
                        settings?.auto_print ? "Enabled" : "Disabled",
                      ],
                      [
                        "Payment methods",
                        settings?.payment_methods
                          ?.join(", ")
                          .toUpperCase() || "—",
                      ],
                      ["Receipt header", settings?.receipt_header || "—"],
                      ["Receipt footer", settings?.receipt_footer || "—"],
                    ]}
                  />
                )}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function ReportCard({
  title,
  value,
  detail,
  warning = false,
}: {
  title: string;
  value: string;
  detail: string;
  warning?: boolean;
}) {
  return (
    <article className={`pos-report-card${warning ? " warning" : ""}`}>
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function SettingsCard({
  title,
  rows,
}: {
  title: string;
  rows: Array<[string, string]>;
}) {
  return (
    <section>
      <h2>{title}</h2>

      <dl className="pos-settings-list">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
