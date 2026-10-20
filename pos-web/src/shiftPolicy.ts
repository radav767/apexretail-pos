export type CashierShiftIdentity = {
  company_id: string; branch_id: string; employee_id: string; device_id: string;
};
export type SaleShift = CashierShiftIdentity & {
  id: string; status: string; offline_shift_token?: string | null;
};

export function hasActiveCashierShift(shift: SaleShift | null, identity: CashierShiftIdentity): boolean {
  return Boolean(shift?.id && shift.status === "open" &&
    Object.entries(identity).every(([field, value]) => value && shift[field as keyof CashierShiftIdentity] === value));
}

export function saleShiftError(required: boolean, shift: SaleShift | null, identity: CashierShiftIdentity, offline = false): string | null {
  // Existing non-enforcing businesses and historical offline queues are unchanged.
  if (!required) return null;
  if (!hasActiveCashierShift(shift, identity)) return "Start Shift before completing a sale. A cashier-specific active shift is required.";
  if (offline && !shift?.offline_shift_token) return "Reconnect to verify this cashier's shift before creating an offline sale.";
  return null;
}
