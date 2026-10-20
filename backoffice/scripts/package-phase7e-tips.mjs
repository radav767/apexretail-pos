// Local development-review bundle. No deployment, DB calls, signing or APK.
import assert from "node:assert/strict";
import { cp, copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
const root = resolve(import.meta.dirname, "../..");
const output = "/root/apexretail-pos/artifacts/phase7e-tips-20261020";
const git = args => execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim();
assert.equal(git(["status","--porcelain"]), "", "Commit reviewed sources first");
assert.equal(git(["diff","--name-only","ff05b36b40196e369ad3f4324cf7eea2dee9af8f","HEAD","--","pos-web/android","pos-web/capacitor.config.ts"]), "", "Android source must remain unchanged");
const backend = await readFile("/tmp/phase7e-backend-final.log","utf8");
assert.match(backend,/351 passed, 6 warnings, 126 subtests passed/);
const frontend = JSON.parse(await readFile(resolve(root,"phase7e-evidence/tips/frontend-final/frontend-test-results.json"),"utf8"));
assert.equal(frontend.length,24); assert.ok(frontend.every(result=>result.status === "PASS"));
const preview = JSON.parse(await readFile(resolve(root,"phase7e-evidence/tips/preview/checks.json"),"utf8"));
assert.equal(preview.checks.length,12); assert.equal(preview.screenshots,12); assert.equal(preview.syntheticOnly,true);
const migration = JSON.parse(await readFile("/tmp/apexretail_phase7e_tips_clone_20261020-rehearsal.json","utf8"));
assert.equal(migration.stages.length,11); assert.ok(migration.stages.every(stage=>stage.historical_content_unchanged));
const synthetic = JSON.parse(await readFile("/tmp/apexretail_phase7e_synthetic_rehearsal-rehearsal.json","utf8"));
assert.equal(synthetic.stages.length,11);
const guards = JSON.parse(await readFile("/tmp/phase7e-tip-guards.json","utf8"));
assert.equal(guards.all_tables_unchanged,true); assert.equal(guards.tables_checked,64);
await mkdir(output,{mode:0o700});
for (const [source,destination] of [
  [resolve(root,"PHASE7E-TIPS-AND-RECOVERY.md"),"PHASE7E-CONTINUATION-REPORT.md"],
  ["/tmp/phase7e-backend-final.log","backend-regression.log"],
  ["/tmp/apexretail_phase7e_tips_clone_20261020-rehearsal.json","restored-backup-rehearsal.json"],
  ["/tmp/apexretail_phase7e_synthetic_rehearsal-rehearsal.json","synthetic-rehearsal.json"],
  ["/tmp/phase7e-tip-guards.json","tip-downgrade-guard.json"],
  ["/tmp/phase7a1-entitlement-public-keyring.json","entitlement-public-keyring.json"],
]) await copyFile(source,resolve(output,destination));
await cp(resolve(root,"phase7e-evidence/tips/frontend-final"),resolve(output,"frontend-verification"),{recursive:true});
await cp(resolve(root,"phase7e-evidence/tips/preview"),resolve(output,"preview"),{recursive:true});
for (const project of ["pos-web","backoffice"]) await cp(resolve(root,project,"dist"),resolve(output,"builds",project),{recursive:true});
await writeFile(resolve(output,"changed-files.txt"),git(["diff","--name-only","ff05b36b40196e369ad3f4324cf7eea2dee9af8f","HEAD"])+"\n");
execFileSync("git",["archive","--format=tar.gz",`--output=${resolve(output,"phase7e-tips-source.tar.gz")}`,"HEAD"],{cwd:root});
execFileSync("zip",["-qr",resolve(output,"phase7e-tips-preview.zip"),"."],{cwd:resolve(output,"preview")});
const commit = git(["rev-parse","HEAD"]);
await writeFile(resolve(output,"release.json"),JSON.stringify({commit,base:"ff05b36b40196e369ad3f4324cf7eea2dee9af8f",
  branch:git(["branch","--show-current"]),status:"PARTIAL_NO_GO",backend:{passed:351,permissionSubtests:126,warnings:6,failed:0,skipped:0},
  frontendCommands:24,responsiveActionChecks:12,screenshots:12,migrations:["p7h_tips_accounting","p7i_pharmacy_return_holds"],
  restoredBackupDate:"2026-10-16",historicalTablesPreserved:34,historicalRowsPreserved:809,migrationStages:11,
  deployed:false,productionModified:false,apkBuilt:false,androidSourceChanged:false,physicalDevicesVerified:false},null,2));
async function list(folder,prefix="") {
  const result=[];
  for (const entry of await readdir(folder,{withFileTypes:true})) {
    const relative=prefix+entry.name;
    if (entry.isDirectory()) result.push(...await list(resolve(folder,entry.name),relative+"/")); else result.push(relative);
  }
  return result;
}
const files=(await list(output)).sort(); const sums=[];
for (const file of files) sums.push(`${createHash("sha256").update(await readFile(resolve(output,file))).digest("hex")}  ${file}`);
await writeFile(resolve(output,"SHA256SUMS"),sums.join("\n")+"\n");
console.log(JSON.stringify({output,commit,files:files.length,status:"PARTIAL_NO_GO"},null,2));
