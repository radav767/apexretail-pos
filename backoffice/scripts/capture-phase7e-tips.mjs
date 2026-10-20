import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { spawn } from "node:child_process";
const root = resolve(import.meta.dirname, "../..");
const output = resolve(root, "phase7e-evidence/tips/preview"); await mkdir(output, { recursive: true });
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const server = spawn(process.execPath, [resolve(root, "backoffice/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5192", "--strictPort"], { cwd: resolve(root, "backoffice"), stdio: "ignore" });
let browser; const checks = []; const images = [];
try {
  for (let n=0;n<80;n++) { try { if ((await fetch("http://127.0.0.1:5192/")).ok) break; } catch {} await new Promise(r => setTimeout(r,200)); }
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE, headless: true, args: ["--no-sandbox"] });
  for (const [device,width,height] of [["desktop",1440,1000],["tablet",820,1180],["android",390,844],["narrow",320,740]]) {
    const page = await browser.newPage({ viewport: { width,height } }); const errors=[];
    page.on("pageerror", e => errors.push(e.message)); page.on("dialog", dialog => dialog.accept());
    await page.route("https://**/*", route => route.abort());
    await page.goto("http://127.0.0.1:5192/tests/visual-phase7e-tips.html");
    await page.getByRole("option", { name: "Reviewed service charge", exact: true }).waitFor({ state: "attached" });
    await page.locator("select").first().selectOption("shared");
    await page.getByLabel("Tip weight Jamie Patel").fill("1"); await page.getByLabel("Tip weight Alex Morgan").fill("2");
    await page.getByRole("button", { name: "Save policy", exact: true }).click();
    await page.getByText("Tip policy saved. Existing entitlements are unchanged.").waitFor();
    const saved = await page.evaluate(() => window.__tipCalls.filter(c => c.method === "put").at(-1).data);
    assert.equal(saved.policy,"shared"); assert.deepEqual(Object.values(saved.weights).sort(),[1,2]);
    await page.getByRole("button", { name: "View tip report", exact:true }).click(); await page.getByText("Employee outstanding balances (all time)").waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false);
    await page.screenshot({ path:resolve(output,`tips-settings-${device}.png`),fullPage:true }); images.push(`tips-settings-${device}.png`);
    const download = page.waitForEvent("download"); await page.getByRole("button",{name:"Export tip totals CSV"}).click(); await download;
    checks.push({ device, view:"settings", policySave:true, report:true, csv:true, overflow:false });
    await page.goto("http://127.0.0.1:5192/tests/visual-phase7e-tips.html?view=pos&timeout=1");
    await page.getByText("Record separate tip payment",{exact:true}).click();
    await page.getByLabel("Amount",{exact:true}).fill("2.00"); await page.getByLabel("Reason",{exact:true}).fill("Confirmed synthetic cash tip");
    await page.getByRole("button",{name:"Confirm & record transfer"}).click();
    await page.getByRole("button",{name:"Retry recording original transfer"}).waitFor();
    await page.getByRole("button",{name:"Retry recording original transfer"}).click();
    await page.getByText("Tip transfer recorded. Product sale and stock are unchanged.").waitFor();
    const retry = await page.evaluate(() => ({ calls:window.__tipCalls.filter(c=>c.url.endsWith("/tips/entries")), count:window.__tipReceiptCount() }));
    assert.equal(retry.calls.length,2); assert.equal(retry.calls[0].data.request_id,retry.calls[1].data.request_id); assert.equal(retry.count,1);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false);
    await page.screenshot({path:resolve(output,`tip-recovery-${device}.png`),fullPage:true}); images.push(`tip-recovery-${device}.png`);
    checks.push({device,view:"pos",timeoutRetained:true,sameRequestRetry:true,oneSimulatedReceipt:true,overflow:false});
    await page.goto("http://127.0.0.1:5192/tests/visual-phase7e-tips.html?view=returns");
    await page.getByText("Inspect held customer returns",{exact:true}).click();
    await page.locator("select").first().selectOption("00000000-0000-4000-a000-000000000004");
    await page.getByLabel("Verified lot code").fill("RETURN-SYN-0042"); await page.getByLabel("Verified expiry").fill("2027-01-01");
    await page.getByLabel("Inspection reason").fill("Synthetic packaging and lot inspection");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false);
    await page.screenshot({path:resolve(output,`return-inspection-${device}.png`),fullPage:true}); images.push(`return-inspection-${device}.png`);
    await page.getByRole("button",{name:"Confirm inspection",exact:true}).click(); await page.getByText("Inspection recorded. The original financial refund is unchanged.").waitFor();
    checks.push({device,view:"returns",inspectionSubmit:true,overflow:false}); assert.deepEqual(errors,[]); await page.close();
  }
  await writeFile(resolve(output,"checks.json"),JSON.stringify({checks,syntheticOnly:true,screenshots:images.length},null,2));
  await writeFile(resolve(output,"index.html"),`<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Phase 7E tips and returns</title><style>body{font:16px system-ui;background:#f5f7f8;color:#20252b;margin:16px}article{max-width:1100px;margin:24px auto}img{width:100%;border:1px solid #dce5df;border-radius:12px}h1{color:#07583b}</style><h1>ApexRetail · Tips & returns review</h1><p>Actual React components · Synthetic data · Not deployed</p>${images.map(name=>`<article><h2>${name}</h2><a href="${name}"><img loading="lazy" src="${name}"></a></article>`).join("")}`);
  console.log(JSON.stringify({checks:checks.length,screenshots:images.length,syntheticOnly:true}));
} finally {await browser?.close();server.kill("SIGTERM");}
