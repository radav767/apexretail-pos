import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const modules = readFileSync(new URL("../src/PosModulePage.tsx", import.meta.url), "utf8");
const dialog = readFileSync(new URL("../src/barcode/BarcodeScannerDialog.tsx", import.meta.url), "utf8");
const detector = readFileSync(new URL("../src/barcode/cameraDetector.ts", import.meta.url), "utf8");
const wedgeHook = readFileSync(new URL("../src/barcode/useKeyboardWedge.ts", import.meta.url), "utf8");
const scannerCss = readFileSync(new URL("../src/barcode/barcode-scanner.css", import.meta.url), "utf8");
const manifest = readFileSync(new URL("../android/app/src/main/AndroidManifest.xml", import.meta.url), "utf8");

test("sales scan reuses the existing cart and supports focused search wedges", () => {
  assert.match(app, /Scan Barcode/);
  assert.match(app, /handleSalesSearchKeyDown/);
  assert.match(app, /handleSalesBarcode\(barcode\)/);
  assert.match(app, /addToCart\(resolution\.product\)/);
  assert.match(app, /const existing = currentCart\.find/);
  assert.match(app, /setWeightedProduct\(product\)/);
  assert.match(app, /is out of stock/);
  assert.match(app, /Product Not Found:/);
});

test("global keyboard wedge capture protects focused form fields", () => {
  assert.match(wedgeHook, /isEditableTarget\(event\.target\)/);
  assert.match(wedgeHook, /detector\.reset\(\)/);
});

test("product scanning populates the barcode without automatically saving", () => {
  assert.match(modules, /data-barcode-input="true"/);
  assert.match(modules, /barcode: normalizeBarcode\(rawBarcode\)/);
  assert.match(modules, /Barcode captured\. Save the product to apply it/);
  assert.doesNotMatch(modules, /handleProductBarcode[\s\S]{0,300}saveProduct/);
});

test("inventory scanning selects a product but does not mutate stock", () => {
  assert.match(modules, /handleInventoryBarcode/);
  assert.match(modules, /product_id: resolution\.product\.id/g);
  assert.match(modules, /No stock was changed/);
  assert.doesNotMatch(modules, /handleInventoryBarcode[\s\S]{0,500}saveAdjustment/);
});

test("camera is permission-on-open, rear-facing, local WASM and cleaned up", () => {
  assert.match(dialog, /getUserMedia/);
  assert.match(dialog, /facingMode: \{ ideal: "environment" \}/);
  assert.match(dialog, /stopMediaStream/);
  assert.match(dialog, /capabilities\?\.torch/);
  assert.match(dialog, /aria-label="Close barcode scanner"/);
  assert.match(dialog, /role="status"/);
  assert.match(detector, /barcode-detector\/ponyfill/);
  assert.match(detector, /zxing-wasm\/reader\/zxing_reader\.wasm\?url/);
  assert.match(manifest, /android\.permission\.CAMERA/);
});

test("scanner overlay covers narrow phone, phone, tablet and desktop", () => {
  assert.match(scannerCss, /@media \(max-width: 720px\)/);
  assert.match(scannerCss, /@media \(max-width: 390px\)/);
  assert.match(scannerCss, /safe-area-inset-top/);
  assert.match(scannerCss, /safe-area-inset-bottom/);
});
