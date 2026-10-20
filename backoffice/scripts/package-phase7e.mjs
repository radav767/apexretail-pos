// Development review artifacts only. No network, deployment, database or APK.
import assert from "node:assert/strict";
import { cp, copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
const root = resolve(import.meta.dirname, "../..");
const output = "/root/apexretail-pos/artifacts/phase7e-20261020";
const git = args => execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim();
assert.equal(git(["status", "--porcelain"]), "", "Commit reviewed sources before packaging");
const commit = git(["rev-parse", "HEAD"]);
const backend = await readFile("/tmp/phase7e-backend-final.log", "utf8");
assert.match(backend, /332 passed, 6 warnings, 122 subtests passed/);
const frontend = JSON.parse(await readFile(resolve(root, "phase7e-evidence/frontend-final/frontend-test-results.json"), "utf8"));
assert.equal(frontend.length, 24); assert.ok(frontend.every(row => row.status === "PASS"));
const migration = JSON.parse(await readFile("/tmp/apexretail_phase7e_production_clone_20261020-rehearsal.json", "utf8"));
assert.equal(migration.stages.length, 9); assert.ok(migration.stages.every(stage => stage.historical_content_unchanged));
const guards = JSON.parse(await readFile("/tmp/phase7e-downgrade-guards.json", "utf8"));
assert.equal(guards.all_tables_unchanged, true);
await mkdir(output, { mode: 0o700 }); // Do not overwrite an existing review bundle.
await copyFile(resolve(root, "PHASE7E-IMPLEMENTATION.md"), resolve(output, "PHASE7E-REPORT.md"));
await copyFile("/tmp/phase7e-backend-final.log", resolve(output, "backend-regression.log"));
for (const [source, destination] of [
  ["/tmp/apexretail_phase7e_production_clone_20261020-rehearsal.json", "restored-backup-rehearsal.json"],
  ["/tmp/apexretail_phase7e_synthetic_rehearsal-rehearsal.json", "synthetic-rehearsal.json"],
  ["/tmp/phase7e-downgrade-guards.json", "downgrade-guards.json"],
  ["/tmp/phase7a1-entitlement-public-keyring.json", "entitlement-public-keyring.json"],
]) await copyFile(source, resolve(output, destination));
await cp(resolve(root, "phase7e-evidence/frontend-final"), resolve(output, "frontend-verification"), { recursive: true });
await cp(resolve(root, "phase7e-evidence/screenshots"), resolve(output, "screenshots"), { recursive: true });
for (const project of ["pos-web", "backoffice"]) await cp(resolve(root, project, "dist"), resolve(output, "builds", project), { recursive: true });
await writeFile(resolve(output, "changed-files.txt"), git(["diff", "--name-only", "4f2109dffff642422e046dde9147f7d0c89d759d", "HEAD"]) + "\n");
execFileSync("git", ["archive", "--format=tar.gz", `--output=${resolve(output, "phase7e-source.tar.gz")}`, "HEAD"], { cwd: root });
execFileSync("zip", ["-qr", resolve(output, "phase7e-screenshots.zip"), "."], { cwd: resolve(output, "screenshots") });
await writeFile(resolve(output, "release.json"), JSON.stringify({ commit, branch: git(["branch", "--show-current"]), status: "PARTIAL_NO_GO",
  backend: { passed: 332, permissionSubtests: 122, warnings: 6, failures: 0, skips: 0 }, frontendCommands: 24,
  deployed: false, productionModified: false, apkBuilt: false, screenshotsSynthetic: true,
  productionBackupDate: "2026-10-16", migrations: ["p7f_offline_order_receipts", "p7g_batch_stock_operations"] }, null, 2));
async function files(folder, prefix = "") {
  const output = [];
  for (const entry of await readdir(folder, { withFileTypes: true })) {
    const relative = prefix + entry.name;
    if (entry.isDirectory()) output.push(...await files(resolve(folder, entry.name), relative + "/"));
    else output.push(relative);
  }
  return output;
}
const names = (await files(output)).sort();
const pngs = names.filter(name => name.endsWith(".png")); assert.equal(pngs.length, 86);
const checksums = [];
for (const name of names) checksums.push(`${createHash("sha256").update(await readFile(resolve(output, name))).digest("hex")}  ${name}`);
await writeFile(resolve(output, "SHA256SUMS"), checksums.join("\n") + "\n");
console.log(JSON.stringify({ output, commit, artifacts: names.length, screenshots: pngs.length, status: "PARTIAL_NO_GO" }, null, 2));
