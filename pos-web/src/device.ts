import { api } from "./api/client";

export function getOrCreateDeviceKey(): string {
  const existing = localStorage.getItem("device_key");

  if (existing) {
    return existing;
  }

  const generated =
    globalThis.crypto?.randomUUID?.() ||
    `web-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2)}`;

  localStorage.setItem("device_key", generated);

  return generated;
}

export async function registerCurrentDevice(
  companyId: string,
) {
  const response = await api.post("/devices/register", {
    company_id: companyId,
    device_key: getOrCreateDeviceKey(),
    name: "Web POS",
    platform: "web",
    app_version: "1.0.0",
  });

  const device = response.data;

  localStorage.setItem("device_id", device.id || "");
  localStorage.setItem("shop_id", device.shop_id || "");
  localStorage.setItem("branch_id", device.branch_id || "");
  localStorage.setItem("device_name", device.name || "Web POS");
  localStorage.setItem(
    "branch_name",
    device.branch_name || "",
  );

  return device;
}
