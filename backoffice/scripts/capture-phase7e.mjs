// Real React components, synthetic adapters, local servers only. Never deploys.
import assert from "node:assert/strict";
import { mkdir, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { spawn, spawnSync } from "node:child_process";
const root = resolve(import.meta.dirname, "../..");
const output = resolve(root, "phase7e-evidence/screenshots");
await mkdir(output, { recursive: true });
for (const [phase, folder] of [["7b", "employees"], ["7c", "printers"], ["7d", "business"]]) {
  if (process.env.PHASE7E_REUSE_BASE_CAPTURES === "1") {
    assert.ok((await readdir(resolve(output, folder))).some(name => name.endsWith(".png")), `Missing prior ${phase} capture evidence`);
    continue;
  }
  const result = spawnSync(process.execPath, [resolve(root, `backoffice/scripts/capture-phase${phase}.mjs`)], {
    cwd: root, env: { ...process.env, [`PHASE${phase.toUpperCase()}_PREVIEW_OUTPUT`]: resolve(output, folder) }, encoding: "utf8", timeout: 240000,
  });
  console.log(result.stdout); if (result.status !== 0) throw new Error(result.stderr || `Phase ${phase} capture failed`);
}
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const servers = [];
let browser;
const checks = [];
try {
  for (const [project, port] of [["pos-web", 5190], ["backoffice", 5191]]) {
    servers.push(spawn(process.execPath, [resolve(root, project, "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", String(port), "--strictPort"], { cwd: resolve(root, project), stdio: "ignore" }));
    let ready = false;
    for (let i = 0; i < 80; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/`)).ok) { ready = true; break; } } catch {} await new Promise(r => setTimeout(r, 200)); }
    assert.ok(ready, `${project} local preview unavailable`);
  }
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE, headless: true, args: ["--no-sandbox"] });
  for (const [device, width, height] of [["desktop", 1440, 1000], ["tablet", 820, 1180], ["android", 390, 844], ["narrow", 320, 740]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.route("https://**/*", route => route.abort());
    for (const feature of ["categories", "composite-products", "product-variants", "units", "price-levels", "barcode-labels", "import-export"]) {
      await page.goto(`http://127.0.0.1:5190/tests/visual-phase7a.html?feature=${feature}`);
      await page.locator(".pos-product-tools").waitFor();
      await page.waitForTimeout(400);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${feature}/${device} overflows`);
      if (device !== "narrow") await page.screenshot({ path: resolve(output, `products-${feature}-${device}.png`), fullPage: true });
      checks.push({ feature, device, overflow: false });
    }
    await page.goto("http://127.0.0.1:5191/tests/visual-phase7d.html?business_view=orders&offline=1");
    await page.getByText("Offline order drafts", { exact: true }).click();
    const panel = page.locator("details").filter({ has: page.getByText("Offline order drafts", { exact: true }) }).first();
    await panel.locator("select").first().selectOption("meal");
    await panel.getByRole("button", { name: "Add draft item", exact: true }).click();
    await page.context().setOffline(true);
    await panel.getByRole("button", { name: "Save unpaid draft", exact: true }).click();
    await panel.getByText("Draft saved on this device. Not sent to the kitchen.", { exact: true }).waitFor();
    const retained = await page.evaluate(() => Object.keys(localStorage).filter(key => key.startsWith("apexretail_unpaid_order_outbox_v1:")).length);
    assert.equal(retained, 1);
    assert.equal(await panel.getByRole("button", { name: "Review & synchronize drafts" }).isDisabled(), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: resolve(output, `offline-draft-${device}.png`), fullPage: true });
    await page.context().setOffline(false); await page.close();
  }
  await writeFile(resolve(output, "phase7e-extra-checks.json"), JSON.stringify({ checks, offlineDraftCreation: true, realOfflinePaymentsTested: false, syntheticOnly: true }, null, 2));
  async function images(folder, prefix = "") {
    const results = [];
    for (const entry of await readdir(folder, { withFileTypes: true })) {
      const relative = prefix + entry.name;
      if (entry.isDirectory()) results.push(...await images(resolve(folder, entry.name), relative + "/"));
      else if (entry.name.endsWith(".png")) results.push(relative);
    }
    return results;
  }
  const all = await images(output);
  await writeFile(resolve(output, "index.html"), `<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Phase 7E review</title><style>body{font:16px system-ui;background:#f5f7f8;color:#20252b;margin:16px}h1{color:#07583b}article{max-width:1100px;margin:24px auto}img{width:100%;border:1px solid #dde4df;border-radius:12px}</style><h1>ApexRetail · Phase 7E development</h1><p>Actual React components · Synthetic data only · Not deployed</p>${all.map(path => `<article><h2>${path}</h2><a href="${path}"><img loading="lazy" src="${path}" alt="${path}"></a></article>`).join("")}`);
  console.log(JSON.stringify({ screenshots: all.length, extraChecks: checks.length, offlineDraftCreation: true }));
} finally { await browser?.close(); for (const server of servers) server.kill("SIGTERM"); }
