import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { spawn } from "node:child_process";

const root = resolve(import.meta.dirname, "../..");
const output = resolve(process.env.PHASE7C_PREVIEW_OUTPUT || resolve(root, "phase7c-evidence/preview-evidence"));
await mkdir(output, { recursive: true });
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const port = 5187;
const server = spawn(process.execPath, [resolve(root, "backoffice/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", String(port), "--strictPort"], { cwd: resolve(root, "backoffice"), stdio: "ignore" });
let browser;
const checks = [], images = [];
try {
  for (let i = 0; i < 80; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/`)).ok) break; } catch {} await new Promise(r => setTimeout(r, 200)); }
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE, args: ["--no-sandbox"] });
  for (const [device, width, height] of [["desktop", 1440, 1000], ["tablet", 820, 1180], ["android", 390, 844], ["narrow", 320, 740]]) {
    for (const app of ["pos", "backoffice"]) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      page.on("pageerror", e => errors.push(e.message));
      await page.route("https://**/*", route => route.abort());
      for (const view of ["home", "stations", "routes", "queue"]) {
        await page.goto(`http://127.0.0.1:${port}/tests/visual-phase7c.html?app=${app}&printer_view=${view}`);
        await page.locator(".printer-management h2").waitFor();
        if (view !== "home") await page.getByRole("option", { name: /Front counter/ }).waitFor({ state: "attached" });
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
        assert.equal(overflow, false, `${app} ${view} ${device} overflows`);
        assert.deepEqual(errors, []);
        checks.push({ app, view, device, width, overflow: false, errors: 0 });
        if (device !== "narrow" && (device !== "tablet" || view === "home")) {
          const filename = `${app}-${view}-${device}.png`;
          await page.screenshot({ path: resolve(output, filename), fullPage: true }); images.push(filename);
        }
      }
      await page.goto(`http://127.0.0.1:${port}/tests/visual-phase7c.html?app=${app}`);
      await page.getByRole("button", { name: /Product routing/ }).click();
      await page.waitForURL("**printer_view=routes");
      await page.goBack();
      await page.getByRole("button", { name: /Printer stations/ }).waitFor();
      await page.goto(`http://127.0.0.1:${port}/tests/visual-phase7c.html?restricted=true`);
      await page.locator(".printer-feature-grid").waitFor();
      assert.equal(await page.getByRole("button", { name: /Product routing/ }).count(), 0);
      await page.close();
    }
  }
  const page = await browser.newPage();
  await page.route("https://**/*", route => route.abort());
  await page.goto(`http://127.0.0.1:${port}/tests/visual-phase7c.html`);
  await page.waitForFunction(() => Boolean(window.__phase7cPrinting));
  const delivery = await page.evaluate(async () => {
    const p = window.__phase7cPrinting;
    const makeJob = id => ({ id, kind: "kot", status: "pending", payload: window.__phase7cPayload });
    let sent = 0;
    const requests = [];
    const deps = { client: { post: async (url, data) => { requests.push({ url, data }); return { data: {} }; } }, transport: async () => { sent++; } };
    await Promise.all([p.deliverJob(makeJob("same"), deps), p.deliverJob(makeJob("same"), deps)]);
    if (sent !== 1) throw Error("Duplicate local sends");
    await p.deliverJob({ ...makeJob("uncertain"), status: "uncertain" }, deps);
    if (sent !== 1) throw Error("Uncertain auto-retried");
    const failureRequests = [];
    try { await p.deliverJob(makeJob("native-fails"), { client: { post: async (url, data) => { failureRequests.push({ url, data }); return { data: {} }; } }, transport: async () => { throw Error("Cable removed"); } }); } catch {}
    if (failureRequests.at(-1).data.outcome !== "uncertain") throw Error("Failure not quarantined");
    let called = false;
    try { await p.deliverJob(makeJob("claim-times-out"), { client: { post: async () => { throw Error("Timeout"); } }, transport: async () => { called = true; } }); } catch {}
    if (called) throw Error("Print happened without confirmed claim");
    localStorage.setItem("company_id", "synthetic-company"); localStorage.setItem("employee_id", "cashier"); localStorage.setItem("device_id", "device"); localStorage.setItem("offline_sales", "financial-sentinel");
    p.rememberPrintIntent("synthetic-company", "offline-sale", true);
    await p.flushPrintIntents();
    if (p.getOfflinePrintReviews("synthetic-company").length !== 1) throw Error("Offline review lost");
    localStorage.setItem("employee_id", "another-cashier");
    if (p.getOfflinePrintReviews("synthetic-company").length !== 0) throw Error("Cashier inherited print intent");
    localStorage.setItem("employee_id", "cashier");
    await p.resolveOfflinePrintReview("synthetic-company", "offline-sale", "already_printed", "Verified paper receipt");
    if (localStorage.getItem("offline_sales") !== "financial-sentinel") throw Error("Financial queue changed");
    if (p.getOfflinePrintReviews("synthetic-company").length !== 0) throw Error("Audited review not resolved");
    const html = p.renderTicket({ ...window.__phase7cPayload, notes: '<img src=x onerror="alert(1)">\x1b@' }, "58mm");
    if (html.includes("<img") || html.includes("\x1b")) throw Error("Ticket injection");
    for (const width of ["58mm", "80mm"]) {
      if (!p.renderTicket(window.__phase7cPayload, width).includes(`size:${width}`)) throw Error("Paper width missing");
    }
    if (requests.some(r => !r.url.startsWith("/printing/"))) throw Error("Print issued a business write");
    return { concurrentDuplicateBlocked: true, uncertainNotRetried: true, claimTimeoutNoPrint: true, nativeFailureQuarantined: true, offlineReviewPreserved: true, cashierIsolation: true, financialQueueUnchanged: true, ticketEscaping: true, paperWidths: ["58mm", "80mm"] };
  });
  for (const width of ["58mm", "80mm"]) {
    const html = await page.evaluate(width => window.__phase7cPrinting.renderTicket(window.__phase7cPayload, width), width);
    await writeFile(resolve(output, `kot-${width}.html`), html);
    const thermal = await browser.newPage({ viewport: { width: width === "58mm" ? 230 : 320, height: 640 } });
    await thermal.setContent(html);
    assert.equal(await thermal.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    const filename = `kot-${width}.png`;
    await thermal.screenshot({ path: resolve(output, filename), fullPage: true }); images.push(filename);
    await thermal.close();
  }
  await writeFile(resolve(output, "responsive-checks.json"), JSON.stringify({ checks, delivery, syntheticOnly: true, screenshots: images.length }, null, 2));
  await writeFile(resolve(output, "index.html"), `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Phase 7C review</title><style>body{font:16px system-ui;background:#f5f7f8;color:#20252b;margin:20px}h1{color:#07583b}img{width:100%;height:auto;border-radius:12px;border:1px solid #dde4df}article{max-width:1100px;margin:30px auto}a{color:#07583b}</style></head><body><h1>ApexRetail · Printer management</h1><p>Actual React screens · Synthetic preview data · Not deployed</p>${images.map(i => `<article><h2>${i.replaceAll("-", " ").replace(".png", "")}</h2><a href="${i}"><img loading="lazy" src="${i}" alt="${i}"></a></article>`).join("")}</body></html>`);
  console.log(JSON.stringify({ responsiveChecks: checks.length, screenshots: images.length, delivery }, null, 2));
} finally { if (browser) await browser.close(); server.kill("SIGTERM"); }
