// Protected local development evidence only. No deployment, DB connection or APK.
import assert from "node:assert/strict";
import { cp, copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
const root=resolve(import.meta.dirname,"../..");
const output="/root/apexretail-pos/artifacts/phase7e-stabilization-20261020";
const base="413eebc368ed1b50ff6e4df5ece65fa148a002cb";
const git=args=>execFileSync("git",args,{cwd:root,encoding:"utf8"}).trim();
assert.equal(git(["status","--porcelain"]),"","Commit reviewed source before packaging");
execFileSync("git",["merge-base","--is-ancestor",base,"HEAD"],{cwd:root});
assert.equal(git(["diff","--name-only",base,"HEAD","--","pos-web/android","pos-web/capacitor.config.ts"]),"");
const log=await readFile("/tmp/phase7e-backend-final.log","utf8");
assert.match(log,/365 passed, 6 warnings, 126 subtests passed/);
const xml=await readFile("/tmp/phase7e-stabilization-backend.xml","utf8");
assert.ok(!/<(?:failure|error|skipped)[\s>]/.test(xml));
const frontend=JSON.parse(await readFile(resolve(root,"phase7e-evidence/stabilization/frontend/frontend-test-results.json"),"utf8"));
assert.equal(frontend.length,24);assert.ok(frontend.every(result=>result.status==="PASS"&&result.exitCode===0));
const matrix=JSON.parse(await readFile(resolve(root,"phase7e-evidence/stabilization/audit/acceptance-summary.json"),"utf8"));
assert.equal(matrix.backend_xml_cases,365);assert.equal(matrix.source_controls,762);assert.equal(matrix.all_actions_verified,false);
const preview=JSON.parse(await readFile(resolve(root,"phase7e-evidence/stabilization/preview/checks.json"),"utf8"));
assert.equal(preview.checks.length,9);assert.equal(preview.screenshots,8);assert.equal(preview.syntheticOnly,true);
const rehearsalFiles=["/tmp/apexretail_phase7e_stabilization_clone_20261020-rehearsal.json","/tmp/apexretail_phase7e_stabilization_empty_20261020-rehearsal.json"];
for(const file of rehearsalFiles){const data=JSON.parse(await readFile(file,"utf8"));assert.equal(data.stages.length,12);assert.ok(data.stages.every(s=>s.historical_content_unchanged));assert.equal(data.stages.at(-1).revision,"p7j_variant_batches");}
await mkdir(output,{mode:0o700}); // Refuse overwrite of an existing reviewed bundle.
for(const [from,to] of [[resolve(root,"PHASE7E-STABILIZATION.md"),"PHASE7E-STABILIZATION-REPORT.md"],["/tmp/phase7e-backend-final.log","backend-regression.log"],["/tmp/phase7e-stabilization-backend.xml","backend-regression.xml"],[rehearsalFiles[0],"restored-backup-rehearsal.json"],[rehearsalFiles[1],"empty-database-rehearsal.json"],["/tmp/phase7a1-entitlement-public-keyring.json","entitlement-public-keyring.json"]])await copyFile(from,resolve(output,to));
for(const [from,to] of [["phase7e-evidence/stabilization/frontend","frontend"],["phase7e-evidence/stabilization/audit","audit"],["phase7e-evidence/stabilization/preview","preview/stabilization"],["phase7e-evidence/tips/preview","preview/tips"],["phase7e-evidence/screenshots","preview/modules"]])await cp(resolve(root,from),resolve(output,to),{recursive:true});
async function list(folder,prefix=""){
  const result=[];
  for(const entry of await readdir(folder,{withFileTypes:true})){const relative=prefix+entry.name;if(entry.isDirectory())result.push(...await list(resolve(folder,entry.name),relative+"/"));else {assert.ok(entry.isFile(),"Unexpected non-file release entry");result.push(relative);}}
  return result;
}
const buildHashes=[];
for(const project of ["pos-web","backoffice"]){
  const dist=resolve(root,project,"dist");const index=await readFile(resolve(dist,"index.html"),"utf8");
  for(const match of index.matchAll(/(?:src|href)="(\/assets\/[^"?#]+)"/g))await readFile(resolve(dist,match[1].slice(1)));
  const files=await list(dist);const js=files.filter(f=>f.endsWith(".js"));assert.ok(js.length>0);
  const bundle=(await Promise.all(js.map(f=>readFile(resolve(dist,f),"utf8")))).join("\n");
  assert.ok(bundle.includes("https://api.apexpos.cloud/api"));
  assert.ok(!bundle.includes("__stabilizationCalls")&&!bundle.includes("__tipCalls"),"Synthetic test adapter leaked into production build");
  if(project==="pos-web")assert.ok(bundle.includes("prod-2026-10-13-r1"),"Approved public entitlement key missing");
  for(const file of files)buildHashes.push(`${createHash("sha256").update(await readFile(resolve(dist,file))).digest("hex")}  builds/${project}/${file}`);
  await cp(dist,resolve(output,"builds",project),{recursive:true});
}
await writeFile(resolve(output,"BUILD-SHA256SUMS"),buildHashes.join("\n")+"\n");
await writeFile(resolve(output,"changed-files.txt"),git(["diff","--name-status",base,"HEAD"])+"\n");
execFileSync("git",["archive","--format=tar.gz",`--output=${resolve(output,"phase7e-stabilization-source.tar.gz")}`,"HEAD"],{cwd:root});
const images=(await list(resolve(output,"preview"))).filter(f=>f.endsWith(".png")).sort();assert.equal(images.length,106);
await writeFile(resolve(output,"preview/index.html"),`<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Phase 7E stabilization review</title><style>body{font:16px system-ui;background:#f5f7f8;color:#20252b;margin:16px}h1{color:#07583b}article{max-width:1100px;margin:24px auto}img{width:100%;border:1px solid #ddd;border-radius:12px}</style><h1>ApexRetail · Phase 7E stabilization</h1><p>Actual React components · Synthetic data · Not deployed · Release blocked</p>${images.map(name=>`<article><h2>${name}</h2><a href="${name}"><img loading="lazy" src="${name}"></a></article>`).join("")}`);
execFileSync("zip",["-qr",resolve(output,"phase7e-stabilization-preview.zip"),"."],{cwd:resolve(output,"preview")});
const commit=git(["rev-parse","HEAD"]);
await writeFile(resolve(output,"release.json"),JSON.stringify({commit,base,branch:git(["branch","--show-current"]),status:"PARTIAL_NO_GO",backend:{passed:365,permissionSubtests:126,warnings:6,failed:0,skipped:0},frontendCommands:24,screenshots:106,sourceControls:762,allActionsVerified:false,migrations:["p7j_variant_batches"],restoredBackupDate:"2026-10-16",historicalTablesPreserved:34,historicalRowsPreserved:809,migrationStagesPerDatabase:12,deployed:false,productionAccessed:false,apkBuilt:false,androidSourceChanged:false,physicalDevicesVerified:false,node:process.version},null,2));
const files=(await list(output)).sort();const sums=[];
for(const file of files)sums.push(`${createHash("sha256").update(await readFile(resolve(output,file))).digest("hex")}  ${file}`);
await writeFile(resolve(output,"SHA256SUMS"),sums.join("\n")+"\n");
console.log(JSON.stringify({output,commit,status:"PARTIAL_NO_GO",files:files.length,sourceControls:762,screenshots:images.length},null,2));
