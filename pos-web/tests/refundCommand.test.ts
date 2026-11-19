import assert from "node:assert/strict";
import test from "node:test";
import { RefundCommands, refundActorStorageId, type RefundPayload } from "../src/refundCommand.ts";
class Storage {
  entries = new Map<string,string>();
  getItem(key:string) { return this.entries.get(key)||null; }
  setItem(key:string,value:string) { this.entries.set(key,value); }
}
function mutex() {
  let tail:Promise<unknown>=Promise.resolve();
  return async <T>(_name:string,task:()=>T|Promise<T>) => {
    const result=tail.then(task);tail=result.catch(()=>{});return result;
  };
}
const payload:RefundPayload={company_id:'synthetic-company',original_sale_id:'synthetic-sale',device_id:'register-A',reason:'Synthetic partial return',items:[{sale_item_id:'item-A',quantity:'2'}]};
function fixture() {
  const storage=new Storage(),lock=mutex();
  const make=(actor='employee:A',company='synthetic-company',sale='synthetic-sale')=>new RefundCommands(company,actor,sale,storage,lock);
  return {storage,make};
}
const result=(request:string,id='synthetic-refund')=>({id,company_id:payload.company_id,original_sale_id:payload.original_sale_id,status:'refunded',client_sale_id:request});

test('lost response/reload/concurrent tabs retain exactly the same original intent',async()=>{
  const f=fixture(),a=f.make(),b=f.make();
  const [one,two]=await Promise.all([a.prepare(payload,0),b.prepare(payload,0)]);
  assert.equal(one.request_id,two.request_id);
  assert.equal((await f.make().prepare(payload,1)).request_id,one.request_id);
  assert.deepEqual(f.make().load().pending?.payload,payload);
});
test('changed quantities, reason, register or account cannot generate another identity',async()=>{
  const f=fixture(),store=f.make();await store.prepare(payload,0);
  for(const changes of [{reason:'Different'},{device_id:'register-B'},{items:[{sale_item_id:'item-A',quantity:'3'}]}]) {
    await assert.rejects(store.prepare({...payload,...changes},0),/unconfirmed/);
  }
  await assert.rejects(f.make('employee:B').prepare(payload,0),/Another account/);
  assert.equal(f.storage.entries.size,1);
});
test('confirmed original increments generation so old forms cannot manufacture a retry UUID',async()=>{
  const f=fixture(),store=f.make(),pending=await store.prepare(payload,0);
  await store.confirm(result(pending.request_id));assert.equal(store.load().pending,undefined);
  await assert.rejects(store.prepare(payload,0),/already confirmed/);
  await assert.rejects(store.prepare(payload,1),/already confirmed/);
  const next=await store.prepare(payload,2);assert.notEqual(next.request_id,pending.request_id);
  // Late acknowledgement for the old command cannot erase a newer pending one.
  await store.confirm(result(pending.request_id));assert.equal(store.load().pending?.request_id,next.request_id);
});
test('wrong or incomplete acknowledgement preserves original intent',async()=>{
  const f=fixture(),store=f.make(),pending=await store.prepare(payload,0);
  for(const bad of [{...result(pending.request_id),client_sale_id:'other'}, {...result(pending.request_id),original_sale_id:'other'},
    {...result(pending.request_id),company_id:'other'},{...result(pending.request_id),status:'completed'}]) {
    await assert.rejects(store.confirm(bad),/does not confirm/);
    assert.equal(store.load().pending?.request_id,pending.request_id);
  }
});
test('tenant/sale isolation and credential exclusion precede submission',async()=>{
  const f=fixture(),store=f.make();
  const secretPayload={...payload,device_key:'do-not-save',manager_authorization_token:'do-not-save'};
  await store.prepare(secretPayload,0);
  assert.equal([...f.storage.entries.values()].some(value=>value.includes('do-not-save')),false);
  assert.equal(f.make('employee:A','other-company').load().pending,undefined);
  assert.equal(f.make('employee:A','synthetic-company','other-sale').load().pending,undefined);
  await assert.rejects(f.make('employee:A','other-company').prepare(payload,0),/scope changed/);
});
test('storage corruption/quota or unavailable locks fail without pretending to submit',async()=>{
  const f=fixture(),store=f.make();await store.prepare(payload,0);
  const key=[...f.storage.entries.keys()][0];f.storage.setItem(key,'broken-original');
  assert.throws(()=>store.load(),/not been cleared/);assert.equal(f.storage.getItem(key),'broken-original');
  const quota={getItem:()=>null,setItem(){throw new Error('quota');}};
  await assert.rejects(new RefundCommands('synthetic-company','employee:A','synthetic-sale',quota,mutex()).prepare(payload,0),/quota/);
  const unavailable=async<T>(_name:string,_task:()=>T|Promise<T>):Promise<T>=>{throw new Error('unavailable locks');};
  await assert.rejects(new RefundCommands('synthetic-company','employee:A','synthetic-sale',new Storage(),unavailable).prepare(payload,0),/unavailable locks/);
});
test('local actor namespace never promotes decoded data into API authority',()=>{
  const storage=new Storage();storage.setItem('employee_id','A');assert.equal(refundActorStorageId(storage),'employee:A');
  storage.entries.delete('employee_id');storage.setItem('token','unsigned.'+Buffer.from(JSON.stringify({sub:'B'})).toString('base64url')+'.untrusted');
  assert.equal(refundActorStorageId(storage),'user:B');storage.setItem('token','bad');assert.throws(()=>refundActorStorageId(storage),/Reconnect/);
});
