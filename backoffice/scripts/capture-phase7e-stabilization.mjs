// Browser actions use actual React components plus synthetic API acknowledgements.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { spawn } from "node:child_process";
const root = resolve(import.meta.dirname, "../..");
const output = resolve(root, "phase7e-evidence/stabilization/preview"); await mkdir(output, { recursive: true });
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const base = "http://127.0.0.1:5193/tests/visual-phase7e-stabilization.html";
const server = spawn(process.execPath, [resolve(root, "backoffice/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5193", "--strictPort"], { cwd: resolve(root, "backoffice"), stdio: "ignore" });
let browser; const checks = []; const images = [];
try {
  for (let i=0;i<80;i++) { try { if ((await fetch(base)).ok) break; } catch {} await new Promise(r => setTimeout(r,200)); }
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE, headless: true, args: ["--no-sandbox"] });
  for (const [device,width,height] of [["desktop",1440,1000],["tablet",820,1180],["android",390,844],["narrow",320,740]]) {
    const context = await browser.newContext({ viewport: { width,height } }); let page = await context.newPage(); const errors=[];
    context.on("page", p => p.on("pageerror", e => errors.push(e.message)));
    page.on("pageerror", e => errors.push(e.message)); page.on("dialog", d => d.accept());
    await context.route("https://**/*", route => route.abort());
    await page.goto(`${base}?timeout=1`); await page.getByText("Receive / return / dispose batch stock",{exact:true}).click();
    await page.getByLabel(/^Product/).selectOption("synthetic-medicine");
    await page.getByLabel(/^Variant/).selectOption("strength-a");
    await page.getByLabel("Batch code").fill("SYN-LOT-250"); await page.getByLabel("Expiry date").fill("2027-06-30");
    await page.getByLabel("Reason",{exact:true}).fill("Synthetic received variant inspection");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false);
    const file=`variant-batches-${device}.png`; await page.screenshot({path:resolve(output,file),fullPage:true}); images.push(file);
    await page.getByRole("button",{name:"Confirm stock operation",exact:true}).click();
    await page.getByRole("button",{name:"Retry original stock request",exact:true}).waitFor();
    await page.reload();
    await page.getByText("Receive / return / dispose batch stock",{exact:true}).click();
    // Fixture replays its timeout after a page restart; the pending command must
    // remain the original identity through both retries.
    await page.getByRole("button",{name:"Retry original stock request",exact:true}).click();
    await page.getByRole("button",{name:"Retry original stock request",exact:true}).click();
    await page.getByText("Stock operation confirmed.",{exact:true}).waitFor();
    const stock = await page.evaluate(() => ({ calls:window.__stabilizationCalls, count:window.__stabilizationReceipts() }));
    assert.equal(stock.calls.length,2); assert.equal(stock.count,1);
    assert.equal(stock.calls[0].payload.request_id,stock.calls[1].payload.request_id); assert.equal(stock.calls[0].payload.variant_id,"strength-a");
    checks.push({device,feature:"variant stock",formSubmission:true,restartRetry:true,originalIdentity:true,oneSimulatedMovement:true,overflow:false});
    await page.goto(`${base}?view=recovery&seed=1&conflict=1`);
    await page.getByText("Offline order drafts",{exact:true}).click(); await page.getByText("pending",{exact:true}).waitFor();
    assert.equal(await page.getByRole("button",{name:"Save unpaid draft",exact:true}).count(),0);
    await page.getByRole("button",{name:"Review & synchronize drafts",exact:true}).click(); await page.getByText("review",{exact:true}).waitFor();
    const original = await page.evaluate(() => Object.entries(localStorage).find(([k])=>k.startsWith("apexretail_unpaid_order_outbox_v1:"))[1]);
    await context.setOffline(true); assert.equal(await page.getByRole("button",{name:"Check server confirmation",exact:true}).isDisabled(),true);
    const recovery=`offline-recovery-${device}.png`; await page.screenshot({path:resolve(output,recovery),fullPage:true}); images.push(recovery);
    await context.setOffline(false); await page.close(); page = await context.newPage();
    await page.goto(`${base}?view=recovery`); await page.getByText("Offline order drafts",{exact:true}).click(); await page.getByText("review",{exact:true}).waitFor();
    assert.equal(await page.evaluate(() => Object.entries(localStorage).find(([k])=>k.startsWith("apexretail_unpaid_order_outbox_v1:"))[1]),original);
    await page.getByRole("button",{name:"Check server confirmation",exact:true}).click(); await page.getByText("acknowledged",{exact:true}).waitFor();
    const restored = await page.evaluate(() => window.__stabilizationCalls[0]);
    assert.equal(restored.endpoint,"/operations/offline/drafts/recover"); assert.equal(restored.payload.captured_at,"2026-10-19T12:00:00Z");
    await page.goto(`${base}?view=recovery&employee=other-cashier`); await page.getByText("Offline order drafts",{exact:true}).click();
    assert.equal(await page.getByText("acknowledged",{exact:true}).count(),0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false); assert.deepEqual(errors,[]);
    checks.push({device,feature:"offline recovery",apiUnavailableStartup:true,reopenedPageRetained:true,conflictRetained:true,cashierIsolation:true,recoverOriginalTimestamp:true,newDraftsBlockedUntilProfileVerified:true,overflow:false});
    await context.close();
  }
  // A malformed HTTP-200 body must never acknowledge a stock operation.
  const page = await browser.newPage(); page.on("dialog",d=>d.accept()); await page.goto(`${base}?malformed=1`);
  await page.getByText("Receive / return / dispose batch stock",{exact:true}).click();
  await page.getByLabel(/^Product/).selectOption("synthetic-medicine"); await page.getByLabel(/^Variant/).selectOption("strength-b");
  await page.getByLabel("Batch code").fill("SYN-250"); await page.getByLabel("Expiry date").fill("2027-06-30"); await page.getByLabel("Reason",{exact:true}).fill("Synthetic malformed acknowledgement test");
  await page.getByRole("button",{name:"Confirm stock operation",exact:true}).click(); await page.getByRole("button",{name:"Retry original stock request",exact:true}).waitFor();
  assert.equal(await page.getByRole("button",{name:"New stock operation",exact:true}).count(),0); checks.push({feature:"stock acknowledgement",malformed200Retained:true}); await page.close();
  await writeFile(resolve(output,"checks.json"),JSON.stringify({checks,syntheticOnly:true,physicalAndroidTested:false,screenshots:images.length},null,2));
  await writeFile(resolve(output,"index.html"),`<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Phase 7E stabilization</title><style>body{font:16px system-ui;margin:16px;background:#f5f7f8;color:#20252b}article{max-width:1100px;margin:24px auto}img{width:100%;border:1px solid #ddd;border-radius:12px}h1{color:#07583b}</style><h1>ApexRetail · Stabilization review</h1><p>Actual React components · Synthetic data · Not deployed</p>${images.map(name=>`<article><h2>${name}</h2><a href="${name}"><img loading="lazy" src="${name}"></a></article>`).join("")}`);
  console.log(JSON.stringify({checks:checks.length,screenshots:images.length,syntheticOnly:true}));
} finally { await browser?.close(); server.kill("SIGTERM"); }
