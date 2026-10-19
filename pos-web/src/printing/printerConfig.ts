import { Capacitor, registerPlugin } from "@capacitor/core";
import type { PluginListenerHandle } from "@capacitor/core";

import type {
  BluetoothStatus,
  PrinterConfig,
  PrinterConnectionType,
  PrinterDevice,
  ReceiptSnapshot,
} from "./types";

const STORAGE_KEY = "apexretail_printer_config_v1";

const defaultPrinterConfig: PrinterConfig = {
  enabled: false,
  connectionType: "bluetooth",
  selectedPrinterId: "",
  selectedPrinterName: "",
  paperWidth: "80mm",
  copies: 1,
  autoPrint: false,
  cutPaper: false,
};

type NativePrinterBridge = {
  getStatus(): Promise<{
    pluginName: string;
    packageName: string;
    bridgeAvailable: boolean;
    webViewAvailable: boolean;
    androidSdkInt: number;
    networkPrinting?: boolean;
  }>;
  getConfig(): Promise<{ config?: Partial<PrinterConfig> }>;
  saveConfig(options: { config: PrinterConfig }): Promise<{ config: PrinterConfig }>;
  clearSavedPrinter(): Promise<{ config: PrinterConfig }>;
  requestBluetoothAccess(): Promise<{ granted: boolean }>;
  getBluetoothStatus(): Promise<BluetoothStatus>;
  listBluetoothPrinters(): Promise<{ devices: PrinterDevice[] }>;
  openBluetoothSettings(): Promise<void>;
  openAppSettings(): Promise<void>;
  listUsbPrinters(): Promise<{ devices: PrinterDevice[] }>;
  openPrintSettings(): Promise<void>;
  requestUsbPermission(options: { deviceId: string }): Promise<{ granted: boolean }>;
  printReceipt(options: {
    connectionType: PrinterConnectionType;
    printerId?: string;
    copies: number;
    rawDataBase64?: string;
  }): Promise<void>;
  launchSystemPrint(options: {
    jobName: string;
    html: string;
  }): Promise<void>;
  addListener(
    eventName: "bluetoothSettingsClosed" | "usbDevicesChanged" | "printerAppResumed",
    listenerFunc: () => void,
  ): Promise<PluginListenerHandle>;
};

const printerBridge = registerPlugin<NativePrinterBridge>("ApexPrinter");

type NativePrinterStatus = Awaited<ReturnType<NativePrinterBridge["getStatus"]>>;

function sanitizeConfig(value: Partial<PrinterConfig> | null | undefined): PrinterConfig {
  const nextCopies = Number(value?.copies ?? defaultPrinterConfig.copies);

  return {
    enabled: Boolean(value?.enabled),
    connectionType:
      value?.connectionType === "usb" || value?.connectionType === "system" || value?.connectionType === "network"
        ? value.connectionType
        : "bluetooth",
    selectedPrinterId: String(value?.selectedPrinterId || ""),
    selectedPrinterName: String(value?.selectedPrinterName || ""),
    paperWidth: value?.paperWidth === "58mm" ? "58mm" : "80mm",
    copies:
      Number.isFinite(nextCopies) && nextCopies > 0
        ? Math.min(5, Math.max(1, Math.round(nextCopies)))
        : defaultPrinterConfig.copies,
    autoPrint: Boolean(value?.autoPrint),
    cutPaper: Boolean(value?.cutPaper),
  };
}

function isNativeAndroid() {
  return Capacitor.getPlatform() === "android";
}

export function getDefaultPrinterConfig() {
  return { ...defaultPrinterConfig };
}

export async function verifyNativePrinterBridge(): Promise<NativePrinterStatus | null> {
  if (!isNativeAndroid()) {
    return null;
  }

  const status = await printerBridge.getStatus();

  if (!status.bridgeAvailable || !status.webViewAvailable) {
    throw new Error("ApexPrinter is registered but the Android bridge is not ready.");
  }

  return status;
}

export async function loadPrinterConfig(): Promise<PrinterConfig> {
  if (isNativeAndroid()) {
    await verifyNativePrinterBridge();
    const result = await printerBridge.getConfig();
    return sanitizeConfig(result.config);
  }

  const rawValue = localStorage.getItem(STORAGE_KEY);

  if (!rawValue) {
    return getDefaultPrinterConfig();
  }

  try {
    return sanitizeConfig(JSON.parse(rawValue) as Partial<PrinterConfig>);
  } catch (error) {
    console.error("Failed to parse stored printer config", error);
    return getDefaultPrinterConfig();
  }
}

export async function savePrinterConfig(config: PrinterConfig): Promise<PrinterConfig> {
  const normalizedConfig = sanitizeConfig(config);

  if (isNativeAndroid()) {
    await verifyNativePrinterBridge();
    const result = await printerBridge.saveConfig({ config: normalizedConfig });
    return sanitizeConfig(result.config);
  }

  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalizedConfig));
  return normalizedConfig;
}

export async function clearSavedPrinter(): Promise<PrinterConfig> {
  if (isNativeAndroid()) {
    await verifyNativePrinterBridge();
    const result = await printerBridge.clearSavedPrinter();
    return sanitizeConfig(result.config);
  }

  const cleared = {
    ...getDefaultPrinterConfig(),
    connectionType: "bluetooth" as const,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cleared));
  return cleared;
}

export async function requestBluetoothAccess() {
  if (!isNativeAndroid()) {
    return { granted: false };
  }

  await verifyNativePrinterBridge();
  return printerBridge.requestBluetoothAccess();
}

export async function getBluetoothStatus(): Promise<BluetoothStatus> {
  if (!isNativeAndroid()) {
    return {
      available: false,
      enabled: false,
    };
  }

  await verifyNativePrinterBridge();
  return printerBridge.getBluetoothStatus();
}

export async function listBluetoothPrinters(): Promise<PrinterDevice[]> {
  if (!isNativeAndroid()) {
    return [];
  }

  await verifyNativePrinterBridge();
  const result = await printerBridge.listBluetoothPrinters();
  return result.devices || [];
}

export async function listUsbPrinters(): Promise<PrinterDevice[]> {
  if (!isNativeAndroid()) {
    return [];
  }

  await verifyNativePrinterBridge();
  const result = await printerBridge.listUsbPrinters();
  return result.devices || [];
}

export async function requestUsbPermission(deviceId: string) {
  if (!isNativeAndroid()) {
    return { granted: false };
  }

  await verifyNativePrinterBridge();
  return printerBridge.requestUsbPermission({ deviceId });
}

export async function openPrintSettings(): Promise<void> {
  if (!isNativeAndroid()) {
    throw new Error("Android print settings are available only in the Android app.");
  }

  await verifyNativePrinterBridge();
  await printerBridge.openPrintSettings();
}

export async function openBluetoothSettings(): Promise<void> {
  if (!isNativeAndroid()) {
    throw new Error("Bluetooth settings are available only in the Android app.");
  }

  await verifyNativePrinterBridge();
  await printerBridge.openBluetoothSettings();
}

export async function openAppSettings(): Promise<void> {
  if (!isNativeAndroid()) {
    throw new Error("App settings are available only in the Android app.");
  }

  await verifyNativePrinterBridge();
  await printerBridge.openAppSettings();
}

export async function onBluetoothSettingsClosed(
  listener: () => void,
): Promise<PluginListenerHandle | null> {
  if (!isNativeAndroid()) {
    return null;
  }

  await verifyNativePrinterBridge();
  return printerBridge.addListener(
    "bluetoothSettingsClosed",
    listener,
  );
}

export async function onUsbDevicesChanged(
  listener: () => void,
): Promise<PluginListenerHandle | null> {
  if (!isNativeAndroid()) {
    return null;
  }

  await verifyNativePrinterBridge();
  return printerBridge.addListener(
    "usbDevicesChanged",
    listener,
  );
}

export async function onPrinterAppResumed(
  listener: () => void,
): Promise<PluginListenerHandle | null> {
  if (!isNativeAndroid()) {
    return null;
  }

  await verifyNativePrinterBridge();
  return printerBridge.addListener(
    "printerAppResumed",
    listener,
  );
}

export async function sendReceiptToPrinter(options: {
  config: PrinterConfig;
  html: string;
  rawDataBase64: string;
  jobName: string;
}) {
  if (!options.config.enabled) {
    throw new Error("Printing is disabled on this device.");
  }

  if (options.config.connectionType === "system") {
    if (isNativeAndroid()) {
      await verifyNativePrinterBridge();
      await printerBridge.launchSystemPrint({
        jobName: options.jobName,
        html: options.html,
      });
      return;
    }

    const printWindow = window.open("", "_blank", "width=420,height=700");

    if (!printWindow) {
      throw new Error("Please allow pop-ups to print the receipt.");
    }

    printWindow.document.write(options.html);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
    return;
  }

  if (!isNativeAndroid()) {
    throw new Error("Direct Bluetooth, USB and LAN printing require the Android app. In Chrome use a system printer configured by your operating system.");
  }

  if (!options.config.selectedPrinterId) {
    throw new Error("Select a printer before printing.");
  }

  const status = await verifyNativePrinterBridge();
  if (options.config.connectionType === "network" && !status?.networkPrinting) {
    throw new Error("LAN printing needs the Phase 7C Android bridge. Use system printing until an approved APK update is installed.");
  }
  await printerBridge.printReceipt({
    connectionType: options.config.connectionType,
    printerId: options.config.selectedPrinterId,
    copies: options.config.copies,
    rawDataBase64: options.rawDataBase64,
  });
}

export function createTestReceiptSnapshot(
  companyId: string,
  branchName: string,
  cashierName: string,
): ReceiptSnapshot {
  const createdAt = new Date().toISOString();

  return {
    id: `test-${createdAt}`,
    receipt_number: "TEST-PRINT",
    company_id: companyId,
    branch_name: branchName,
    business_name: "ApexRetail POS",
    created_at: createdAt,
    cashier_name: cashierName,
    subtotal_amount: "10.00",
    tax_name: "Tax",
    tax_rate: "15.000",
    tax_amount: "1.50",
    tax_inclusive: false,
    total_amount: "11.50",
    amount_received: "20.00",
    change_due: "8.50",
    payment_method: "cash",
    status: "test",
    items: [
      {
        name: "Printer Test Item",
        quantity: 1,
        unit_price: "10.00",
        line_total: "10.00",
      },
    ],
    receipt_footer: "Printer test completed.",
  };
}
