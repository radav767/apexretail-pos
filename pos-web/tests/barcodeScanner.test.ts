import assert from "node:assert/strict";

import {
  createDuplicateScanGate,
  normalizeBarcode,
  resolveBarcodeProduct,
} from "../src/barcode/barcode.ts";
import { cameraErrorMessage, stopMediaStream } from "../src/barcode/cameraLifecycle.ts";
import { KeyboardWedgeDetector } from "../src/barcode/keyboardWedge.ts";

assert.equal(normalizeBarcode("  000 Ab-C/ 9  "), "000 Ab-C/ 9");
assert.notEqual(normalizeBarcode("ABC"), normalizeBarcode("abc"));

const products = [
  { id: "one", name: "One", barcode: "000123", active: true },
  { id: "two", name: "Two", barcode: "Ab C-9", active: true },
  { id: "off", name: "Off", barcode: "OFF", active: false },
];
assert.equal(resolveBarcodeProduct(products, " 000123 ").status, "found");
assert.equal(resolveBarcodeProduct(products, "000123").status, "found");
assert.equal(resolveBarcodeProduct(products, "ab c-9").status, "not_found");
assert.equal(resolveBarcodeProduct(products, "OFF").status, "not_found");
assert.equal(resolveBarcodeProduct(products, "missing").status, "not_found");

const wedge = new KeyboardWedgeDetector();
let result: string | null = null;
for (const [index, key] of [..."000123"].entries()) {
  result = wedge.feed({ key, timestamp: 100 + index * 12 });
}
result = wedge.feed({ key: "Enter", timestamp: 180 });
assert.equal(result, "000123");

const human = new KeyboardWedgeDetector();
for (const [index, key] of [..."123456"].entries()) {
  result = human.feed({ key, timestamp: 100 + index * 180 });
}
assert.equal(human.feed({ key: "Enter", timestamp: 1_300 }), null);

const modified = new KeyboardWedgeDetector();
modified.feed({ key: "1", timestamp: 10 });
assert.equal(modified.feed({ key: "c", timestamp: 20, modifier: true }), null);
assert.equal(modified.feed({ key: "Enter", timestamp: 30 }), null);

const gate = createDuplicateScanGate(1_000);
assert.equal(gate("1234", 100), "1234");
assert.equal(gate("1234", 200), null);
assert.equal(gate("1234", 1_101), "1234");

assert.match(cameraErrorMessage({ name: "NotAllowedError" }), /permission was denied/);
assert.match(cameraErrorMessage({ name: "NotFoundError" }), /No usable camera/);

let stopped = 0;
stopMediaStream({
  getTracks: () => [{ stop: () => { stopped += 1; } }, { stop: () => { stopped += 1; } }],
} as unknown as MediaStream);
assert.equal(stopped, 2);

console.log("PASS: barcode identity, lookup, wedge timing, duplicate suppression and camera lifecycle");
