import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");

test("PIN login submits the durable device identity and current session", () => {
  assert.match(appSource, /const storedIdentity = getPinLoginDeviceIdentity\(companyId\)/);
  assert.match(appSource, /\.\.\.storedIdentity/);
});

test("a direct-login conflict retains its terminal for explicit migration", () => {
  assert.match(appSource, /setTakeoverSelection\(/);
  assert.match(appSource, /attemptedSelection\.shop_id && attemptedSelection\.device_id/);
  assert.match(appSource, /loginWithEmployeePin\(\{ \.\.\.target, takeover: true \}\)/);
  assert.match(appSource, />Take over this session<\/button>/);
});

test("cancelling migration clears the retained target", () => {
  assert.match(
    appSource,
    /setTakeoverPrompt\(false\); setTakeoverSelection\(null\);/,
  );
});

test("device synchronization refreshes the durable shop assignment", () => {
  assert.match(appSource, /localStorage\.setItem\("shop_id", synchronizedShopId\)/);
  assert.match(appSource, /device\?\.friendly_name \|\| device\?\.name/);
});
