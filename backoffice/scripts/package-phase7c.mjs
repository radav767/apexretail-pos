// Preserve review artifacts locally. This script never publishes or deploys.
import assert from "node:assert/strict";
import { cp, copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve, relative } from "node:path";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";

const root = resolve(import.meta.dirname, "../..");
const evidence = resolve(root, "phase7c-evidence");
const output = resolve(process.env.PHASE7C_RELEASE_OUTPUT || "/root/apexretail-pos/artifacts/phase7c-20261019");
assert.equal(execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" }).trim(), "", "Commit and verify the source before packaging");
const commit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
const backend = await readFile(resolve(evidence, "backend-regression.log"), "utf8");
const integration = await readFile(resolve(evidence, "printer-integration.log"), "utf8");
assert.match(backend, /289 passed/); assert.doesNotMatch(backend, /\bFAILED\b/);
assert.match(integration, /21 passed/); assert.doesNotMatch(integration, /\bFAILED\b/);
const frontend = JSON.parse(await readFile(resolve(evidence, "frontend-evidence/frontend-test-results.json"), "utf8"));
assert.equal(frontend.length, 23); assert.ok(frontend.every(r => r.status === "PASS"));
const visual = JSON.parse(await readFile(resolve(evidence, "preview-evidence/responsive-checks.json"), "utf8"));
assert.equal(visual.checks.length, 32); assert.equal(visual.screenshots, 20);
const migration = JSON.parse(await readFile("/tmp/phase7c-migration-rehearsal.json", "utf8"));
assert.ok(Object.values(migration.stages).every(s => s.historical_content_unchanged));
assert.equal(migration.production_accessed, false);
assert.match(await readFile(resolve(evidence, "android-checks.log"), "utf8"), /BUILD SUCCESSFUL/);
await mkdir(output); // Refuse overwriting an existing review release.
await cp(resolve(evidence, "preview-evidence"), output, { recursive: true });
await cp(resolve(evidence, "frontend-evidence"), resolve(output, "frontend-verification"), { recursive: true });
for (const name of ["backend-regression.log", "printer-integration.log", "android-checks.log", "visual-checks.log"]) await copyFile(resolve(evidence, name), resolve(output, name));
await copyFile("/tmp/phase7c-migration-rehearsal.json", resolve(output, "migration-rehearsal.json"));
await copyFile(resolve(root, "docs/PHASE7C-PRINTING-REPORT.md"), resolve(output, "PHASE7C-REPORT.md"));
await cp(resolve(root, "pos-web/android/app/build/reports"), resolve(output, "android-reports"), { recursive: true });
await cp(resolve(root, "pos-web/android/app/build/test-results/testReleaseUnitTest"), resolve(output, "android-unit-results"), { recursive: true });
for (const project of ["pos-web", "backoffice"]) await cp(resolve(root, project, "dist"), resolve(output, "builds", project), { recursive: true });
const files = execFileSync("git", ["diff", "--name-only", "99f138694e0bd6fbbc8765c5142d48d9138ca634", commit], { cwd: root, encoding: "utf8" });
await writeFile(resolve(output, "changed-files.txt"), files);
execFileSync("git", ["archive", "--format=tar.gz", `--output=${resolve(output, "phase7c-source.tar.gz")}`, commit], { cwd: root });
await writeFile(resolve(output, "release.json"), JSON.stringify({ commit, branch: "phase7c/printers-kitchen-printing", parent: "99f138694e0bd6fbbc8765c5142d48d9138ca634", migration: "p7d_printers_kitchen_jobs", tests: { backend: 289, subtests: 110, printerIntegration: 21, frontendCommands: 23, responsive: 32, screenshots: 20 }, productionModified: false, deployed: false, apkBuilt: false, physicalPrintersTested: false }, null, 2));
const sums = [];
async function walk(path) {
  for (const entry of (await readdir(path, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
    const file = resolve(path, entry.name);
    if (entry.isDirectory()) await walk(file);
    else sums.push(`${createHash("sha256").update(await readFile(file)).digest("hex")}  ${relative(output, file)}`);
  }
}
await walk(output); await writeFile(resolve(output, "SHA256SUMS"), sums.join("\n") + "\n");
console.log(JSON.stringify({ output, commit, files: sums.length, deployment: "not performed" }, null, 2));
