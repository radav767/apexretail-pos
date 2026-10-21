// Actual application entry point. Synthetic platform responses, loopback assets.
// Browser routing intercepts admin hostname before networking; no production calls.
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createServer} from 'vite';
import {chromium} from '/root/.npm/_npx/420ff84f11983ee5/node_modules/playwright/index.mjs';
const root=fileURLToPath(new URL('..',import.meta.url)),out=fileURLToPath(new URL('../../artifacts/phase10-domain',import.meta.url));await mkdir(out,{recursive:true});
const server=await createServer({root,server:{host:'127.0.0.1',port:18936,strictPort:true}});await server.listen();
const browser=await chromium.launch({executablePath:'/tmp/apexretail-pw-browsers/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']});
const context=await browser.newContext(),calls=[],errors=[],external=[],checks=[];
await context.route('**/*',async route=>{
 const req=route.request(),url=new URL(req.url());
 if(url.hostname!=='admin.apexpos.cloud'){external.push(req.url());await route.abort();return;}
 if(url.pathname.startsWith('/api/')){
  calls.push({path:url.pathname,authorization:req.headers().authorization});
  let data={},status=200;
  if(url.pathname==='/api/platform/login')data={challenge:'synthetic-test-challenge-not-a-real-credential',mfa_required:true,enrollment_required:false};
  else if(url.pathname==='/api/platform/mfa')data={access_token:'apx_platform_synthetic_only',role:'support',admin_id:'synthetic-support'};
  else if(req.headers().authorization!=='Bearer apx_platform_synthetic_only'){status=401;data={detail:'Platform authentication required'};}
  else if(url.pathname==='/api/platform/dashboard')data={businesses:1,subscriptions:{active:1,trial:0,expired:0},revenue:[]};
  else if(url.pathname==='/api/platform/plans'||url.pathname==='/api/platform/businesses')data=[];
  else if(url.pathname==='/api/platform/settings')data={brand_name:'ApexRetail',version:0,trial_days:30,business_types:['Retail']};
  else if(url.pathname==='/api/platform/logout')data={ok:true};
  else throw Error('Unexpected platform route: '+url.pathname);
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});return;
 }
 const response=await route.fetch({url:'http://127.0.0.1:18936'+url.pathname+url.search});await route.fulfill({response});
});
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
const pass=name=>checks.push(name);
try{
 await page.addInitScript(()=>localStorage.setItem('backoffice_token','synthetic-business-token-not-valid'));
 await page.goto('http://admin.apexpos.cloud:18936/?console=business');
 await page.getByRole('button',{name:'Sign in',exact:true}).waitFor();pass('Dedicated host root selects existing platform login even with tenant query');
 await page.getByLabel('Email',{exact:true}).fill('preview@example.test');await page.getByLabel('Password',{exact:true}).fill('synthetic-password-not-real');await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await page.getByLabel('Authentication code',{exact:true}).waitFor();assert.equal(calls[0].path,'/api/platform/login');assert.equal(calls[0].authorization,undefined);pass('Same-origin platform login does not send saved business token');
 assert.equal(await page.getByRole('navigation').count(),0);pass('MFA challenge does not unlock management navigation');
 await page.getByLabel('Authentication code',{exact:true}).fill('123456');await page.getByRole('button',{name:'Verify code',exact:true}).click();await page.getByRole('heading',{name:'Dashboard',exact:true}).waitFor();
 assert.equal(calls[1].path,'/api/platform/mfa');assert.ok(calls.every(c=>c.path.startsWith('/api/platform/')));pass('MFA and console API paths remain under restricted same-origin proxy');
 assert.equal(await page.getByRole('navigation').getByRole('button',{name:'Administrators',exact:true}).count(),0);pass('Support role has no administrator controls');
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:out+'/admin-domain-mobile.png',fullPage:true});pass('Dedicated domain console is usable at Android phone width');
 await page.getByRole('button',{name:'Log out',exact:true}).click();await page.getByRole('button',{name:'Sign in',exact:true}).waitFor();assert.equal(await page.evaluate(()=>localStorage.getItem('backoffice_token')),'synthetic-business-token-not-valid');pass('Platform logout preserves tenant local storage');
 await page.evaluate(()=>sessionStorage.setItem('apex_platform_session_v1',JSON.stringify({access_token:'synthetic-business-token-not-valid',role:'super_admin',admin_id:'fake'})));
 await page.reload();await page.getByRole('button',{name:'Sign in',exact:true}).waitFor();pass('Backend rejection clears forged platform session without granting access');
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);pass('No production/external requests or uncaught browser errors');
}catch(e){process.exitCode=1;console.error(e);await page.screenshot({path:out+'/failure.png',fullPage:true});}
finally{await writeFile(out+'/browser-results.json',JSON.stringify({checks,calls,errors,external,synthetic:true,passed:!process.exitCode},null,2));await browser.close();await server.close();console.log(JSON.stringify({checks:checks.length,passed:!process.exitCode}));}
