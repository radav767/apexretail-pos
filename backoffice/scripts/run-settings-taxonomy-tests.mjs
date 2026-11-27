import {readFileSync,mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import ts from 'typescript';
import assert from 'node:assert/strict';
const root=resolve(import.meta.dirname,'..'),out=mkdtempSync(join(tmpdir(),'apex-bo-taxonomy-'));
try{
 const source=readFileSync(join(root,'src/pages/settingsTaxonomy.ts'),'utf8');writeFileSync(join(out,'taxonomy.mjs'),ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.ESNext}}).outputText);
 const {settingsGroups,settingsGroup,filteredSettingsGroups}=await import(join(out,'taxonomy.mjs'));
 assert.deepEqual(settingsGroups.map(group=>group.title),['Business & Branches','Users & Security','Products & Inventory','Sales & Checkout','Customers & Credit','Payments & Currencies','Printers & Devices','Documents & Branding','Appearance & Navigation','Subscriptions & Integrations']);
 assert.equal(new Set(settingsGroups.map(group=>group.id)).size,10);
 assert.deepEqual([...new Set(settingsGroups.flatMap(group=>group.entries.map(entry=>entry.section).filter(Boolean)))].sort(),['company','currencies','devices','fiscal','presentation','printers','receipts','shops','subscription','tips']);
 for(const entry of settingsGroups.flatMap(group=>group.entries)){if(entry.workspace){if(entry.workspace.page==='inventory'){assert.equal(entry.workspace.inventoryTab,'workflows');assert.equal(entry.workspace.workflowTab,'documents')}assert.ok(!['sales','reports','credit-settlements','expenses','shift-reports'].includes(entry.workspace.page));assert.notEqual(entry.workspace.feature,'composites')}}
 assert.equal(settingsGroup('__proto__'),null);assert.equal(settingsGroup('unknown'),null);assert.equal(settingsGroup(null),null);
 assert.equal(filteredSettingsGroups('').length,10);assert.deepEqual(filteredSettingsGroups('pReSeNtAtIoN').map(group=>group.id),['appearance-navigation']);assert.equal(filteredSettingsGroups('nothingmatches').length,0);
 console.log('Approved exact ten sections, complete original leaf coverage, operational separation, recipe boundary, search and unknown-group rejection passed');
}finally{rmSync(out,{recursive:true,force:true})}
