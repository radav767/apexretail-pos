import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import assert from "node:assert/strict";

const root = resolve(import.meta.dirname, "..");
const path = "android/app/src/main/java/cloud/apexpos/pos";
const plugin = readFileSync(resolve(root, path, "ApexPrinterPlugin.java"), "utf8");
assert.ok(plugin.includes("Manifest.permission.BLUETOOTH_CONNECT"));
assert.ok(plugin.includes("ContextCompat.RECEIVER_NOT_EXPORTED"));
assert.ok(plugin.includes('"bluetooth".equals(connectionType)'));
assert.ok(plugin.includes('"usb".equals(connectionType)'));
assert.ok(plugin.includes('"network".equals(connectionType)'));
assert.ok(plugin.includes("PrinterNetworkTarget.parse(printerId)"));
assert.ok(plugin.includes("socket.connect(") && plugin.includes("5000"));
const output = mkdtempSync(resolve(tmpdir(), "apex-printer-jvm-"));
try {
  const compile = spawnSync("javac", ["-d", output, resolve(root, path, "PrinterNetworkTarget.java"), resolve(root, "android/app/src/test/java/cloud/apexpos/pos/PrinterNetworkTargetCheck.java")], { stdio: "inherit" });
  assert.equal(compile.status, 0);
  const run = spawnSync("java", ["-cp", output, "cloud.apexpos.pos.PrinterNetworkTargetCheck"], { stdio: "inherit" });
  assert.equal(run.status, 0);
  console.log("PASS: Bluetooth/USB permission guard and transport source checks. No APK built.");
} finally { rmSync(output, { recursive: true, force: true }); }
