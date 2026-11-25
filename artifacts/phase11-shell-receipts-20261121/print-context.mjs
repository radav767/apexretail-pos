import {build} from '/tmp/apex-phase11-build-xijhpj7t/pos-web/node_modules/vite/dist/node/index.js';
import {mkdtempSync,readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const out=mkdtempSync('/tmp/phase11-print-context-');
await build({configFile:false,root:'/tmp/apex-phase11-build-xijhpj7t/pos-web',define:{'import.meta.env.VITE_API_BASE_URL':JSON.stringify('/api')},build:{outDir:out,target:'esnext',lib:{entry:'/tmp/apex-phase11-build-xijhpj7t/pos-web/src/printing/queue.ts',formats:['es'],fileName:()=> 'queue.mjs'},minify:false},logLevel:'error'});
const values=new Map();globalThis.localStorage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
globalThis.fetch=()=>{throw Error('No network allowed in print transport unit tests')};
const {deliverJob}=await import(pathToFileURL(out+'/queue.mjs'));
const payload=JSON.parse(readFileSync('/tmp/apexpos-phase11/artifacts/phase11-split-receipts-20261121/fixtures.json','utf8')).original;
function reset(){values.clear();for(const [key,value] of Object.entries({company_id:'synthetic',token:'synthetic-owner',employee_token:'synthetic-employee',employee_id:'synthetic-cashier',device_id:'synthetic-device',branch_id:'synthetic-branch',shop_id:'synthetic-shop'}))values.set(key,value)}
const results=[];
for(const key of ['employee_token','device_id','company_id']){
 reset();let resolveClaim,calls=[],sent=0;const job={id:crypto.randomUUID(),status:'pending',kind:'receipt',payload};const original=JSON.stringify(job);
 const pending=deliverJob(job,{client:{post:async(path)=>{calls.push(path);await new Promise(resolve=>resolveClaim=resolve);return {data:{}}}},transport:async()=>{sent++}});
 await Promise.resolve();values.set(key,'changed-context');resolveClaim();await assert.rejects(pending,/context changed/);assert.equal(sent,0);assert.equal(calls.length,1);assert.equal(JSON.stringify(job),original);results.push(`late claim ${key}: no transport or result`);
}
reset();let sent=0,calls=0;
await assert.rejects(deliverJob({id:crypto.randomUUID(),status:'pending',kind:'receipt',payload},{client:{post:async()=>{calls++;throw Error('lost committed claim response')}},transport:async()=>{sent++}}),/lost committed/);assert.equal(sent,0);assert.equal(calls,1);results.push('lost claim: no automatic retry or transport');
reset();calls=0;await assert.rejects(deliverJob({id:crypto.randomUUID(),status:'pending',kind:'receipt',payload},{client:{post:async()=>{calls++;return {data:{}}}},transport:async()=>{values.delete('employee_token')}}),/context changed/);assert.equal(calls,2);results.push('identity changes during fake transport: no false submitted/uncertain result under new identity');
console.log(JSON.stringify({synthetic_only:true,cases:results,real_transport_invoked:false,hardware_acceptance:false}));
