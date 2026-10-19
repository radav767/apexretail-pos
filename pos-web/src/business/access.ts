export function canProcessSales(permissions?: Record<string, boolean>) {
  return (permissions?.sales_process ?? permissions?.sales) !== false;
}

export function canAccessOperations(permissions?: Record<string, boolean>) {
  return ["orders_manage", "orders_settle", "kitchen_view", "bar_view", "hospitality_manage", "batches_view", "quotations_manage", "business_settings_manage"].some(key => permissions?.[key] === true);
}
