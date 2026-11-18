import { chromium } from '/tmp/apex-phase11-browser-tools/node_modules/playwright/index.mjs';
import { readFileSync, existsSync, writeFileSync } from 'node:fs';
import { resolve, extname } from 'node:path';
import { randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';
const local = 'http://127.0.0.1:18043';
const bo = 'https://backoffice.apexpos.cloud';
const dist = '/tmp/apex-phase11-build-xijhpj7t/backoffice/dist';
const checks = [];
async function api(path, body, headers = {}) {
  const result = await fetch(local + '/api' + path, {method: body ? 'POST' : 'GET', headers: {'Content-Type': 'application/json', ...headers}, body: body ? JSON.stringify(body) : undefined});
  return {status: result.status, data: await result.json()};
}
async function register(name) {
  const email = `phase11-browser-${name}-${randomUUID()}@example.com`;
  const result = await api('/auth/register', {owner_name: 'Synthetic Owner ' + name, owner_pin: '1234', business_name: 'Synthetic Browser ' + name,
    business_type: 'Retail', country: 'Zimbabwe', phone: '000000000', email,
    password: 'synthetic-browser-password', confirm_password: 'synthetic-browser-password',
    base_currency_code: 'USD', base_currency_symbol: '$', base_currency_decimal_places: 2, device_key: randomUUID()});
  assert.equal(result.status, 200); return {...result.data, email:email.toLowerCase()};
}
const a = await register('A'), b = await register('B');
const browser = await chromium.launch({executablePath: '/root/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell', headless: true, args: ['--no-sandbox', '--disable-background-networking']});
const context = await browser.newContext({viewport: {width: 1440, height: 1000}, serviceWorkers: 'block'});
const blocked = [], paths = [], errors = [], calls = [];
await context.route('**/*', async route => {
  const request = route.request(), url = new URL(request.url());
  if (url.origin === 'https://api.apexpos.cloud' && url.pathname.startsWith('/api/')) {
    paths.push(url.pathname);
    const headers = await request.allHeaders(); delete headers.host;
    const result = await fetch(local + url.pathname + url.search, {method: request.method(), headers, body: ['GET','HEAD'].includes(request.method()) ? undefined : request.postData()});
    calls.push({path:url.pathname, method:request.method(), status:result.status});
    return route.fulfill({status: result.status, headers: Object.fromEntries(result.headers), body: Buffer.from(await result.arrayBuffer())});
  }
  if (url.origin === bo || url.origin === 'https://pos.apexpos.cloud') {
    const buildRoot = url.origin === bo ? dist : '/tmp/apex-phase11-browser-dialog-dist';
    let file = resolve(buildRoot, '.' + url.pathname);
    if (!file.startsWith(buildRoot + '/')) file = resolve(buildRoot, 'index.html');
    if (url.pathname === '/' || !extname(url.pathname)) file = resolve(buildRoot, 'index.html');
    if (!existsSync(file)) return route.fulfill({status: 404, body: ''});
    const type = {'.html':'text/html', '.js':'application/javascript', '.css':'text/css', '.wasm':'application/wasm', '.svg':'image/svg+xml'}[extname(file)] || 'application/octet-stream';
    return route.fulfill({status: 200, contentType: type, body: readFileSync(file)});
  }
  blocked.push(url.origin); return route.abort();
});
const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
const stored = () => page.evaluate(() => ({token: sessionStorage.getItem('backoffice_token'), company: sessionStorage.getItem('backoffice_company_id'), persistent: localStorage.getItem('backoffice_token')}));
try {
  await page.goto(bo); await page.getByRole('heading', {name: 'ApexRetail Backoffice'}).waitFor();
  const remember = page.getByRole('checkbox', {name: /Remember Me/}); assert.equal(await remember.isChecked(), false);
  await page.locator('input[type=email]').fill(b.email); await page.locator('input[type=password]').fill('synthetic-browser-password');
  await remember.check(); await page.getByRole('button', {name: 'Login', exact: true}).click();
  await page.waitForFunction(id => sessionStorage.getItem('backoffice_company_id') === id, b.company.id);
  const previous = await stored(); assert.equal(previous.persistent, null);
  let cookie = (await context.cookies('https://api.apexpos.cloud')).find(cookie => cookie.name === '__Host-apex_business_refresh');
  assert(cookie && cookie.httpOnly && cookie.secure && cookie.sameSite === 'Strict' && cookie.expires > Date.now()/1000);
  const oldCookie = cookie.value;
  await page.reload(); await page.getByRole('button', {name:'Log out', exact:true}).first().waitFor();
  await page.waitForFunction(id => sessionStorage.getItem('backoffice_company_id') === id, b.company.id);
  cookie = (await context.cookies('https://api.apexpos.cloud')).find(cookie => cookie.name === '__Host-apex_business_refresh');
  assert.notEqual(cookie.value, oldCookie); checks.push('unchecked default, persistent HttpOnly cookie, refresh restoration and rotation');
  const employeeHeaders = {Authorization:'Bearer ' + a.employee.access_token};
  assert.equal((await api('/auth/handoff', {company_id:a.company.id, branch_id:a.branch.id}, employeeHeaders)).status, 403);
  assert.equal((await api('/auth/handoff', {company_id:a.company.id, branch_id:a.branch.id, owner_email:b.email, owner_password:'synthetic-browser-password'}, employeeHeaders)).status, 403);
  const handoff = await api('/auth/handoff', {company_id:a.company.id, branch_id:a.branch.id, owner_email:a.email, owner_password:'synthetic-browser-password'}, employeeHeaders);
  assert.equal(handoff.status, 200);
  await page.goto(handoff.data.url);
  await page.getByRole('button', {name:'Continue with this account'}).waitFor();
  assert(!page.url().includes('#')); assert((await page.locator('.login-card').innerText()).includes(a.email));
  assert.equal((await stored()).token, null);
  const denied = await api(`/fiscal/${b.company.id}/configuration`, null, {Authorization: 'Bearer ' + previous.token});
  assert.equal(denied.status, 401);
  await page.getByRole('button', {name:'Continue with this account'}).click();
  await page.waitForFunction(id => sessionStorage.getItem('backoffice_company_id') === id, a.company.id);
  assert.equal((await stored()).persistent, null); checks.push('two-owner handoff retires prior account and requires visible identity confirmation');
  await page.goto(bo + '/#handoff=' + 'x'.repeat(43));
  await page.getByText(/This entry link is invalid/).waitFor(); assert.equal((await stored()).token, null);
  await page.reload(); await page.getByRole('button', {name:'Login', exact:true}).waitFor();
  assert.equal((await stored()).token, null); checks.push('invalid handoff and reload never restore prior browser context');
  const process = spawnSync('/tmp/apexpos-phase11-tests.qlfdlS/venv/bin/python', ['/tmp/apex-phase11-browser-recovery.py', a.email], {
    env: {PATH:'/usr/local/bin:/usr/bin:/bin', HOME:'/tmp', PYTHONDONTWRITEBYTECODE:'1', PYTHONPATH:'/tmp/apexpos-phase11/backend',
      DATABASE_URL:'postgresql+asyncpg://postgres@/apexretail_phase10_fresh_20261021t072213?host=/tmp/apex-phase11-postgres-auOybQ&port=55441',
      JWT_SECRET:'synthetic-phase11-isolated-hmac-secret-123456789', APP_ENV:'test'}, encoding:'utf8'});
  assert.equal(process.status, 0, process.stderr);
  await page.goto(process.stdout.trim());
  await page.getByText('Choose a new password', {exact:true}).waitFor(); assert(!page.url().includes('#'));
  await page.locator('input[type=password]').nth(0).fill('new-synthetic-browser-password');
  await page.locator('input[type=password]').nth(1).fill('new-synthetic-browser-password');
  await page.getByRole('button', {name:'Reset password', exact:true}).click();
  await page.getByText('Password reset. Sign in with your new password.').waitFor();
  assert.equal((await api('/auth/login', {email:a.email, password:'synthetic-browser-password'})).status, 401);
  assert.equal((await api('/auth/login', {email:a.email, password:'new-synthetic-browser-password'})).status, 200);
  assert.equal((await api(`/fiscal/${a.company.id}/configuration`, null, {Authorization:'Bearer ' + a.token})).status, 401);
  checks.push('sink-issued recovery fragment, actual browser reset and old password/token denial');
  const dialogPage = await context.newPage();
  dialogPage.on('pageerror', error => errors.push(error.message));
  await dialogPage.addInitScript(fixture => { window.__fixture = fixture; localStorage.setItem('pos_offline_queue', 'retain'); }, {employee:a.employee.access_token,company:a.company.id,branch:a.branch.id});
  await dialogPage.goto('https://pos.apexpos.cloud');
  await dialogPage.getByRole('button', {name:'Test owner authentication'}).click();
  await dialogPage.getByRole('dialog', {name:'Open Backoffice'}).waitFor();
  assert.equal(await dialogPage.getByLabel('Email', {exact:true}).evaluate(element => element === document.activeElement), true);
  await dialogPage.getByLabel('Email', {exact:true}).fill(b.email);
  await dialogPage.getByLabel('Password', {exact:true}).fill('synthetic-browser-password');
  assert.equal(await dialogPage.getByLabel('Password', {exact:true}).getAttribute('type'), 'password');
  await dialogPage.getByRole('button', {name:'Open with owner authentication'}).click();
  await dialogPage.getByRole('alert').waitFor();
  assert.equal(await dialogPage.getByLabel('Password', {exact:true}).inputValue(), '');
  await dialogPage.getByLabel('Email', {exact:true}).fill(a.email);
  await dialogPage.getByLabel('Password', {exact:true}).fill('new-synthetic-browser-password');
  await dialogPage.getByRole('button', {name:'Open with owner authentication'}).click();
  await dialogPage.locator('dialog').waitFor({state:'hidden'});
  assert.equal(await dialogPage.evaluate(() => localStorage.getItem('pos_offline_queue')), 'retain');
  assert.equal(await dialogPage.evaluate(() => typeof window.__handoff === 'string' && window.__handoff.includes('#handoff=')), true);
  await dialogPage.close(); checks.push('cashier fresh owner proof; real POS dialog focus, masked input, cross-business denial, secret clearing and offline storage preservation');
  assert.deepEqual(errors, []); assert.deepEqual(blocked, []);
  const result = {synthetic_only:true, playwright:'1.65.1', browser:browser.version(), checks, page_errors:errors,
    external_requests_blocked:blocked, api_requests_to_loopback_only:paths.length, real_provider_actions:false};
  writeFileSync('/tmp/phase11-browser-acceptance.json', JSON.stringify(result,null,2)+'\n'); console.log(JSON.stringify(result));
} catch (error) { console.log(JSON.stringify({failure:String(error.message).replace(/[A-Za-z0-9_-]{40,}/g, '[redacted]'), text:await page.locator('body').innerText(), calls, page_errors:errors})); throw new Error('Browser acceptance failed; inspect sanitized diagnostics'); } finally { await context.close(); await browser.close(); }
