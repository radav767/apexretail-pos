import { api } from "./api/client";

export function getOrCreateDeviceKey(): string {
  const existing = localStorage.getItem("device_key");

  if (existing) {
    return existing;
  }

  const generated =
    globalThis.crypto?.randomUUID?.() ||
    `web-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  localStorage.setItem("device_key", generated);

  return generated;
}

export async function registerCurrentDevice(companyId: string) {
  const response = await api.post("/devices/register", {
    company_id: companyId,
    device_key: getOrCreateDeviceKey(),
    name: "Web POS",
    platform: "web",
    app_version: "1.0.0",
  });

  const result = response.data?.device || response.data;

  if (result?.device_key) {
    localStorage.setItem(
      "device_key",
      String(result.device_key),
    );
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

  return response.data;
}
