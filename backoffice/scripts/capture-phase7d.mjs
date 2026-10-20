import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { spawn } from "node:child_process";

const root = resolve(import.meta.dirname, "../..");
const output = resolve(process.env.PHASE7D_PREVIEW_OUTPUT || resolve(root, "phase7d-evidence/preview"));
await mkdir(output, { recursive: true });
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const port = 5188;
const server = spawn(process.execPath, [resolve(root, "backoffice/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", String(port), "--strictPort"], { cwd: resolve(root, "backoffice"), stdio: "ignore" });
let browser;
const checks = [], images = [];
try {
  for (let i = 0; i < 80; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/`)).ok) break; } catch {} await new Promise(r => setTimeout(r, 200)); }
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE, args: ["--no-sandbox"] });
  for (const [device, width, height] of [["desktop", 1440, 1000], ["tablet", 820, 1180], ["android", 390, 844], ["narrow", 320, 740]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.route("https://**/*", route => route.abort());
    for (const [view, profile] of [["home", "restaurant"], ["tables", "restaurant"], ["orders", "restaurant"], ["kitchen", "restaurant"], ["bar", "restaurant"], ["rooms", "hospitality"], ["batches", "pharmacy"], ["quotations", "wholesale"], ["profile", "restaurant"], ["reports", "restaurant"]]) {
      await page.goto(`http://127.0.0.1:${port}/tests/visual-phase7d.html?app=${device === "android" ? "pos" : "backoffice"}&profile=${profile}&business_view=${view}`);
      await page.waitForFunction(() => document.querySelector(".business-eyebrow")?.textContent !== "ApexRetail");
      if (["orders", "quotations"].includes(view)) await page.getByRole("button", { name: /O-SYN-0042/ }).waitFor();
      if (view === "tables") await page.getByRole("button", { name: /Table 12/ }).waitFor();
      if (view === "kitchen") await page.getByText("Main kitchen").first().waitFor();
      if (view === "reports") await page.getByRole("button", { name: "View report" }).click();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      assert.equal(overflow, false, `${view} ${device} overflow`); assert.deepEqual(errors, []);
      checks.push({ view, profile, device, width, overflow: false, errors: 0 });
      if (device === "desktop" || device === "android" || (device === "tablet" && ["home", "tables", "kitchen"].includes(view))) {
        const filename = `${view}-${device}.png`; await page.screenshot({ path: resolve(output, filename), fullPage: true }); images.push(filename);
      }
      if (view === "orders") {
        await page.getByRole("button", { name: /O-SYN-0042/ }).click();
        await page.getByRole("heading", { name: "O-SYN-0042" }).waitFor();
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        if (device === "desktop" || device === "android") { const filename = `open-bill-${device}.png`; await page.screenshot({ path: resolve(output, filename), fullPage: true }); images.push(filename); }
      }
    }
    await page.goto(`http://127.0.0.1:${port}/tests/visual-phase7d.html`);
    await page.getByRole("button", { name: /Tables & floors Open/ }).click(); await page.waitForURL("**business_view=tables"); await page.goBack();
    await page.getByRole("button", { name: /Business profile Open/ }).waitFor();
    await page.context().setOffline(true); await page.getByText("Live orders and payment require a connection.", { exact: false }).waitFor();
    assert.ok(await page.getByRole("button", { name: "Refresh", exact: true }).isDisabled());
    await page.context().setOffline(false);
    await page.goto(`http://127.0.0.1:${port}/tests/visual-phase7d.html?role=kitchen`);
    await page.getByRole("button", { name: /Kitchen display Open/ }).waitFor();
    assert.equal(await page.getByRole("button", { name: /Open orders Open/ }).count(), 0);
    const access = await page.evaluate(() => ({ kitchenSales: window.__phase7dAccess.canProcessSales({ sales: false, kitchen_view: true }), kitchenOperations: window.__phase7dAccess.canAccessOperations({ sales: false, kitchen_view: true }), explicitSalesDenial: window.__phase7dAccess.canProcessSales({ sales: true, sales_process: false }), legacyRetail: window.__phase7dAccess.canProcessSales({ sales: true }) }));
    assert.deepEqual(access, { kitchenSales: false, kitchenOperations: true, explicitSalesDenial: false, legacyRetail: true });
    await page.close();
  }
  await writeFile(resolve(output, "responsive-checks.json"), JSON.stringify({ checks, browserBack: true, offlineWriteControlsDisabled: true, kitchenCannotCheckout: true, syntheticOnly: true, screenshots: images.length }, null, 2));
  await writeFile(resolve(output, "index.html"), `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Phase 7D review</title><style>body{font:16px system-ui;background:#f5f7f8;color:#20252b;margin:20px}h1{color:#07583b}img{width:100%;height:auto;border-radius:12px;border:1px solid #dde4df}article{max-width:1100px;margin:30px auto}a{color:#07583b}</style></head><body><h1>ApexRetail · Phase 7D</h1><p>Actual React screens · Synthetic data only · Not deployed</p>${images.map(i => `<article><h2>${i.replaceAll("-", " ").replace(".png", "")}</h2><a href="${i}"><img loading="lazy" src="${i}" alt="${i}"></a></article>`).join("")}</body></html>`);
  console.log(JSON.stringify({ checks: checks.length, screenshots: images.length, browserBack: true, offlineProtected: true, kitchenCannotCheckout: true }, null, 2));
} finally { if (browser) await browser.close(); server.kill("SIGTERM"); }
