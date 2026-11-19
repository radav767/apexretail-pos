import { chromium } from '/tmp/apex-phase11-browser-tools/node_modules/playwright/index.mjs';
import ts from '/tmp/apex-phase11-build-xijhpj7t/pos-web/node_modules/typescript/lib/typescript.js';
import { readFileSync,writeFileSync } from 'node:fs';
import { generateKeyPairSync,sign,randomUUID } from 'node:crypto';
import assert from 'node:assert/strict';
const root='/tmp/apexpos-phase11/pos-web/';
const keys=generateKeyPairSync('rsa',{modulusLength:2048,publicKeyEncoding:{type:'spki',format:'pem'},privateKeyEncoding:{type:'pkcs8',format:'pem'}});
const ring={version:1,max_token_lifetime_seconds:43200,max_offline_grace_seconds:259200,keys:[{kid:'synthetic-browser',public_key_pem:keys.publicKey}]};
const transpile=source=>ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.ESNext}}).outputText;
const moduleUrl=source=>'data:text/javascript;base64,'+Buffer.from(source).toString('base64');
let entitlement=readFileSync(root+'src/offline/entitlement.ts','utf8');
assert(entitlement.includes('const PUBLIC_KEYRING_JSON ='));
entitlement=entitlement.replace(/const PUBLIC_KEYRING_JSON =[\s\S]*?;\n/, 'const PUBLIC_KEYRING_JSON = '+JSON.stringify(JSON.stringify(ring))+';\n');
const entitlementUrl=moduleUrl(transpile(entitlement));
const leaseUrl=moduleUrl(transpile(readFileSync(root+'src/offline/lease.ts','utf8')).replace('"./entitlement.ts"',JSON.stringify(entitlementUrl)));
const ordersUrl=moduleUrl(transpile(readFileSync(root+'src/business/offlineOrders.ts','utf8')).replace('"../offline/lease.ts"',JSON.stringify(leaseUrl)));
const html='<!doctype html><title>Synthetic lease fixture</title><script type="module">'+
 `import * as lease from ${JSON.stringify(leaseUrl)}; import * as entitlements from ${JSON.stringify(entitlementUrl)}; import { OfflineOrderOutbox } from ${JSON.stringify(ordersUrl)};window.fixture={...lease,...entitlements,OfflineOrderOutbox};`+'</script>';
const origin='http://127.0.0.1:18117';const unexpected=[],errors=[];
const browser=await chromium.launch({executablePath:'/root/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell',headless:true,args:['--no-sandbox','--disable-background-networking']});
try {
 const context=await browser.newContext();
 await context.route('**/*',async route=>{
  if(route.request().url().startsWith(origin+'/'))await route.fulfill({status:200,contentType:'text/html',body:html});
  else {unexpected.push(route.request().url().split('?')[0]);await route.abort();}
 });
 const a=await context.newPage(),b=await context.newPage();for(const p of [a,b])p.on('pageerror',e=>errors.push(e.message));
 const ready=async p=>{await p.goto(origin+'/fixture');await p.waitForFunction(()=>Boolean(window.fixture));};
 await ready(a);await a.evaluate(()=>{localStorage.setItem('company_id','synthetic-company');localStorage.setItem('token','synthetic-owner');localStorage.setItem('employee_id','synthetic-employee');localStorage.setItem('employee_token','synthetic-employee-token');localStorage.setItem('device_id','synthetic-register');localStorage.setItem('device_key','synthetic-key');localStorage.setItem('branch_id','synthetic-branch');localStorage.setItem('device_assignment_revision','1');});
 await ready(b);
 const connect=async(actions={sale:true,draft:true,kitchen:true,kitchen_update:true,bar_update:true})=>{
  const nonce=await a.evaluate(()=>{window.challenge=fixture.offlineLease.beginRefresh('synthetic-company');return window.challenge.nonce;});
  const now=Math.floor(Date.now()/1000);
  const claims={sub:'synthetic-company',company_id:'synthetic-company',status:'active',token_type:'entitlement',iat:now,exp:now+43200,offline_grace_expires_at:new Date((now+86400)*1000).toISOString(),iss:'apexpos',aud:'apexpos-pos-entitlement',lease_nonce:nonce,offline_actor:{actor_type:'employee',actor_id:'synthetic-employee',session_version:0,branch_id:'synthetic-branch',device_id:'synthetic-register',assignment_revision:1,actions},features:{restaurant:true,kitchen_printing:true}};
  const encoded=[{alg:'RS256',typ:'JWT',kid:'synthetic-browser'},claims].map(v=>Buffer.from(JSON.stringify(v)).toString('base64url'));
  const token=encoded.join('.')+'.'+sign('RSA-SHA256',Buffer.from(encoded.join('.')),keys.privateKey).toString('base64url');
  const saved={company_id:'synthetic-company',status:'active',writes_allowed:true,snapshot_token:token,offline_grace_expires_at:claims.offline_grace_expires_at,snapshot_expires_at:new Date((now+43200)*1000).toISOString(),updated_at:new Date().toISOString()};
  assert.equal(await a.evaluate(async snapshot=>{const result=await fixture.offlineLease.acceptOnline(snapshot,window.challenge);if(result.ok)fixture.saveEntitlementSnapshot(snapshot);return result.ok;},saved),true);
 };
 await connect();
 await a.evaluate(async()=>{const box=new fixture.OfflineOrderOutbox(localStorage,{company:'synthetic-company',employee:'synthetic-employee',device:'synthetic-register'});await box.enqueueLicensed({id:'synthetic-command',endpoint:'/operations/offline/drafts',payload:{request_id:'synthetic-command',items:[{quantity:'2'}]}},'synthetic-company');});
 assert.equal(await b.evaluate(async()=>(await fixture.offlineLease.verify(fixture.loadEntitlementSnapshot('synthetic-company'))).ok),false);
 await b.evaluate(()=>fixture.invalidateOfflineLease());
 await a.waitForFunction(async()=>!(await fixture.offlineLease.verify(fixture.loadEntitlementSnapshot('synthetic-company'))).ok);
 assert.equal(await a.evaluate(()=>new fixture.OfflineOrderOutbox(localStorage,{company:'synthetic-company',employee:'synthetic-employee',device:'synthetic-register'}).list().length),1);
 await connect();await b.evaluate(()=>localStorage.setItem('employee_token','synthetic-other-cashier'));
 await a.waitForFunction(async()=>!(await fixture.offlineLease.verify(fixture.loadEntitlementSnapshot('synthetic-company'))).ok);
 await b.evaluate(()=>localStorage.setItem('employee_token','synthetic-employee-token'));
 assert.equal(await a.evaluate(async()=>(await fixture.offlineLease.verify(fixture.loadEntitlementSnapshot('synthetic-company'))).ok),false);
 await connect();await a.reload();await a.waitForFunction(()=>Boolean(window.fixture));
 assert.equal(await a.evaluate(async()=>(await fixture.offlineLease.verify(fixture.loadEntitlementSnapshot('synthetic-company'))).ok),false);
 const preserved=await a.evaluate(async()=>{const box=new fixture.OfflineOrderOutbox(localStorage,{company:'synthetic-company',employee:'synthetic-employee',device:'synthetic-register'});try{await box.enqueueLicensed({id:'unlicensed-command',endpoint:'/operations/offline/drafts',payload:{}},'synthetic-company');return false;}catch{return box.list().length===1 && box.list()[0].payload.items[0].quantity==='2';}});
 assert(preserved);
 await connect({sale:false,draft:false,kitchen:false,kitchen_update:false,bar_update:true});
 const permissionDenied=await a.evaluate(async()=>{
  localStorage.setItem('apexpos_offline_cashiers_v1',JSON.stringify({permissions:{sales_process:true,orders_manage:true,kitchen_update:true}}));
  try{await fixture.requireOfflineAccess('synthetic-company',[],'sale');return false;}catch{}
  try{await fixture.requireOfflineAccess('synthetic-company',[],'kitchen_update');return false;}catch{}
  await fixture.requireOfflineAccess('synthetic-company',['restaurant'],'bar_update');
  const box=new fixture.OfflineOrderOutbox(localStorage,{company:'synthetic-company',employee:'synthetic-employee',device:'synthetic-register'});
  try{await box.enqueueLicensed({id:'denied-draft',endpoint:'/operations/offline/drafts',payload:{}},'synthetic-company');return false;}catch{}
  return box.list().length===1;
 });
 assert(permissionDenied);assert.deepEqual(unexpected,[]);assert.deepEqual(errors,[]);
 const result={synthetic_only:true,chromium:browser.version(),fresh_challenge_enables_capture:true,other_tab_cannot_restore_cached_lease:true,broadcast_logout_invalidates_other_tab:true,identity_change_and_restore_cannot_reanchor:true,reload_denies_new_capture:true,original_queue_preserved:true,signed_current_actions_override_cached_permissions:true,bar_action_scoped_separately:true,unexpected_requests:unexpected,page_errors:errors,physical_or_provider_actions:false};
 writeFileSync('/tmp/phase11-lease-actor-browser.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
 await context.close();
} finally {await browser.close();}
