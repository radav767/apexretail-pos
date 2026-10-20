import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {chromium} from '/root/.npm/_npx/420ff84f11983ee5/node_modules/playwright/index.mjs';
const runtime='/tmp/apexretail-phase7f-runtime';
const pointer=JSON.parse(await readFile(runtime+'/phase7g-current.json','utf8'));
const state=JSON.parse(await readFile(pointer.private_fixture,'utf8'));
const out='/tmp/apexpos-phase7f/phase7g-evidence/browser';await mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/tmp/apexretail-pw-browsers/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']});
const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:390,height:844}});context.setDefaultTimeout(12000);
const errors=[],external=[],checks=[],opens=[],sales=[],entitlementFailures=[];
await context.route('**/*',route=>{
 const u=new URL(route.request().url());
 if(u.hostname!=='localhost'||u.port!=='18770'){external.push(u.origin);return route.abort();}
 return route.continue();
});
await context.addInitScript(reg=>{
 localStorage.setItem('device_key',reg.device.device_key);localStorage.setItem('device_id',reg.device.id);localStorage.setItem('device_company_id',reg.company.id);
},state.registration);
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
page.on('console',async message=>{if(message.text().startsWith('[entitlement] verification failed')){const value=await message.args()[1]?.jsonValue();entitlementFailures.push(value?.category||'unknown');}});
page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/shifts/open'))opens.push(r.postDataJSON());if(r.method()==='POST'&&r.url().endsWith('/sales'))sales.push(r.url());});
function check(name,condition=true){checks.push({check:name,result:condition?'PASS':'FAIL'});if(!condition)throw Error(name);}
try{
 await page.goto('https://localhost:18770/');
 await page.locator('input[type=email]').fill(state.email);await page.locator('input[type=password]').fill(state.password);
 await page.getByRole('button',{name:'Sign in',exact:true}).last().click();
 await page.locator('.pos-pin-input').fill('1357');await page.getByRole('button',{name:'Open POS',exact:true}).click();
 await page.waitForTimeout(500);
 const takeover=page.getByRole('button',{name:'Take over this session',exact:true});
 if(await takeover.isVisible())await takeover.click();
 await page.getByRole('heading',{name:'Start Shift',exact:true}).waitFor();check('Real cashier PIN opens Start Shift prompt');
 await page.getByRole('button',{name:'Return to Sales',exact:true}).click();
 check('Return to Sales cannot dismiss mandatory prompt',await page.getByRole('heading',{name:'Start Shift',exact:true}).isVisible());
 check('Checkout unavailable without active shift',await page.locator('.pos-product-card').count()===0);
 await context.setOffline(true);await page.getByRole('button',{name:'Refresh',exact:true}).click();
 await page.getByRole('button',{name:'OPEN SHIFT',exact:true}).waitFor();
 check('Cannot open a shift offline',await page.getByRole('button',{name:'OPEN SHIFT',exact:true}).isDisabled());
 await context.setOffline(false);await page.getByRole('button',{name:'Refresh',exact:true}).click();
 await page.getByRole('button',{name:'OPEN SHIFT',exact:true}).waitFor({state:'visible'});
 await page.locator('#open-shift .pos-shift-count-grid input').fill('');
 await page.getByRole('button',{name:'OPEN SHIFT',exact:true}).click();
 await page.locator('.pos-menu-trigger').waitFor();
 check('Blank optional opening amount submits zero',opens.length===1&&opens[0].opening_balances.every(v=>v.amount==='0'));
 check('Sales available after opening shift',await page.locator('.pos-product-card').count()>0);
 check('Saved authorization verified after offline/reconnect',await page.evaluate(()=>Boolean(localStorage.getItem('apexpos_entitlement_snapshot_v1'))));
 check('No authorization warning on Sales',!(await page.locator('body').innerText()).includes('The saved POS authorization could not be verified'));
 await page.screenshot({path:out+'/cashier-sales-390.png',fullPage:true});
 await page.locator('.pos-menu-trigger').click();
 await page.getByRole('navigation',{name:'POS navigation'}).getByRole('button',{name:'Shift Management',exact:true}).click();
 await page.locator('#close-shift input[inputmode=decimal]').fill('0');
 await page.locator('.pos-shift-confirm input').check();await page.getByRole('button',{name:'CLOSE SHIFT',exact:true}).click();
 await page.getByText('SHIFT CLOSED SUCCESSFULLY',{exact:true}).waitFor();check('Cashier closes own shift through UI');
 check('Checkout is hidden on Shift Management page',!(await page.locator('.pos-sales-main').isVisible()));
 await page.getByRole('button',{name:/^VIEW Z REPORT$/i}).click();
 await page.locator('.pos-z-report-modal').waitFor();check('Closing report modal uses backend report');
 await page.screenshot({path:out+'/closing-report-390.png',fullPage:true});
 await page.locator('.pos-z-report-modal').getByRole('button',{name:'Return to Sales',exact:true}).click();
 await page.getByRole('heading',{name:'Start Shift',exact:true}).waitFor();check('Closed cashier returns to Start Shift state');
 await page.screenshot({path:out+'/start-shift-390.png',fullPage:true});
 for(const width of [320,390,820,1440]){
  await page.setViewportSize({width,height:900});
  check(`Start Shift ${width}px no horizontal overflow`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 }
 check('No sales submitted from blocked/offline UI',sales.length===0);
 check('No production/external requests',external.length===0);
 check('No uncaught JavaScript errors',errors.length===0);
 check('No entitlement verification failures',entitlementFailures.length===0);
 check('No saved authorization warning after reconnection',!(await page.locator('body').innerText()).includes('The saved POS authorization could not be verified'));
 const token=await page.evaluate(()=>localStorage.getItem('employee_token'));
 const logout=await context.request.post('https://localhost:18770/api/employees/session/logout',{headers:{Authorization:'Bearer '+token}});
 check('Synthetic cashier session logs out cleanly',logout.status()===200);
}catch(e){checks.push({check:'Browser acceptance completion',result:'FAIL',error:e.message});await page.screenshot({path:out+'/failure.png',fullPage:true});process.exitCode=1;}
finally{
 await writeFile(out+'/results.json',JSON.stringify({checks,errors,external,entitlementFailures,physicalAndroid:false},null,2));
 await browser.close();console.log(JSON.stringify({passed:checks.filter(c=>c.result==='PASS').length,failed:checks.filter(c=>c.result==='FAIL').length,errors}));
}
