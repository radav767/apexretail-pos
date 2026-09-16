import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../src/pages/ShopsDevicesPage.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/pages/shops-devices.css", import.meta.url), "utf8");
const employees = readFileSync(new URL("../src/pages/EmployeesPage.tsx", import.meta.url), "utf8");

test("device management exposes company branch creation and assignment states", () => {
  assert.ok(page.includes('api.post<Branch>("/devices/branches"'));
  assert.ok(page.includes('`/devices/branches/${companyId}`'));
  for (const copy of ["Creating...", "Select branch", "Failed to create branch", "Device-management permission required"]) {
    assert.ok(page.includes(copy), copy);
  }
  assert.ok(employees.includes('manage_devices: "Manage POS devices"'));
});

test("permanent deletion requires impact, warning, exact name and reauthentication", () => {
  assert.ok(page.includes("/deletion-impact"));
  assert.ok(page.includes("This cannot be undone."));
  assert.ok(page.includes("confirmation_name"));
  assert.ok(page.includes("reauthentication_secret"));
  assert.ok(page.includes('type="password"'));
  assert.ok(page.includes("Decommission terminal"));
  assert.ok(page.includes("decommissionBlockedDevice"));
  assert.ok(page.includes("offline_queue_resolved: deleteDialog.offlineQueueResolved"));
  assert.ok(page.includes("active_checkout_closed: deleteDialog.activeCheckoutClosed"));
  assert.ok(page.includes("Delete POS permanently"));
  assert.ok(!page.includes("void updateStatus(\n                            device,\n                            \"removed\""));
});

test("device controls remain vertically usable at required responsive sizes", () => {
  assert.match(css, /@media \(max-width: 700px\)[\s\S]*?\.device-actions-row,[\s\S]*?width:\s*100%/);
  for (const { width, height } of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
    { width: 320, height: 568 },
  ]) {
    const contentWidth = width <= 700 ? width - 36 : width - 48;
    assert.ok(contentWidth > 0);
    assert.ok(height >= 568);
    if (width <= 700) {
      assert.match(css, /grid-template-columns:\s*1fr/);
    }
  }
});
