// Local evidence packaging only: no DB, deployment, signing or APK commands.
import assert from "node:assert/strict";
import {cp,copyFile,mkdir,readFile,readdir,writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {createHash} from "node:crypto";
import {execFileSync} from "node:child_process";
const root=resolve(import.meta.dirname,"../..");const base="d691e58438d7fd4683a41727cb7b332c6ff77b5c";
const output="/root/apexretail-pos/artifacts/phase7e-completion-20261020";
const git=args=>execFileSync("git",args,{cwd:root,encoding:"utf8"}).trim();
assert.equal(git(["status","--porcelain"]),"");execFileSync("git",["merge-base","--is-ancestor",base,"HEAD"],{cwd:root});
assert.equal(git(["diff","--name-only",base,"HEAD","--","pos-web/android","backend/migrations"]),"","No native or migration changes expected");
assert.match(await readFile("/tmp/phase7e-backend-final.log","utf8"),/374 passed, 6 warnings, 126 subtests passed/);
const xml=await readFile("/tmp/phase7e-completion-backend.xml","utf8");assert.ok(!/<(?:failure|error|skipped)[\s>]/.test(xml));
const frontend=JSON.parse(await readFile(resolve(root,"phase7e-evidence/completion/frontend/frontend-test-results.json"),"utf8"));assert.equal(frontend.length,24);assert.ok(frontend.every(r=>r.status==="PASS"&&r.exitCode===0));
const preview=JSON.parse(await readFile(resolve(root,"phase7e-evidence/completion/preview/checks.json"),"utf8"));assert.equal(preview.checks.length,16);assert.equal(preview.syntheticOnly,true);
const backup=JSON.parse(await readFile("/tmp/phase7e-completion-backup.json","utf8"));assert.equal(backup.allHistoricalHashesUnchanged,true);assert.equal(backup.productionAccessed,false);
const matrix=JSON.parse(await readFile(resolve(root,"phase7e-evidence/completion/audit/acceptance-summary.json"),"utf8"));assert.equal(matrix.automatedFailures,0);assert.equal(matrix.allActionsVerified,false);
await mkdir(output,{mode:0o700}); // Existing bundles cannot be overwritten.
for(const [from,to] of [[resolve(root,"PHASE7E-COMPLETION.md"),"PHASE7E-COMPLETION-REPORT.md"],["/tmp/phase7e-backend-final.log","backend-regression.log"],["/tmp/phase7e-completion-backend.xml","backend-regression.xml"],["/tmp/phase7e-completion-backup.json","backup-verification.json"]])await copyFile(from,resolve(output,to));
for(const name of ["frontend","preview","audit"])await cp(resolve(root,"phase7e-evidence/completion",name),resolve(output,name),{recursive:true});
async function list(folder,prefix=""){const result=[];for(const e of await readdir(folder,{withFileTypes:true})){const file=prefix+e.name;if(e.isDirectory())result.push(...await list(resolve(folder,e.name),file+"/"));else{assert.ok(e.isFile());result.push(file);}}return result;}
const buildSums=[];
for(const project of ["pos-web","backoffice"]){
 const dist=resolve(root,project,"dist");const index=await readFile(resolve(dist,"index.html"),"utf8");for(const m of index.matchAll(/(?:src|href)="(\/assets\/[^"?#]+)"/g))await readFile(resolve(dist,m[1].slice(1)));
 const files=await list(dist);const js=(await Promise.all(files.filter(f=>f.endsWith(".js")).map(f=>readFile(resolve(dist,f),"utf8")))).join("\n");
 assert.ok(js.includes("https://api.apexpos.cloud/api"));assert.ok(!js.includes("__completionCalls")&&!js.includes("synthetic-transfer-receipt"));if(project==="pos-web")assert.ok(js.includes("prod-2026-10-13-r1"));
 for(const file of files)buildSums.push(`${createHash("sha256").update(await readFile(resolve(dist,file))).digest("hex")}  builds/${project}/${file}`);
 await cp(dist,resolve(output,"builds",project),{recursive:true});
}
await writeFile(resolve(output,"BUILD-SHA256SUMS"),buildSums.join("\n")+"\n");
await writeFile(resolve(output,"changed-files.txt"),git(["diff","--name-status",base,"HEAD"])+"\n");
execFileSync("git",["archive","--format=tar.gz",`--output=${resolve(output,"phase7e-completion-source.tar.gz")}`,"HEAD"],{cwd:root});
execFileSync("zip",["-qr",resolve(output,"phase7e-completion-preview.zip"),"."],{cwd:resolve(output,"preview")});
const commit=git(["rev-parse","HEAD"]);
await writeFile(resolve(output,"release.json"),JSON.stringify({commit,base,branch:git(["branch","--show-current"]),status:"PENDING_ACCEPTANCE_NOT_READY",backend:{passed:374,permissionSubtests:126,failed:0,skipped:0,warnings:6},frontendCommands:24,newBrowserChecks:16,newScreenshots:16,sourceControls:matrix.sourceControls,allActionsVerified:false,newMigrations:[],existingMigrationHead:"p7j_variant_batches",archivedBackupDate:backup.archivedBackupDate,historicalTablesPreserved:34,historicalRowsPreserved:809,physicalAndroid:"PENDING",physicalPrinters:"PENDING",liveProductionVerification:"PENDING",productionAccessed:false,deployed:false,apkBuilt:false,androidSourceChanged:false},null,2));
const files=(await list(output)).sort();const sums=[];for(const file of files)sums.push(`${createHash("sha256").update(await readFile(resolve(output,file))).digest("hex")}  ${file}`);await writeFile(resolve(output,"SHA256SUMS"),sums.join("\n")+"\n");
console.log(JSON.stringify({output,commit,status:"PENDING_ACCEPTANCE_NOT_READY",files:files.length},null,2));
