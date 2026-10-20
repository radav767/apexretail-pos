import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { chromium } from '/root/.npm/_npx/420ff84f11983ee5/node_modules/playwright/index.mjs';
const root='/tmp/apexpos-phase7f/phase7f-evidence/browser';
await mkdir(root,{recursive:true});
const state=JSON.parse(await readFile('/tmp/apexretail-phase7f-runtime/acceptance-accounts.json','utf8'));
const account=state.accounts[0];
const browser=await chromium.launch({executablePath:'/tmp/apexretail-pw-browsers/chromium-1194/chrome-linux/chrome',headless:true,args:['--no-sandbox']});
const results=[], failures=[], external=[], apiErrors=[];
async function record(name, task){
  try{await task();results.push({check:name,result:'PASS'});}
  catch(error){results.push({check:name,result:'FAIL',error:String(error.message).slice(0,400)});failures.push(name);}
  await writeFile(root+'/results.json',JSON.stringify({results,external,apiErrors},null,2));
}
const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
context.setDefaultTimeout(10000);
await context.route('**/*',route=>{
  const url=new URL(route.request().url());
  if(['localhost','127.0.0.1'].includes(url.hostname)&&url.port==='18770')return route.continue();
  external.push(url.origin+url.pathname);return route.abort();
});
context.on('response',response=>{if(response.url().includes('/api/')&&response.status()>=400)apiErrors.push({url:response.url().split('?')[0],status:response.status()});});
await context.addInitScript(reg=>{
  localStorage.setItem('device_key',reg.device.device_key);
  localStorage.setItem('device_id',reg.device.id);
  localStorage.setItem('device_company_id',reg.company.id);
},account.registration);
const pos=await context.newPage();
pos.on('pageerror',error=>failures.push('POS JavaScript: '+error.message));
await record('POS real password and PIN login',async()=>{
  await pos.goto('https://localhost:18770/');
  await pos.locator('input[type=email]').fill(account.email);
  await pos.locator('input[type=password]').fill(account.password);
  await pos.getByRole('button',{name:'Sign in',exact:true}).last().click();
  await pos.locator('.pos-pin-input').fill(account.pin);
  await pos.getByRole('button',{name:'Open POS',exact:true}).click();
  await pos.waitForTimeout(500);
  const takeover=pos.getByRole('button',{name:'Take over this session',exact:true});
  if(await takeover.isVisible())await takeover.click();
  await pos.waitForFunction(()=>Boolean(localStorage.getItem('employee_token')),null,{timeout:10000});
  await pos.waitForTimeout(1000);
});
if(failures.length){await pos.screenshot({path:root+'/login-failure.png',fullPage:true});await browser.close();throw Error('Login gate failed');}
await record('POS zero opening float through UI',async()=>{
  const start=pos.getByRole('button',{name:/^OPEN SHIFT$/i});
  if(await start.count())await start.click();
  await pos.locator('.pos-menu-trigger').waitFor();
});
if(failures.length){await pos.screenshot({path:root+'/shift-failure.png',fullPage:true});await browser.close();throw Error('Shift UI gate failed');}
const leaves=[['Sales','Sales'],['Business Operations','Business Operations'],['Transaction History','Sales Management'],['Shift Management','Shift Management'],['Credit Settlement','Credit Settlements'],['Customers','Customers'],['Expenses','Expenses'],['Products','Products'],['Categories','Products'],['Composite Products','Products'],['Goods Received (GRN)','Inventory'],['Stock Adjustments','Inventory'],['Stock Transfers','Inventory'],['Sales Summary','Reports'],['Sales Reports','Reports'],['Top Selling Products','Reports'],['Settings','Settings']];
for(const[label,module]of leaves)await record('POS menu: '+label,async()=>{
  if(await pos.locator('.pos-menu-panel').getAttribute('aria-hidden')==='true')await pos.locator('.pos-menu-trigger').click();
  for(const group of await pos.locator('.pos-nav-group-toggle').all())if(await group.getAttribute('aria-expanded')==='false')await group.click();
  const nav=pos.getByRole('navigation',{name:'POS navigation'});
  const destination=label==='Products'?nav.locator('.pos-nav-children').getByRole('button',{name:label,exact:true}):nav.getByRole('button',{name:label,exact:true});
  await destination.click();await pos.waitForTimeout(200);
  if(new URL(pos.url()).searchParams.get('module')!==module)throw Error('Wrong module destination');
  if((await pos.locator('body').innerText()).length<100)throw Error('Empty page');
});
for(const module of ['Sales Management','Products','Inventory','Reports','Settings']){
  if(await pos.locator('.pos-menu-panel').getAttribute('aria-hidden')==='true')await pos.locator('.pos-menu-trigger').click();
  for(const group of await pos.locator('.pos-nav-group-toggle').all())if(await group.getAttribute('aria-expanded')==='false')await group.click();
  const entry={'Sales Management':'Transaction History',Products:'Categories',Inventory:'Goods Received (GRN)',Reports:'Sales Summary',Settings:'Settings'}[module];
  await pos.getByRole('navigation',{name:'POS navigation'}).getByRole('button',{name:entry,exact:true}).click();
  const back=pos.locator('.pos-feature-back');
  if(module!=='Settings'){await back.waitFor();await back.click();await pos.locator('.pos-feature-grid').waitFor();}
  await pos.waitForTimeout(200);
  const titles=await pos.locator('.pos-feature-grid button strong').allTextContents();
  if(module!=='Settings'&&titles.length===0)throw Error('Missing feature hub: '+module);
  for(const title of titles)await record(`POS ${module} feature: ${title}`,async()=>{
    await pos.locator('.pos-feature-grid button').filter({hasText:title}).click();
    await pos.waitForTimeout(200);
    if(!new URL(pos.url()).searchParams.get('feature'))throw Error('Feature URL not selected');
    await pos.goBack();
    await pos.locator('.pos-feature-grid').waitFor();
    if(new URL(pos.url()).searchParams.has('feature'))throw Error('Browser Back did not restore feature menu');
  });
  if(module==='Settings'){
    const names=await pos.locator('.pos-settings-menu-item strong').allTextContents();
    for(const title of names)await record('POS Settings feature: '+title,async()=>{
      await pos.locator('.pos-settings-menu-item').filter({hasText:title}).click();
      await pos.getByRole('button',{name:'Back to Settings',exact:true}).waitFor();
      await pos.goBack();await pos.locator('.pos-settings-menu').waitFor();
    });
  }
}
// Independent storage profile prevents POS tokens masking Backoffice auth bugs.
const boContext=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
boContext.setDefaultTimeout(10000);
await boContext.route('**/*',route=>{
  const url=new URL(route.request().url());
  if(['localhost','127.0.0.1'].includes(url.hostname)&&url.port==='18770')return route.continue();
  external.push(url.origin+url.pathname);return route.abort();
});
boContext.on('response',response=>{if(response.url().includes('/api/')&&response.status()>=400)apiErrors.push({url:response.url().split('?')[0],status:response.status()});});
const bo=await boContext.newPage();
bo.on('pageerror',error=>failures.push('Backoffice JavaScript: '+error.message));
await record('Backoffice real password login',async()=>{
  await bo.goto('https://localhost:18770/backoffice/');
  await bo.locator('input[type=email]').fill(account.email);
  await bo.locator('input[type=password]').fill(account.password);
  await bo.getByRole('button',{name:'Login',exact:true}).click();
  await bo.locator('#backoffice-navigation').waitFor();
});
const boButtons=(await bo.locator('#backoffice-navigation button').allTextContents()).filter(title=>title.trim()!=='Log out');
for(const title of boButtons)await record('Backoffice menu: '+title.trim(),async()=>{
  await bo.locator('#backoffice-navigation').getByRole('button',{name:title.trim(),exact:true}).click();
  await bo.waitForTimeout(250);
  if((await bo.locator('main').innerText()).length<50)throw Error('Empty content');
});
await bo.locator('#backoffice-navigation').getByRole('button',{name:'Dashboard',exact:true}).click();
await bo.locator('.dashboard-feature-grid').waitFor();
const dashboardFeatures=await bo.locator('.dashboard-feature-grid button strong').allTextContents();
for(const title of dashboardFeatures)await record('Backoffice dashboard feature: '+title,async()=>{
  await bo.locator('.dashboard-feature-grid button').filter({hasText:title}).click();
  await bo.waitForTimeout(200);
  if((await bo.locator('main').innerText()).length<50)throw Error('Empty feature content');
  await bo.goBack();await bo.locator('.dashboard-feature-grid').waitFor();
});
for(const width of [1440,820,390,320])for(const[app,page,url]of[['pos',pos,'https://localhost:18770/?module=Sales'],['backoffice',bo,'https://localhost:18770/backoffice/']]){
  await record(`${app} ${width}px responsive live staging`,async()=>{
    await page.setViewportSize({width,height:1000});
    if(app==='backoffice')await page.goto(url);
    else{
      if(await page.locator('.pos-menu-panel').getAttribute('aria-hidden')==='true')await page.locator('.pos-menu-trigger').click();
      await page.getByRole('navigation',{name:'POS navigation'}).getByRole('button',{name:'Sales',exact:true}).click();
      if(await page.locator('.pos-menu-panel').getAttribute('aria-hidden')==='false')await page.locator('.pos-menu-trigger').click();
    }
    await page.waitForTimeout(500);
    if(app==='pos')await page.locator('.pos-menu-trigger').waitFor();
    const metrics=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
    await page.screenshot({path:`${root}/${app}-${width}.png`,fullPage:true});
    if(metrics.scroll>metrics.width+1)throw Error(`Horizontal overflow ${JSON.stringify(metrics)}`);
  });
}
await record('Backoffice logout action',async()=>{
  await bo.setViewportSize({width:1440,height:1000});
  await bo.locator('.logout-button').click();
  await bo.locator('input[type=email]').waitFor();
});
await record('No production or external requests',async()=>{if(external.length)throw Error(JSON.stringify(external));});
await record('All authenticated staging API reads succeed',async()=>{if(apiErrors.length)throw Error(JSON.stringify(apiErrors).slice(0,350));});
await boContext.close();await context.close();await browser.close();
await writeFile(root+'/summary.json',JSON.stringify({passed:results.filter(r=>r.result==='PASS').length,failed:failures.length,failures,physicalHardwareTest:false},null,2));
console.log(JSON.stringify({passed:results.filter(r=>r.result==='PASS').length,failed:failures.length,failures}));
if(failures.length)process.exitCode=1;
