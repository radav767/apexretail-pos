import {chromium} from '/tmp/apex-phase11-browser-tools/node_modules/playwright/index.mjs';
import {build} from '/tmp/apex-phase11-build-xijhpj7t/pos-web/node_modules/vite/dist/node/index.js';
import react from '/tmp/apex-phase11-build-xijhpj7t/pos-web/node_modules/@vitejs/plugin-react/dist/index.js';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join,extname} from 'node:path';
import assert from 'node:assert/strict';
const root='/tmp/apex-phase11-build-xijhpj7t/pos-web',dir=root+'/customer-fixture';mkdirSync(dir,{recursive:true});
writeFileSync(dir+'/index.html','<!doctype html><div id="root"></div><script type="module" src="/customer-fixture/main.tsx"></script>');
writeFileSync(dir+'/main.tsx',`import React from 'react';import {createRoot} from 'react-dom/client';import Inline from '../src/components/InlineCustomerCreate';import {advanceAuthenticationEpoch} from '../src/api/authLifecycle';
window.posts=[];window.created=[];window.advance=advanceAuthenticationEpoch;
const client={post:(path,payload)=>new Promise((resolve,reject)=>window.posts.push({path,payload,resolve,reject}))};
const cart=JSON.stringify({items:[{id:'P1',quantity:'2.5',price:'3.40'}],discount:'.25',tender:'20.00',method:'cash'});
createRoot(document.getElementById('root')).render(<><output data-testid="cart">{cart}</output><Inline companyId="company-A" actorKey="employee-A" client={client} onCreated={value=>window.created.push(value)}/></>);`);
await build({configFile:false,root,plugins:[react()],build:{outDir:dir+'/dist',emptyOutDir:true,rolldownOptions:{input:dir+'/index.html'}},logLevel:'warn'});
const origin='http://127.0.0.1:18117',unexpected=[],errors=[];
const browser=await chromium.launch({executablePath:'/root/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell',headless:true,args:['--no-sandbox','--disable-background-networking']});
try{
 const context=await browser.newContext();await context.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin!==origin){unexpected.push(u.origin);await route.abort();return;}const path=u.pathname==='/'?'/customer-fixture/index.html':u.pathname;const file=dir+'/dist'+path;try{await route.fulfill({status:200,contentType:extname(file)==='.js'?'text/javascript':extname(file)==='.css'?'text/css':'text/html',body:readFileSync(file)});}catch{unexpected.push(path);await route.abort();}});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto(origin+'/');
 await page.getByRole('button',{name:'New customer',exact:true}).waitFor();
 const cart=await page.getByTestId('cart').textContent();
 await page.getByRole('button',{name:'New customer',exact:true}).click();await page.getByLabel('Name',{exact:true}).fill('Synthetic inline contact');await page.getByLabel('Phone',{exact:true}).fill('000000000');await page.getByRole('button',{name:'Save customer',exact:true}).click();await page.waitForFunction(()=>window.posts.length===1);
 const original=await page.evaluate(()=>window.posts[0].payload);assert.equal(original.credit_enabled,undefined);assert.equal(original.device_key,undefined);
 await page.evaluate(()=>window.posts[0].reject(new Error('synthetic lost response')));await page.getByRole('button',{name:'Retry customer creation'}).waitFor();assert.equal(await page.getByLabel('Name',{exact:true}).isDisabled(),true);
 await page.reload();await page.getByRole('button',{name:'New customer',exact:true}).click();await page.getByRole('button',{name:'Retry customer creation'}).click();await page.waitForFunction(()=>window.posts.length===1);
 assert.deepEqual(await page.evaluate(()=>window.posts[0].payload),original);
 const confirm=async index=>page.evaluate(index=>{const request=window.posts[index];request.resolve({data:{id:crypto.randomUUID(),company_id:request.payload.company_id,customer_code:'POS-'+request.payload.request_id.replaceAll('-','').toUpperCase(),name:request.payload.name,active:true,credit_enabled:false,unlimited_credit:false,credit_limit:null,credit_terms_days:0,outstanding_balance:'0.00',available_credit:null}})},index);
 await confirm(0);await page.waitForFunction(()=>window.created.length===1);assert.equal(await page.getByTestId('cart').textContent(),cart);
 await page.getByRole('button',{name:'New customer',exact:true}).click();await page.getByLabel('Name',{exact:true}).fill('Synthetic late contact');await page.getByRole('button',{name:'Save customer',exact:true}).click();await page.waitForFunction(()=>window.posts.length===2);
 await page.evaluate(()=>{localStorage.setItem('employee_token','synthetic-new-actor');window.advance()});await confirm(1);await page.getByRole('button',{name:'Retry customer creation'}).waitFor();assert.equal(await page.evaluate(()=>window.created.length),1);
 assert.equal(await page.evaluate(()=>Object.keys(sessionStorage).filter(key=>key.startsWith('apexretail_checkout_customer_v1:')).length),1);assert.equal(await page.getByTestId('cart').textContent(),cart);
 // Actual command store fails closed on damaged evidence without any request.
 await page.reload();await page.evaluate(()=>{for(const key of Object.keys(sessionStorage))sessionStorage.setItem(key,'{broken')});await page.getByRole('button',{name:'New customer',exact:true}).click();await page.getByText('The pending customer request needs review.',{exact:false}).waitFor();assert.equal(await page.evaluate(()=>window.posts.length),0);
 assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);
 const result={synthetic_only:true,lost_response_reload_retains_request_id_and_contact:true,no_credit_or_credentials_in_command:true,cart_quantity_price_discount_tender_unchanged:true,late_identity_response_cannot_select_customer:true,unconfirmed_request_retained_after_identity_change:true,damaged_evidence_blocks_new_request:true,page_errors:errors,unexpected_requests:unexpected,real_messages_or_provider_actions:false};writeFileSync('/tmp/phase11-checkout-customer-browser.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}finally{await browser.close()}
