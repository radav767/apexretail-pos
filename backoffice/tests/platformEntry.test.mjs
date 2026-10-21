import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../src/platformEntry.ts',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText;
const {isPlatformHost,platformEntry,platformApiBase}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
test('admin root always selects existing platform console',()=>{
 for(const host of ['admin.apexpos.cloud','ADMIN.APEXPOS.CLOUD','admin.apexpos.cloud.']){
  assert.equal(isPlatformHost(host),true);
  assert.equal(platformEntry(host,''),true);
  assert.equal(platformEntry(host,'?console=business'),true);
  assert.equal(platformApiBase(host,'https://api.apexpos.cloud/api'),'/api');
 }
});
test('other hosts preserve tenant app and original API selection',()=>{
 for(const host of ['backoffice.apexpos.cloud','pos.apexpos.cloud','localhost','admin.apexpos.cloud.attacker.test','notadmin.apexpos.cloud']){
  assert.equal(isPlatformHost(host),false);
  assert.equal(platformEntry(host,''),false);
  assert.equal(platformApiBase(host,'https://api.apexpos.cloud/api'),'https://api.apexpos.cloud/api');
 }
});
test('existing explicit platform-console entry remains compatible',()=>{
 assert.equal(platformEntry('backoffice.apexpos.cloud','?console=platform'),true);
 assert.equal(platformEntry('backoffice.apexpos.cloud','?console=PLATFORM'),false);
});
