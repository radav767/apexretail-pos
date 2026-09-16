import { api } from "./api/client.ts";
import {
  getOrCreateDeviceKey,
  rememberDeviceIdentity,
} from "./deviceIdentity.ts";

export { getOrCreateDeviceKey } from "./deviceIdentity.ts";

export async function registerCurrentDevice(companyId: string) {
  const response = await api.post("/devices/register", {
    company_id: companyId,
    device_key: getOrCreateDeviceKey(companyId),
    name: "Web POS",
    platform: "web",
    app_version: "1.0.0",
  });

  const result = response.data?.device || response.data;

  if (result?.device_key) {
    rememberDeviceIdentity(
      companyId,
      String(result.device_key),
      result?.id ? String(result.id) : undefined,
    );
  } else if (result?.id) {
    localStorage.setItem("device_id", String(result.id));
  }

  const branchId =
    result?.branch_id ||
    result?.branch?.id ||
    response.data?.branch_id ||
    response.data?.branch?.id;

  const branchName =
    result?.branch_name ||
    result?.branch?.name ||
    response.data?.branch_name ||
    response.data?.branch?.name;

  if (branchId) {
    localStorage.setItem("branch_id", String(branchId));
  }

  if (branchName) {
    localStorage.setItem("branch_name", String(branchName));
  }

  if (result?.shop_id) {
    localStorage.setItem("shop_id", String(result.shop_id));
  }

  if (result?.shop_name) {
    localStorage.setItem("shop_name", String(result.shop_name));
  }

  if (result?.assignment_revision != null) {
    localStorage.setItem(
      "device_assignment_revision",
      String(result.assignment_revision),
    );
  }

  if (result?.friendly_name || result?.name) {
    localStorage.setItem(
      "pos_name",
      String(result?.friendly_name || result?.name),
    );
  }

  if (result?.pos_number != null) {
    localStorage.setItem(
      "pos_number",
      String(result.pos_number),
    );
  }

  const shopAddress = {
    address_line_1:
      result?.shop_address_line_1 || null,
    address_line_2:
      result?.shop_address_line_2 || null,
    city: result?.shop_city || null,
    state_province:
      result?.shop_state_province || null,
    country: result?.shop_country || null,
    phone: result?.shop_phone || null,
    tax_vat_number:
      result?.shop_tax_vat_number || null,
  };

  if (Object.values(shopAddress).some(Boolean)) {
    localStorage.setItem(
      "shop_address_snapshot",
      JSON.stringify(shopAddress),
    );
  }

  return response.data;
}
