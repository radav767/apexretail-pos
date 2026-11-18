import assert from "node:assert/strict";
import test from "node:test";
import { generateKeyPairSync, sign } from "node:crypto";
import { OfflineLease, MAX_DISCONNECTED_MS } from "../src/offline/lease.ts";
import type { CachedEntitlementSnapshot, EntitlementKeyring, EntitlementVerificationResult } from "../src/offline/entitlement.ts";
const keys = generateKeyPairSync("rsa", { modulusLength: 2048,
  publicKeyEncoding: { type: "spki", format: "pem" }, privateKeyEncoding: { type: "pkcs8", format: "pem" } });
const server = Date.UTC(2026, 10, 18, 12);
const ring: EntitlementKeyring = { version: 1, max_token_lifetime_seconds: 43200,
  max_offline_grace_seconds: 259200, keys: [{kid:"synthetic", public_key_pem:keys.publicKey}] };
function snapshot(nonce: string, changes: Record<string, unknown> = {}): CachedEntitlementSnapshot {
  const claims = { sub:"synthetic-company", company_id:"synthetic-company", status:"active", token_type:"entitlement",
    iat:server/1000, exp:server/1000+43200, offline_grace_expires_at:new Date(server+86400000).toISOString(),
    iss:"apexpos", aud:"apexpos-pos-entitlement", lease_nonce:nonce, ...changes };
  const header = Buffer.from(JSON.stringify({alg:"RS256", typ:"JWT", kid:"synthetic"})).toString("base64url");
  const body = Buffer.from(JSON.stringify(claims)).toString("base64url");
  const signature = sign("RSA-SHA256", Buffer.from(`${header}.${body}`), keys.privateKey).toString("base64url");
  return { company_id:"synthetic-company", status:"active", writes_allowed:true,
    snapshot_token:`${header}.${body}.${signature}`, offline_grace_expires_at:"untrusted", snapshot_expires_at:"untrusted", updated_at:"untrusted" };
}
function category(result: EntitlementVerificationResult) { assert.equal(result.ok, false); return result.ok ? "" : result.category; }
function fixture() {
  let mono=0, wall=server, identity="employee-A";
  const clock=()=>({monotonic:mono,wall}); const context=()=>identity;
  const lease=new OfflineLease(clock,ring,context);
  return { lease, clock, context, tick(ms:number) { mono+=ms;wall+=ms; },
    changeClock(monotonic:number,wallChange:number) { mono+=monotonic;wall+=wallChange; },
    identity(value:string) { identity=value; } };
}
async function connected(f=fixture(), changes:Record<string,unknown>={}) {
  const request=f.lease.beginRefresh("synthetic-company"); const saved=snapshot(request.nonce,changes);
  assert.equal((await f.lease.acceptOnline(saved,request)).ok,true); return { f,saved };
}

test("fresh signed challenge establishes server time independent of initial wall-clock offset", async()=>{
  const f=fixture();f.changeClock(0,-864000000);const {saved}=await connected(f);
  f.tick(3600000);assert.equal((await f.lease.verify(saved)).ok,true);
});
test("four-hour maximum cannot be extended by reloading or restoring saved storage", async()=>{
  const {f,saved}=await connected();f.tick(MAX_DISCONNECTED_MS-1);assert.equal((await f.lease.verify(saved)).ok,true);
  f.tick(1);assert.equal(category(await f.lease.verify(saved)),"offline_lease_expired");
  const reloaded=new OfflineLease(f.clock,ring,f.context);
  assert.equal(category(await reloaded.verify(saved)),"offline_reconnect_required");
});
test("rollback, forward jump, monotonic reset and long sleep fail closed", async()=>{
  for(const jump of [[60000,-60001],[0,120001],[-1,0],[0,MAX_DISCONNECTED_MS]]) {
    const {f,saved}=await connected();f.changeClock(jump[0],jump[1]);
    assert.equal(category(await f.lease.verify(saved)),"offline_clock_changed");
    f.changeClock(-jump[0],-jump[1]);assert.equal(category(await f.lease.verify(saved)),"offline_reconnect_required");
  }
});
test("small tolerated wall adjustments cannot extend monotonic lifetime", async()=>{
  const {f,saved}=await connected();f.changeClock(MAX_DISCONNECTED_MS,MAX_DISCONNECTED_MS-30000);
  assert.equal(category(await f.lease.verify(saved)),"offline_lease_expired");
});
test("signed expiry, grace and key retirement cap the lease", async()=>{
  for(const field of ["exp","offline_grace_expires_at"]) {
    const {f,saved}=await connected(fixture(),{[field]:field==="exp"?server/1000+60:new Date(server+60000).toISOString()});
    f.tick(60001);assert.equal(category(await f.lease.verify(saved)),field==="exp"?"snapshot_expired":"offline_grace_expired");
  }
  const f=fixture();const retired={...ring,keys:[{...ring.keys[0],accept_until:new Date(server+60000).toISOString()}]};
  const lease=new OfflineLease(f.clock,retired,f.context);const request=lease.beginRefresh("synthetic-company");const saved=snapshot(request.nonce);
  assert.equal((await lease.acceptOnline(saved,request)).ok,true);f.tick(60001);
  assert.equal(category(await lease.verify(saved)),"key_retired");
});
test("old signed responses and copied challenges cannot re-anchor a lease", async()=>{
  const f=fixture();const old=f.lease.beginRefresh("synthetic-company");const oldSaved=snapshot(old.nonce);
  const current=f.lease.beginRefresh("synthetic-company");
  assert.equal(category(await f.lease.acceptOnline(oldSaved,old)),"offline_refresh_stale");
  assert.equal(category(await f.lease.acceptOnline(oldSaved,current)),"offline_challenge_mismatch");
  const next=f.lease.beginRefresh("synthetic-company");
  assert.equal(category(await f.lease.acceptOnline(snapshot(next.nonce),{...next})),"offline_refresh_stale");
});
test("late verification cannot restore access after logout or another refresh", async()=>{
  const f=fixture();const request=f.lease.beginRefresh("synthetic-company");const saved=snapshot(request.nonce);
  const pending=f.lease.acceptOnline(saved,request);f.lease.invalidate();
  assert.equal(category(await pending),"offline_refresh_stale");assert.equal(category(await f.lease.verify(saved)),"offline_reconnect_required");
  const request2=f.lease.beginRefresh("synthetic-company");const saved2=snapshot(request2.nonce);
  const old=f.lease.acceptOnline(saved2,request2);const request3=f.lease.beginRefresh("synthetic-company");const saved3=snapshot(request3.nonce);
  assert.equal((await f.lease.acceptOnline(saved3,request3)).ok,true);assert.equal(category(await old),"offline_refresh_stale");
  assert.equal((await f.lease.verify(saved3)).ok,true);
});
test("suspension and invalid signatures retire a previously good lease", async()=>{
  for(const suspended of [true,false]) {
    const {f,saved}=await connected();const request=f.lease.beginRefresh("synthetic-company");const replacement=snapshot(request.nonce,suspended?{status:"suspended"}:{});
    if(!suspended) { const parts=replacement.snapshot_token.split(".");parts[2]=(parts[2][0]==="A"?"B":"A")+parts[2].slice(1);replacement.snapshot_token=parts.join("."); }
    assert.equal(category(await f.lease.acceptOnline(replacement,request)),suspended?"subscription_not_writable":"invalid_signature");
    assert.equal(category(await f.lease.verify(saved)),"offline_reconnect_required");
  }
});
test("tenant or cashier/register context changes require a fresh online proof", async()=>{
  const {f,saved}=await connected();f.identity("employee-B");assert.equal(category(await f.lease.verify(saved)),"offline_clock_changed");
  f.identity("employee-A");assert.equal(category(await f.lease.verify(saved)),"offline_reconnect_required");
  const other=await connected();assert.equal(category(await other.f.lease.verify({...other.saved,company_id:"other"})),"offline_reconnect_required");
});
test("delayed challenge response cannot extend the lease or revive an expired request", async()=>{
  const f=fixture();const request=f.lease.beginRefresh("synthetic-company");f.tick(60001);
  assert.equal(category(await f.lease.acceptOnline(snapshot(request.nonce),request)),"offline_clock_changed");
});
