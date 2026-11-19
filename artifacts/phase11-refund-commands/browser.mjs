import {chromium} from '/tmp/apex-phase11-browser-tools/node_modules/playwright/index.mjs';
import ts from '/tmp/apex-phase11-build-xijhpj7t/pos-web/node_modules/typescript/lib/typescript.js';
import {readFileSync,writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const source=readFileSync('/tmp/apexpos-phase11/pos-web/src/refundCommand.ts','utf8');
const js=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.ESNext}}).outputText;
const url='data:text/javascript;base64,'+Buffer.from(js).toString('base64');
const html='<!doctype html><title>Synthetic refund intent</title><script type="module">import * as fixture from '+JSON.stringify(url)+';window.fixture=fixture;window.store=new fixture.RefundCommands("synthetic-company","employee:A","synthetic-sale");window.generation=store.load().generation;</script>';
const origin='http://127.0.0.1:18118';const unexpected=[],errors=[];
const browser=await chromium.launch({executablePath:'/root/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell',headless:true,args:['--no-sandbox','--disable-background-networking']});
try {
 const context=await browser.newContext();await context.route('**/*',async route=>{
  if(route.request().url().startsWith(origin+'/'))await route.fulfill({status:200,contentType:'text/html',body:html});
  else{unexpected.push(route.request().url().split('?')[0]);await route.abort();}
 });
 const a=await context.newPage(),b=await context.newPage();for(const p of [a,b])p.on('pageerror',e=>errors.push(e.message));
 const ready=async p=>{await p.goto(origin+'/fixture');await p.waitForFunction(()=>Boolean(window.store));};await ready(a);await ready(b);
 const payload={company_id:'synthetic-company',original_sale_id:'synthetic-sale',device_id:'synthetic-register',reason:'Synthetic partial refund',items:[{sale_item_id:'synthetic-item',quantity:'2'}]};
 const prepare=p=>p.evaluate(async payload=>await store.prepare(payload,generation),payload);
 const [first,second]=await Promise.all([prepare(a),prepare(b)]);assert.equal(first.request_id,second.request_id);
 await a.reload();await a.waitForFunction(()=>Boolean(window.store));const restored=await prepare(a);assert.equal(restored.request_id,first.request_id);
 const acknowledged={id:'synthetic-refund',company_id:'synthetic-company',original_sale_id:'synthetic-sale',client_sale_id:first.request_id,status:'refunded'};
 await a.evaluate(async result=>await store.confirm(result),acknowledged);
 const stale=await b.evaluate(async payload=>{try{await store.prepare(payload,generation);return false;}catch(error){return error.message.includes('already confirmed');}},payload);assert(stale);
 await b.reload();await b.waitForFunction(()=>Boolean(window.store));const next=await prepare(b);assert.notEqual(next.request_id,first.request_id);
 await a.evaluate(async result=>await store.confirm(result),acknowledged);
 assert.equal(await a.evaluate(()=>store.load().pending.request_id),next.request_id);
 const actorDenied=await a.evaluate(async payload=>{try{await new fixture.RefundCommands('synthetic-company','employee:B','synthetic-sale').prepare(payload,0);return false;}catch(error){return error.message.includes('Another account');}},payload);assert(actorDenied);
 assert.deepEqual(unexpected,[]);assert.deepEqual(errors,[]);
 const result={synthetic_only:true,chromium:browser.version(),real_browser_web_locks:true,two_tabs_one_refund_uuid:true,reload_preserves_request:true,stale_form_cannot_create_new_uuid_after_confirmation:true,late_ack_cannot_erase_new_intent:true,account_change_does_not_replace_unconfirmed_request:true,acknowledgement_shape_fixture_only:true,unexpected_requests:unexpected,page_errors:errors,api_provider_or_payment_actions:false};
 writeFileSync('/tmp/phase11-refund-browser.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));await context.close();
}finally{await browser.close();}
