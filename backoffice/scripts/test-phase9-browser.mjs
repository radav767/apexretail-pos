import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from '/root/.npm/_npx/420ff84f11983ee5/node_modules/playwright/index.mjs';
const root = fileURLToPath(new URL('..', import.meta.url));
const out = fileURLToPath(new URL('../../artifacts/phase9-fiscal', import.meta.url));
await mkdir(out, { recursive: true });
const server = await createServer({ root, server: { host: '127.0.0.1', port: 18933, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ executablePath: '/tmp/apexretail-pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
const context = await browser.newContext(), errors = [], external = [], checks = [];
await context.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : (external.push(route.request().url()), route.abort()));
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto('http://127.0.0.1:18933/tests/visual-phase9.html');
  await page.getByRole('button', { name: 'Save draft configuration' }).waitFor();
  for (const width of [1440, 820, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({ path: `${out}/fiscal-preparation-${width}.png`, fullPage: true });
    checks.push(`${width}px no horizontal overflow`);
  }
  await page.getByLabel('Taxpayer TIN', { exact: true }).fill('0000000001');
  await page.locator('select').nth(1).selectOption('branch-test');
  await page.locator('select').nth(2).selectOption('register-test');
  await page.getByLabel('Device serial', { exact: true }).fill('SYNTHETIC');
  await page.getByLabel('Registered model', { exact: true }).fill('NOT-REGISTERED');
  await page.getByLabel('Registered model version', { exact: true }).fill('test');
  await page.getByRole('button', { name: 'Save draft configuration' }).click();
  await page.getByText('Draft saved. Fiscal submission remains disabled.', { exact: true }).waitFor();
  const saved = await page.evaluate(() => window.phase9Calls.find(row => row.method === 'put').body);
  assert.equal(saved.expected_version, 0); assert.equal(saved.environment, 'test'); assert.deepEqual(saved.taxes, []);
  assert.ok(!('activation_key' in saved)); checks.push('Draft save uses concurrency version, no default rates or secret fields');
  await page.getByLabel('Draft tax mappings (from FDMS configuration; no default rates)').fill('invalid');
  await page.getByRole('button', { name: 'Save draft configuration' }).click();
  await page.getByText('Invalid tax mapping JSON.', { exact: true }).waitFor();
  checks.push('Malformed tax JSON cannot be saved');
  assert.equal(await page.getByRole('button', { name: 'Submit fiscal receipt' }).count(), 0);
  checks.push('No commissioning or live submission controls');
  await page.goto('http://127.0.0.1:18933/tests/visual-phase9.html?denied=true');
  await page.getByText('Business owner account required.', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Save draft configuration' }).count(), 0);
  checks.push('Denied role cannot render editing controls');
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  checks.push('No external requests or uncaught browser errors');
} catch (error) { process.exitCode = 1; console.error(error); }
finally {
  await writeFile(`${out}/browser-results.json`, JSON.stringify({ passed: !process.exitCode, checks, errors, external, syntheticAdapters: true }, null, 2));
  await browser.close(); await server.close();
  console.log(JSON.stringify({ success: !process.exitCode, checks: checks.length }));
}
