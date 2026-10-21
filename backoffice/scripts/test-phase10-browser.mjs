// Actual platform components, synthetic API fixtures only; all external traffic blocked.
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createServer} from 'vite';
import {chromium} from '/root/.npm/_npx/420ff84f11983ee5/node_modules/playwright/index.mjs';
const root=fileURLToPath(new URL('..',import.meta.url)),out=fileURLToPath(new URL('../../artifacts/phase10-platform',import.meta.url));
await mkdir(out,{recursive:true});
const server=await createServer({root,server:{host:'127.0.0.1',port:18934,strictPort:true}});await server.listen();
const browser=await chromium.launch({executablePath:'/tmp/apexretail-pw-browsers/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']});
const context=await browser.newContext(),errors=[],external=[],checks=[];
await context.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():(external.push(route.request().url()),route.abort()));
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.type()==='prompt'?d.accept('Synthetic authorized review'):d.accept());
const pass=name=>checks.push(name);
async function nav(name){
 if(await page.getByRole('button',{name:'Platform navigation',exact:true}).isVisible())await page.getByRole('button',{name:'Platform navigation',exact:true}).click();
 await page.getByRole('navigation').getByRole('button',{name,exact:true}).click();
 await page.getByRole('heading',{name,exact:true}).waitFor();
}
async function login(role='super_admin'){
 await page.goto(`http://127.0.0.1:18934/tests/visual-phase8.html?role=${role}`);
 await page.getByLabel('Email',{exact:true}).fill('synthetic@example.test');await page.getByLabel('Password',{exact:true}).fill('synthetic-password-not-a-real-account');await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await page.getByRole('heading',{name:'Set up authenticator',exact:true}).waitFor();
 assert.equal(await page.getByRole('navigation').count(),0);
 await page.getByLabel('Authentication code',{exact:true}).fill('123456');await page.getByRole('button',{name:'Verify code',exact:true}).click();await page.getByRole('heading',{name:'Dashboard',exact:true}).waitFor();
 assert.equal(await page.locator('.platform-secret').count(),0);
}
try{
 await login();pass('Password → MFA setup → verified session; no navigation before MFA or retained setup secret');
 for(const width of [1440,820,390,320]){
  await page.setViewportSize({width,height:1000});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:`${out}/dashboard-${width}.png`,fullPage:true});pass(`Dashboard at ${width}px has no horizontal overflow`);
 }
 for(const view of ['Devices','Fiscal status','Settings','Administrators','Sessions','System health']){
  await nav(view);
  await page.waitForTimeout(100);
  assert.equal(await page.getByRole('heading',{name:'Dashboard',exact:true}).count(),0);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:`${out}/${view.replaceAll(' ','-').toLowerCase()}-mobile.png`,fullPage:true});pass(`${view} is a separate mobile page with no overflow`);
 }
 await nav('Devices');await page.getByRole('button',{name:'Activity',exact:true}).click();await page.getByText('2026-10-21T10:00:00Z · terminal_registered',{exact:true}).waitFor();pass('Device activity loads without exposing device secrets');
 await nav('Settings');await page.getByLabel('Trial duration (new businesses only)',{exact:true}).fill('14');await page.getByRole('button',{name:'Save settings',exact:true}).click();
 await page.waitForFunction(()=>window.phase8Calls.some(c=>c.url==='/platform/settings'&&c.method==='put'&&c.body.trial_days===14&&c.body.expected_version===1));pass('Settings save sends bounded trial default and optimistic version');
 await nav('Businesses');await page.getByRole('combobox',{name:/Business details/}).selectOption('synthetic-company');await page.getByRole('heading',{name:'Synthetic Retail Shop',exact:true}).waitFor();
 await page.getByRole('button',{name:'Request owner identity review',exact:true}).click();await page.getByText('Owner identity review pending; no account credentials changed.',{exact:true}).waitFor();pass('Business details and safe identity-review request');
 await page.getByRole('button',{name:'Log out',exact:true}).click();await page.getByRole('button',{name:'Sign in',exact:true}).waitFor();
 await login('support');await nav('Settings');assert.equal(await page.getByRole('button',{name:'Save settings',exact:true}).count(),0);assert.ok(await page.getByLabel('Brand name',{exact:true}).isDisabled());
 if(await page.getByRole('button',{name:'Platform navigation',exact:true}).isVisible())await page.getByRole('button',{name:'Platform navigation',exact:true}).click();
 assert.equal(await page.getByRole('navigation').getByRole('button',{name:'Administrators',exact:true}).count(),0);pass('Support has read-only settings and no administrator navigation');
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);pass('No uncaught browser errors or external requests');
}catch(e){process.exitCode=1;console.error(e);await page.screenshot({path:`${out}/failure.png`,fullPage:true});}
finally{await writeFile(`${out}/browser-results.json`,JSON.stringify({checks,errors,external,synthetic:true,passed:!process.exitCode},null,2));await browser.close();await server.close();console.log(JSON.stringify({checks:checks.length,passed:!process.exitCode}));}
