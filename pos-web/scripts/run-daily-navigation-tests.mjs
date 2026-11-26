import {readFileSync,mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import ts from 'typescript';
import assert from 'node:assert/strict';
const root=resolve(import.meta.dirname,'..'),out=mkdtempSync(join(tmpdir(),'apex-daily-nav-'));
try{
 for(const name of ['salesReports','dailyPos']){
  const source=readFileSync(join(root,'src/navigation',name+'.ts'),'utf8');
  const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.ESNext}}).outputText.replace("'./salesReports'","'./salesReports.mjs'");writeFileSync(join(out,name+'.mjs'),compiled);
 }
 const {canOpenSalesDestination:can,salesDestinationFor:target}=await import(join(out,'salesReports.mjs'));
 const {dailyPosDestinations:daily,isDailyPosRoute:isDaily}=await import(join(out,'dailyPos.mjs'));
 assert.deepEqual(daily({role:'owner'}).map(x=>x.id),['history','returns','shift','z']);
 assert.deepEqual(daily({role:'cashier',permissions:{}}).map(x=>x.id),['shift']);
 assert.deepEqual(daily({role:'cashier',permissions:{sales_history_view:false,sales:true}}).map(x=>x.id),['shift']);
 assert.ok(can({role:'cashier',permissions:{sales:true}},'history'));
 assert.equal(can({role:'custom',permissions:{revenue_view:true}},'reconciliation'),false);
 assert.equal(can({role:'custom',permissions:{revenue_view:true,credit_settlements:true}},'reconciliation'),true);
 assert.equal(can({role:'owner'},'unknown'),false);assert.equal(can(null,'shift'),false);
 for(const [module,feature] of [['Products','all-products'],['Inventory','stock-counts'],['Reports','sales-reports'],['Settings','business'],['Settings','presentation'],['Expenses','home']])assert.equal(isDaily(module,feature),false);
 for(const [module,feature] of [['Sales Management','transaction-history'],['Sales Management','z-reports'],['Inventory','inventory-overview'],['Settings','printer'],['Shift Management','home']])assert.equal(isDaily(module,feature),true);
 assert.equal(target('Sales Management','cashier-shifts').id,'shift');assert.equal(target('Sales Management','credit-settlement').id,'credit');
 console.log('Daily navigation behavior: owner/restricted/granular denial, recovery, legacy aliases, Backoffice-only administration passed');
}finally{rmSync(out,{recursive:true,force:true})}
