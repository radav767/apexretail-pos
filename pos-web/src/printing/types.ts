export type PrinterConnectionType =
  | "bluetooth"
  | "usb"
  | "network"
  | "system";

export type PrinterPaperWidth = "58mm" | "80mm";

export type PrinterDevice = {
  id: string;
  name: string;
  shortIdentifier?: string;
  address?: string;
  productName?: string;
  manufacturerName?: string;
  vendorId?: number;
  productId?: number;
  transport?: "classic" | "ble" | "dual" | "usb" | "system" | "unknown";
  supported: boolean;
  connected?: boolean;
  note?: string;
};

export type PrinterConfig = {
  enabled: boolean;
  connectionType: PrinterConnectionType;
  selectedPrinterId: string;
  selectedPrinterName: string;
  paperWidth: PrinterPaperWidth;
  copies: number;
  autoPrint: boolean;
  cutPaper: boolean;
};

export type ReceiptLineItem = {
  product_id?: string;
  name: string;
  quantity: string | number;
  selling_unit?: string;
  unit_price: string;
  line_total: string;
  line_discount_amount?: string | null;
};

export type ReceiptSnapshot = {
  id: string;
  receipt_number: string;
  company_id: string;
  device_id?: string | null;
  shop_id?: string | null;
  shop_name?: string | null;
  shop_address?: {
    address_line_1?: string | null;
    address_line_2?: string | null;
    city?: string | null;
    state_province?: string | null;
    country?: string | null;
    phone?: string | null;
    tax_vat_number?: string | null;
  } | null;
  branch_id?: string | null;
  branch_name?: string | null;
  business_name: string;
  pos_name?: string | null;
  pos_number?: string | null;
  receipt_header?: string | null;
  receipt_footer?: string | null;
  created_at: string;
  shift_id?: string | null;
  is_duplicate?: boolean;
  original_receipt_number?: string;
  original_sale_time?: string;
  reprint_at?: string;
  reprint_count?: number;
  cashier_name?: string | null;
  customer_name?: string | null;
  customer_code?: string | null;
  credit_due_date?: string | null;
  credit_outstanding_balance?: string | null;
  subtotal_amount?: string;
  discount_amount?: string | null;
  sale_discount_amount?: string | null;
  tax_name?: string | null;
  tax_rate?: string;
  tax_amount?: string;
  tax_inclusive?: boolean;
  total_amount: string;
  amount_received: string;
  change_due: string;
  payment_method: string;
  base_currency_code?: string | null;
  payment_currency_code?: string | null;
  exchange_rate_id?: string | null;
  exchange_rate_snapshot?: string | null;
  payment_amount_original?: string | null;
  tendered_amount_original?: string | null;
  change_amount_original?: string | null;
  status: string;
  items: ReceiptLineItem[];
  document_type?: "shift_summary";
  shift_summary_lines?: Array<{ label: string; value: string }>;
};

export type PrinterError = {
  message: string;
  code?: string;
};

export type BluetoothStatus = {
  available: boolean;
  enabled: boolean;
};
