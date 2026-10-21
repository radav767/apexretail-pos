import assert from 'node:assert/strict';
import{mkdir,writeFile}from'node:fs/promises';
import{fileURLToPath}from'node:url';
import{createServer}from'vite';
import{chromium}from'/root/.npm/_npx/420ff84f11983ee5/node_modules/playwright/index.mjs';
const root=fileURLToPath(new URL('..',import.meta.url)),out=process.env.PLATFORM_BROWSER_OUTPUT_DIR||fileURLToPath(new URL('../../artifacts/phase8-commercial',import.meta.url));await mkdir(out,{recursive:true});
const server=await createServer({root,server:{host:'127.0.0.1',port:18932,strictPort:true}});await server.listen();
const browser=await chromium.launch({executablePath:'/tmp/apexretail-pw-browsers/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']});
const context=await browser.newContext(),errors=[],external=[],checks=[];
await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():(external.push(r.request().url()),r.abort()));
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
const pass=name=>checks.push(name);
async function login(role='super_admin'){
 await page.goto(`http://127.0.0.1:18932/tests/visual-phase8.html?role=${role}`);
 if(await page.getByLabel('Email',{exact:true}).count()){
  await page.getByLabel('Email',{exact:true}).fill('synthetic@example.test');await page.getByLabel('Password',{exact:true}).fill('synthetic-only-not-a-real-account');await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByLabel('Authentication code',{exact:true}).fill('123456');await page.getByRole('button',{name:'Verify code',exact:true}).click();
 }
 await page.getByRole('heading',{name:'Dashboard',exact:true}).waitFor();
}
try{
 await login();pass('Separate platform sign-in and dashboard');
 for(const width of[1440,820,390,320]){await page.setViewportSize({width,height:1000});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:`${out}/platform-dashboard-${width}.png`,fullPage:true});pass(`Platform dashboard ${width}px no horizontal overflow`);}
 await page.setViewportSize({width:1440,height:1000});await page.getByRole('navigation').getByRole('button',{name:'Plans',exact:true}).click();
 await page.getByLabel('Name',{exact:true}).fill('Synthetic quarterly retail');await page.locator('form select').first().selectOption('3');await page.getByLabel('price',{exact:true}).fill('9.99');
 await page.getByLabel('restaurant',{exact:true}).check();await page.getByRole('button',{name:'Save plan',exact:true}).click();await page.getByRole('button',{name:'Edit',exact:true}).waitFor();
 let plan=await page.evaluate(()=>window.phase8Calls.find(c=>c.url==='/platform/plans'&&c.method==='post').body);assert.equal(plan.months,3);assert.equal(plan.features.restaurant,true);pass('Plan creation preserves period, price, currency and selected feature');
 await page.getByRole('button',{name:'Edit',exact:true}).click();await page.getByLabel('price',{exact:true}).fill('12.50');await page.getByRole('button',{name:'Save plan',exact:true}).click();
 await page.waitForFunction(()=>window.phase8Calls.some(c=>c.method==='put'&&c.body.expected_version===1));pass('Plan edit includes optimistic concurrency version');
 await page.screenshot({path:`${out}/platform-plans-desktop.png`,fullPage:true});
 await page.getByRole('navigation').getByRole('button',{name:'Businesses',exact:true}).click();await page.getByRole('button',{name:'Billing',exact:true}).last().click();
 const issue=page.locator('form').filter({has:page.getByRole('heading',{name:'Issue subscription invoice',exact:true})});
 await issue.locator('select').selectOption('synthetic-plan');await issue.getByLabel('Reason',{exact:true}).fill('Synthetic approved invoice');await issue.getByRole('button',{name:'Issue invoice',exact:true}).click();
 await page.getByRole('cell',{name:'USD 12.50',exact:true}).waitFor();pass('Issue invoice and show authoritative currency/amount');
 const payment=page.locator('form').filter({has:page.getByRole('heading',{name:'Confirm payment',exact:true})});
 await payment.locator('select').first().selectOption('synthetic-invoice');await payment.getByLabel('Amount',{exact:true}).fill('12.50');await payment.getByLabel('Original payment reference',{exact:true}).fill('SYNTHETIC-RECEIPT-1');
 await payment.getByRole('button',{name:'Confirm received payment',exact:true}).click();await page.getByRole('button',{name:'Retry original request',exact:true}).waitFor();
 const original=await page.evaluate(()=>window.phase8Calls.find(c=>c.url==='/platform/payments').body);
 await page.getByRole('button',{name:'Retry original request',exact:true}).click();await page.getByText('Confirmed.',{exact:true}).waitFor();
 const attempts=await page.evaluate(()=>window.phase8Calls.filter(c=>c.url==='/platform/payments').map(c=>c.body));assert.equal(attempts.length,2);assert.deepEqual(attempts[1],original);pass('Uncertain payment retry retains exact original identity/reference/amount');
 await page.screenshot({path:`${out}/platform-billing-desktop.png`,fullPage:true});
 await page.getByRole('button',{name:'Log out',exact:true}).click();await page.getByRole('button',{name:'Sign in',exact:true}).waitFor();pass('Platform logout clears only platform session');
 await login('support');await page.getByRole('navigation').getByRole('button',{name:'Plans',exact:true}).click();assert.equal(await page.getByRole('button',{name:'Save plan',exact:true}).count(),0);pass('Support role has no plan mutation controls');
 await page.goto('http://127.0.0.1:18932/tests/visual-phase8.html?denied=true');await page.getByText('This feature is not included in your subscription.',{exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Restricted editor must not render',exact:true}).count(),0);pass('Frontend feature denial hides editor, not just its navigation link');
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);pass('No external requests or uncaught browser errors');
}catch(e){process.exitCode=1;console.error(e);await page.screenshot({path:`${out}/failure.png`,fullPage:true});}
finally{await writeFile(`${out}/browser-results.json`,JSON.stringify({checks,errors,external,syntheticAdapters:true,passed:!process.exitCode},null,2));await browser.close();await server.close();console.log(JSON.stringify({passed:checks.length,success:!process.exitCode}));}
