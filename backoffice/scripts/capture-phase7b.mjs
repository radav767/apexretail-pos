// Capture the real React screens using preview-only synthetic API adapters.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { dirname } from "node:path";

const modulePath = process.env.PLAYWRIGHT_MODULE;
if (!modulePath) throw new Error("Set PLAYWRIGHT_MODULE to an installed Playwright module");
const { chromium } = await import(pathToFileURL(modulePath).href);
const output = resolve(process.env.PHASE7B_PREVIEW_OUTPUT || "../../artifacts/phase7b-20261019");
await mkdir(output, { recursive: true });
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const servers = [];
async function ensureServer(project, port) {
  const endpoint = `http://127.0.0.1:${port}/`;
  try { if ((await fetch(endpoint)).ok) return; } catch {}
  const server = spawn(process.execPath, [resolve(root, project, "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", String(port), "--strictPort"], { cwd: resolve(root, project), stdio: "ignore" });
  servers.push(server);
  for (let attempt = 0; attempt < 50; attempt++) {
    if (server.exitCode !== null) throw new Error(`${project} preview exited before listening`);
    try { if ((await fetch(endpoint)).ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error(`${project} preview did not become ready`);
}
await Promise.all([ensureServer("backoffice", 5178), ensureServer("pos-web", 5179)]);
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE || undefined, args: ["--no-sandbox"] });
const images = [];
const checks = [];
const views = ["home", "employees", "roles", "permissions", "activity", "assignments"];
try {
  for (const [device, width, height] of [["desktop", 1440, 1000], ["tablet", 820, 1180], ["android", 390, 844], ["narrow", 320, 740]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("https://**/*", route => route.abort());
    for (const view of views) {
      const url = `http://127.0.0.1:5178/tests/visual-phase7b.html?employees_view=${view}`;
      assert.equal((await page.goto(url)).status(), 200);
      await page.locator(".phase7b-header b").first().waitFor();
      await page.waitForFunction(() => document.querySelector(".phase7b-header b")?.textContent === "3");
      const overflow = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: innerWidth }));
      assert.ok(overflow.scroll <= overflow.width, `${device} ${view}: horizontal overflow ${JSON.stringify(overflow)}`);
      assert.deepEqual(errors, []);
      checks.push({ device, view, width, overflow: false, javascriptErrors: 0 });
      if (device === "desktop" || device === "android" || (device === "tablet" && view === "employees")) {
        const filename = `backoffice-${view}-${device}.png`;
        await page.screenshot({ path: resolve(output, filename), fullPage: true });
        images.push({ filename, title: `Backoffice ${view} · ${device}` });
      }
    }
    // Exercise real feature navigation and the browser Back button.
    await page.goto("http://127.0.0.1:5178/tests/visual-phase7b.html");
    await page.getByRole("button", { name: /Roles Built-in and custom roles/ }).click();
    await page.waitForURL("**employees_view=roles");
    await page.goBack();
    await page.getByRole("heading", { name: "Employees & Permissions", exact: true }).waitFor();
    await page.close();
  }
  for (const [device, width, height] of [["desktop", 1440, 1000], ["android", 390, 844], ["narrow", 320, 740]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.route("https://**/*", route => route.abort());
    assert.equal((await page.goto("http://127.0.0.1:5179/tests/visual-phase7b.html")).status(), 200);
    await page.getByRole("dialog").waitFor();
    const bounds = await page.getByRole("dialog").boundingBox();
    assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width);
    const filename = `pos-manager-approval-${device}.png`;
    await page.screenshot({ path: resolve(output, filename), fullPage: true });
    images.push({ filename, title: `POS manager approval · ${device}` });
    await page.getByLabel("Manager PIN").fill("9876");
    assert.equal(await page.getByLabel("Manager PIN").getAttribute("type"), "password");
    await page.getByRole("button", { name: "Authorize" }).click();
    if (device === "desktop") {
      const sessions = await page.evaluate(async () => {
        const { api } = await import("/src/api/client.ts");
        let capturedHeader;
        api.defaults.adapter = async (config) => {
          capturedHeader = config.headers.Authorization;
          return { data: { ok: true }, status: 200, statusText: "OK", headers: {}, config };
        };
        localStorage.setItem("employee_token", "previous-cashier-token");
        localStorage.setItem("employee_id", "previous-cashier");
        const logout = api.post("/employees/session/logout");
        localStorage.removeItem("employee_token");
        localStorage.removeItem("employee_id");
        await logout;
        let rejectLogout;
        api.defaults.adapter = config => new Promise((_resolve, reject) => {
          rejectLogout = () => reject({ isAxiosError: true, config, response: { status: 401, data: { detail: "Old session expired" } } });
        });
        localStorage.setItem("employee_token", "previous-cashier-token");
        const lateLogout = api.post("/employees/session/logout").catch(() => {});
        localStorage.setItem("employee_token", "new-cashier-token");
        localStorage.setItem("employee_id", "new-cashier");
        rejectLogout();
        await lateLogout;
        const survives = localStorage.getItem("employee_token") === "new-cashier-token";
        api.defaults.adapter = async config => { throw { isAxiosError: true, config, response: { status: 401, data: { detail: "Session revoked" } } }; };
        await api.get("/sales").catch(() => {});
        return { capturedHeader, survives, rejectedSessionCleared: !localStorage.getItem("employee_token") };
      });
      assert.equal(sessions.capturedHeader, "Bearer previous-cashier-token");
      assert.equal(sessions.survives, true);
      assert.equal(sessions.rejectedSessionCleared, true);
    }
    await page.close();
  }
  await writeFile(resolve(output, "responsive-checks.json"), JSON.stringify({ checks, managerApprovalWidths: [1440, 390, 320], navigation: "PASS", cashierLogoutIdentity: "PASS", staleLogoutDoesNotClearNewSession: "PASS", revokedSessionFailsClosed: "PASS", data: "synthetic only" }, null, 2));
  const cards = images.map(({ filename, title }) => `<figure><a href="${filename}"><img src="${filename}" alt="${title}" loading="lazy"></a><figcaption>${title}</figcaption></figure>`).join("");
  await writeFile(resolve(output, "index.html"), `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Phase 7B preview</title><style>body{margin:0;padding:22px;background:#f5f7f8;color:#20252b;font:16px system-ui}h1{color:#07583b}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,400px),1fr));gap:18px}figure{margin:0;padding:12px;background:white;border:1px solid #dce5df;border-radius:16px}img{width:100%;max-height:650px;object-fit:contain;object-position:top}figcaption{padding:12px 0;font-weight:700}a{color:#07583b}</style><h1>Phase 7B · Employees & permissions</h1><p>Actual development screens with synthetic preview data. Select an image for its original PNG.</p><main>${cards}</main></html>`);
  console.log(`PASS: ${checks.length} responsive page checks, browser Back on four viewports, manager approval on three viewports. ${images.length} PNG screenshots in ${output}`);
} finally {
  await browser.close();
  for (const server of servers) server.kill();
}
