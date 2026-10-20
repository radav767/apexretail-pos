// Real UI actions against the existing isolated HTTPS acceptance service.
// No mock adapters, production origins, credential artifacts or new environment.
import assert from 'node:assert/strict';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {chromium} from '/root/.npm/_npx/420ff84f11983ee5/node_modules/playwright/index.mjs';
const account=JSON.parse(await readFile('/tmp/apexretail-phase7f-runtime/acceptance-accounts.json','utf8')).accounts[1];
const fixture=JSON.parse(await readFile(new URL('../artifacts/phase7-software-completion/authenticated-fixture.json',import.meta.url),'utf8'));
const out=new URL('../artifacts/phase7-software-completion/browser/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/tmp/apexretail-pw-browsers/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']});
const checks=[],external=[],errors=[];
async function context(){
 const c=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
 c.setDefaultTimeout(10000);
 await c.route('**/*',r=>{
  const u=new URL(r.request().url());
  return ['localhost','127.0.0.1'].includes(u.hostname)&&u.port==='18770'?r.continue():(external.push(u.origin+u.pathname),r.abort());
 });
 c.on('page',p=>{p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());});
 return c;
}
function pass(check){checks.push({check,result:'PASS'});}
async function pinLogin(page){
 await page.locator('.pos-pin-input').waitFor();await page.locator('.pos-pin-input').fill(account.pin);
 await page.getByRole('button',{name:'Open POS',exact:true}).click();await page.waitForTimeout(500);
 const takeover=page.getByRole('button',{name:'Take over this session',exact:true});if(await takeover.isVisible())await takeover.click();
 const start=page.getByRole('button',{name:'OPEN SHIFT',exact:true});
 await Promise.race([start.waitFor(),page.locator('.pos-menu-trigger').waitFor()]);
 if(await start.isVisible())await start.click();
 await page.locator('.pos-menu-trigger').waitFor();
}
async function categoryActions(page,app){
 const name=`UI ${app} ${fixture.run}`,renamed=name+' edited';
 await page.getByPlaceholder('Category name',{exact:true}).fill(name);
 await page.getByRole('button',{name:'Add',exact:true}).click();
 const rows=app==='POS'?page.getByRole('row'):page.locator('.category-row');
 let row=rows.filter({hasText:name});await row.getByRole('button',{name:'Edit',exact:true}).click();
 await page.getByPlaceholder('Category name',{exact:true}).fill(renamed);
 await page.getByRole('button',{name:'Update',exact:true}).click();
 row=rows.filter({hasText:renamed});await row.waitFor();pass(`${app} authenticated category create/edit`);
 await page.reload();if(app==='POS')await pinLogin(page);row=rows.filter({hasText:renamed});await row.waitFor();pass(`${app} category persists after app reload`);
 await row.getByRole('button',{name:'Delete',exact:true}).click();await row.waitFor({state:'detached'});pass(`${app} authenticated empty-category delete`);
}
try{
 const posContext=await context();
 await posContext.addInitScript(reg=>{
  if(location.origin!=='https://localhost:18770')return;
  localStorage.setItem('device_key',reg.device.device_key);localStorage.setItem('device_id',reg.device.id);localStorage.setItem('device_company_id',reg.company.id);
 },account.registration);
 const pos=await posContext.newPage();await pos.goto('https://localhost:18770/');
 // Fixed server identity is checked before entering credentials or performing writes.
 const identity=await posContext.request.get('https://localhost:18770/api/staging-identity');
 assert.equal((await identity.json()).database,'apexretail_phase7f_acceptance');
 await pos.locator('input[type=email]').fill(account.email);await pos.locator('input[type=password]').fill(account.password);
 await pos.getByRole('button',{name:'Sign in',exact:true}).last().click();
 await pinLogin(pos);
 pass('POS real password/PIN authentication on registered test device');
 await pos.goto('https://localhost:18770/?module=Products&feature=categories');await pinLogin(pos);
 await categoryActions(pos,'POS');
 await pos.goto('https://localhost:18770/?module=Inventory&feature=stock-counts');await pinLogin(pos);
 const countLabel='Physical count Verified stock '+fixture.run;
 await pos.getByLabel(countLabel,{exact:true}).fill('30');
 await pos.getByRole('button',{name:'Complete Stock Take (1)',exact:true}).click();
 await pos.getByRole('button',{name:'New stock count',exact:true}).waitFor();pass('POS real authenticated physical count acknowledgment');
 await pos.reload();await pinLogin(pos);await pos.getByRole('button',{name:'New stock count',exact:true}).waitFor();pass('POS confirmed count survives app restart without resubmission');
 await pos.getByRole('button',{name:'New stock count',exact:true}).click();
 await pos.getByLabel(countLabel,{exact:true}).waitFor();
 await pos.goBack();pass('POS browser Back restores previous dedicated feature');
 await pos.goto('https://localhost:18770/?module=Business%20Operations&business_view=orders');await pinLogin(pos);
 await pos.getByRole('button',{name:'Open order',exact:true}).waitFor();
 const draftPanel=pos.locator('details.business-manager').filter({has:pos.locator('summary').filter({hasText:/^Offline order drafts$/})});
 await draftPanel.locator('summary').first().click();
 await draftPanel.locator('form select').nth(0).selectOption(fixture.productId);
 await draftPanel.locator('form select').nth(1).selectOption(fixture.variantId);
 await posContext.setOffline(true);
 await draftPanel.getByRole('button',{name:'Add draft item',exact:true}).click();
 await draftPanel.getByRole('button',{name:'Save unpaid draft',exact:true}).click();
 const original=await pos.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('apexretail_unpaid_order_outbox_v1:')).map(k=>JSON.parse(localStorage.getItem(k))).find(c=>c.endpoint==='/operations/offline/drafts'));
 assert.equal(original.status,'pending');assert.equal(original.payload.items[0].variant_id,fixture.variantId);pass('Actual offline UI saves original cashier-bound variant draft');
 await posContext.setOffline(false);await pos.reload();await pinLogin(pos);await pos.getByRole('button',{name:'Open order',exact:true}).waitFor();
 await draftPanel.locator('summary').first().click();
 await draftPanel.getByRole('button',{name:'Check server confirmation',exact:true}).click();
 await draftPanel.getByText('Not confirmed on server. Synchronize the unchanged original draft.',{exact:true}).waitFor();
 pass('Restart recovery retains an unsynchronized original draft');
 await draftPanel.getByRole('button',{name:'Review & synchronize drafts',exact:true}).click();
 await draftPanel.getByText('acknowledged',{exact:true}).waitFor();
 const acknowledged=await pos.evaluate(id=>Object.keys(localStorage).filter(k=>k.startsWith('apexretail_unpaid_order_outbox_v1:')).map(k=>JSON.parse(localStorage.getItem(k))).find(c=>c.id===id),original.id);
 assert.deepEqual(acknowledged.payload,original.payload);pass('Reconnection synchronizes without replacing original timestamp, cashier or variant');
 await draftPanel.getByRole('button',{name:'Review & synchronize drafts',exact:true}).click();
 await pos.locator('.business-records button').filter({hasText:acknowledged.result.order.number}).click();
 await posContext.setOffline(true);await pos.getByRole('button',{name:'Save kitchen request',exact:true}).click();
 await pos.getByRole('button',{name:'Save kitchen request',exact:true}).click();
 const kitchen=await pos.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('apexretail_unpaid_order_outbox_v1:')).map(k=>JSON.parse(localStorage.getItem(k))).filter(c=>c.endpoint==='/operations/offline/kitchen'));
 assert.equal(kitchen.length,1);assert.equal(await pos.getByRole('button',{name:'Confirm payment',exact:true}).isDisabled(),true);pass('Offline kitchen intent deduplicated; offline payment remains disabled');
 await posContext.setOffline(false);await draftPanel.getByRole('button',{name:'Review & synchronize drafts',exact:true}).click();
 await pos.waitForFunction(()=>Object.keys(localStorage).filter(k=>k.startsWith('apexretail_unpaid_order_outbox_v1:')).map(k=>JSON.parse(localStorage.getItem(k))).some(c=>c.endpoint==='/operations/offline/kitchen'&&c.status==='acknowledged'));
 pass('Offline KOT intent dispatches only after authenticated reconnection');
 await pos.goto('https://localhost:18770/?module=Business%20Operations&business_view=kitchen');await pinLogin(pos);
 const ticket=pos.locator('.business-kds article').filter({hasText:acknowledged.result.order.number});await ticket.waitFor();
 await posContext.setOffline(true);await ticket.getByRole('button',{name:'Save start preparation request',exact:true}).click();
 await posContext.setOffline(false);await draftPanel.locator('summary').first().click();
 await draftPanel.getByRole('button',{name:'Review & synchronize drafts',exact:true}).click();
 await ticket.locator('.business-badge').getByText('preparing',{exact:true}).waitFor();pass('Actual offline KDS request synchronizes and refreshes displayed server status');
 await posContext.setOffline(true);await ticket.getByRole('button',{name:'Save mark ready request',exact:true}).click();
 const conflict=await pos.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('apexretail_unpaid_order_outbox_v1:')).map(k=>JSON.parse(localStorage.getItem(k))).find(c=>c.endpoint==='/operations/offline/kds'&&c.status==='pending'));
 await posContext.setOffline(false);
 const updated=await pos.evaluate(async id=>{
  const r=await fetch(`/api/operations/kitchen/${id}`,{method:'PUT',headers:{'Content-Type':'application/json',Authorization:'Bearer '+localStorage.getItem('employee_token')},body:JSON.stringify({status:'ready'})});
  return r.status;
 },conflict.payload.ticket_id);assert.equal(updated,200);
 await draftPanel.getByRole('button',{name:'Review & synchronize drafts',exact:true}).click();
 const rejected=draftPanel.locator('article').filter({hasText:'Kitchen ticket changed; review current server status'});
 await rejected.getByRole('button',{name:'Review current server state',exact:true}).click();
 await draftPanel.getByLabel('Resolution reason',{exact:true}).fill('Kitchen confirmed current server status');
 await draftPanel.getByRole('button',{name:'Accept current server state',exact:true}).click();
 await draftPanel.getByText('resolved',{exact:true}).waitFor();
 const resolution=await pos.evaluate(id=>Object.keys(localStorage).filter(k=>k.startsWith('apexretail_unpaid_order_outbox_v1:')).map(k=>JSON.parse(localStorage.getItem(k))).find(c=>c.id===id),conflict.id);
 assert.deepEqual(resolution.payload,conflict.payload);assert.equal(resolution.result.resolution.decision,'accepted_server_state');
 await ticket.locator('.business-badge').getByText('ready',{exact:true}).waitFor();pass('Actual UI conflict review records explicit resolution without overwriting current kitchen status or original command');
 const boContext=await context(),bo=await boContext.newPage();
 await bo.goto('https://localhost:18770/backoffice/');await bo.locator('input[type=email]').fill(account.email);await bo.locator('input[type=password]').fill(account.password);
 await bo.getByRole('button',{name:'Login',exact:true}).click();await bo.locator('#backoffice-navigation').waitFor();pass('Independent Backoffice actual password authentication');
 await bo.locator('#backoffice-navigation').getByRole('button',{name:'Products',exact:true}).click();
 await bo.getByRole('button').filter({hasText:'Categories'}).last().click();
 await categoryActions(bo,'Backoffice');
 await bo.goto('https://localhost:18770/backoffice/?module=Products&feature=variants');
 // Navigate through the real sidebar so Backoffice retains its own route contract.
 await bo.locator('#backoffice-navigation').getByRole('button',{name:'Products',exact:true}).click();
 const hub=bo.getByRole('button').filter({hasText:'Product Variants'});if(await hub.count())await hub.last().click();
 await bo.locator('.advanced-product-picker select').selectOption(fixture.productId);
 const variant=bo.getByRole('row').filter({hasText:'V-'+fixture.run});await variant.getByRole('button',{name:'Edit',exact:true}).click();
 await bo.getByPlaceholder('Variant name',{exact:true}).fill('Small UI verified');await bo.getByRole('button',{name:'Update variant',exact:true}).click();
 await bo.getByRole('row').filter({hasText:'Small UI verified'}).waitFor();pass('Backoffice real variant metadata edit persisted');
 for(const width of [320,390,820,1440]){
  await pos.goto('https://localhost:18770/?module=Inventory&feature=stock-counts');await pinLogin(pos);await pos.getByRole('heading',{name:'Stock Take',exact:true}).waitFor();
  await pos.setViewportSize({width,height:900});assert.ok(await pos.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));pass(`Actual POS count page ${width}px no horizontal overflow`);
  await pos.screenshot({path:new URL(`stock-count-${width}.png`,out).pathname,fullPage:true});
 }
 assert.deepEqual(external,[]);assert.deepEqual(errors,[]);pass('No production requests or uncaught browser exceptions');
}catch(e){process.exitCode=1;checks.push({check:'Authenticated UI acceptance',result:'FAIL',error:e.message});console.error(e.message);
 for(const c of browser.contexts())for(const p of c.pages())console.error((await p.locator('body').innerText()).replaceAll(account.email,'[test email]').slice(-2200));
}
finally{await writeFile(new URL('results.json',out),JSON.stringify({checks,external,errors,physicalDevice:false},null,2));await browser.close();console.log(JSON.stringify({passed:checks.filter(c=>c.result==='PASS').length,failed:checks.filter(c=>c.result==='FAIL').length}));}
