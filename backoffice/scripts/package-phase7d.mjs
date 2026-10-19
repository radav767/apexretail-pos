// Local review packaging only: no publication, production connection or APK build.
import assert from "node:assert/strict";
import { cp, copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve, relative } from "node:path";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";

const root = resolve(import.meta.dirname, "../..");
const evidence = resolve(root, "phase7d-evidence");
const output = resolve(process.env.PHASE7D_RELEASE_OUTPUT || "/root/apexretail-pos/artifacts/phase7d-20261019");
assert.equal(execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" }).trim(), "", "Commit the verified development source before packaging");
const commit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
const backend = await readFile(resolve(evidence, "backend-regression.log"), "utf8");
assert.match(backend, /320 passed/); assert.doesNotMatch(backend, /\bFAILED\b/);
const frontend = JSON.parse(await readFile(resolve(evidence, "frontend/frontend-test-results.json"), "utf8"));
assert.equal(frontend.length, 23); assert.ok(frontend.every(r => r.status === "PASS" && r.exitCode === 0));
const visual = JSON.parse(await readFile(resolve(evidence, "preview/responsive-checks.json"), "utf8"));
assert.equal(visual.checks.length, 40); assert.equal(visual.screenshots, 25);
const migration = JSON.parse(await readFile("/tmp/phase7d-migration-rehearsal.json", "utf8"));
assert.ok(Object.values(migration.stages).every(s => s.historical_content_unchanged));
const guard = JSON.parse(await readFile("/tmp/phase7d-downgrade-guard.json", "utf8"));
assert.equal(guard.downgrade_refused, true); assert.equal(guard.all_content_unchanged, true);
assert.equal(migration.production_accessed, false); assert.equal(guard.production_accessed, false);
await mkdir(output); // Do not overwrite an earlier review package.
await cp(resolve(evidence, "preview"), output, { recursive: true });
await cp(resolve(evidence, "frontend"), resolve(output, "frontend-verification"), { recursive: true });
for (const file of ["backend-regression.log", "operations-tests.log", "visual-checks.log", "test-database-setup.log", "migration-rehearsal.log"]) await copyFile(resolve(evidence, file), resolve(output, file));
for (const name of ["migration-rehearsal", "downgrade-guard"]) await copyFile(`/tmp/phase7d-${name}.json`, resolve(output, `${name}.json`));
await copyFile(resolve(root, "docs/PHASE7D-IMPLEMENTATION-REPORT.md"), resolve(output, "PHASE7D-REPORT.md"));
for (const project of ["pos-web", "backoffice"]) await cp(resolve(root, project, "dist"), resolve(output, "builds", project), { recursive: true });
const files = execFileSync("git", ["diff", "--name-only", "f880817b3af8eeeff890a54c27c66d1affc55552", commit], { cwd: root, encoding: "utf8" });
await writeFile(resolve(output, "changed-files.txt"), files);
execFileSync("git", ["archive", "--format=tar.gz", `--output=${resolve(output, "phase7d-source.tar.gz")}`, commit], { cwd: root });
const previews = (await readdir(output)).filter(name => name.endsWith(".png") || name === "index.html");
execFileSync("zip", ["-q", resolve(output, "phase7d-screenshots.zip"), ...previews], { cwd: output });
await writeFile(resolve(output, "release.json"), JSON.stringify({ commit, branch: "phase7d/multi-business-restaurant", parent: "f880817b3af8eeeff890a54c27c66d1affc55552", migration: "p7e_business_orders_batches", tests: { backend: 320, subtests: 122, frontendCommands: 23, responsive: 40, screenshots: 25 }, productionModified: false, deployed: false, apkBuilt: false, physicalDevicesTested: false, status: "development review candidate; operational limits require owner acceptance" }, null, 2));
const sums = [];
async function walk(path) {
  for (const entry of (await readdir(path, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
    const file = resolve(path, entry.name);
    if (entry.isDirectory()) await walk(file);
    else sums.push(`${createHash("sha256").update(await readFile(file)).digest("hex")}  ${relative(output, file)}`);
  }
}
await walk(output); await writeFile(resolve(output, "SHA256SUMS"), sums.join("\n") + "\n");
console.log(JSON.stringify({ output, commit, files: sums.length, productionDeployment: false, apkBuilt: false }, null, 2));
