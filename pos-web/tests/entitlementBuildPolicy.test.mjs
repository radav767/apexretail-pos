import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
test('Build rejects incomplete public keyring lifetime policy before compiling assets',()=>{
 const directory=mkdtempSync(resolve(tmpdir(),'apex-entitlement-build-'));
 try{
  const path=resolve(directory,'public-keyring.json');
  writeFileSync(path,JSON.stringify({version:1,keys:[{kid:'synthetic',public_key_pem:'-----BEGIN PUBLIC KEY-----\nsynthetic\n-----END PUBLIC KEY-----'}]}));
  const result=spawnSync(process.execPath,['scripts/build-production.mjs'],{cwd:resolve(import.meta.dirname,'..'),env:{...process.env,ENTITLEMENT_PUBLIC_KEYRING_FILE:path},encoding:'utf8'});
  assert.notEqual(result.status,0);assert.match(result.stderr,/positive integer lifetime limits/);
 }finally{rmSync(directory,{recursive:true,force:true});}
});
