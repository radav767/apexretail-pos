import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { cp, mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import { dirname, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const output = resolve(process.env.PHASE7B_REVIEW_OUTPUT || "/root/apexretail-pos/artifacts/phase7b-20261019");
function git(...args) {
  const result = spawnSync("git", args, { cwd: root, encoding: "utf8" });
  if (result.status !== 0) throw new Error(result.stderr);
  return result.stdout.trim();
}
assert.equal(git("status", "--porcelain"), "", "Commit the reviewed source before packaging");
const commit = git("rev-parse", "HEAD");
const frontend = JSON.parse(await readFile(resolve(output, "frontend-test-results.json"), "utf8"));
assert.equal(frontend.length, 22);
assert.ok(frontend.every(result => result.status === "PASS"));
const backend = await readFile(resolve(output, "backend-regression.log"), "utf8");
assert.ok(/\d+ passed/.test(backend) && !/\d+ failed|FAILED /.test(backend), "Backend regression must pass");
const visual = JSON.parse(await readFile(resolve(output, "responsive-checks.json"), "utf8"));
assert.equal(visual.checks.length, 24);
assert.equal(visual.cashierLogoutIdentity, "PASS");
assert.equal(visual.staleLogoutDoesNotClearNewSession, "PASS");
assert.equal(visual.revokedSessionFailsClosed, "PASS");
const migration = JSON.parse(await readFile(resolve(output, "migration-rehearsal.json"), "utf8"));
for (const check of ["upgrade", "downgrade", "forward_recovery"]) assert.equal(migration[check], "PASS");
await mkdir(resolve(output, "builds-final"), { recursive: true });
for (const [project, name] of [["pos-web", "pos"], ["backoffice", "backoffice"]]) {
  const directory = resolve(root, project, "dist");
  const html = await readFile(resolve(directory, "index.html"), "utf8");
  for (const match of html.matchAll(/(?:src|href)="([^"]+)"/g)) {
    if (match[1].startsWith("http")) continue;
    assert.ok((await stat(resolve(directory, match[1].replace(/^\//, "")))).isFile());
  }
  await cp(directory, resolve(output, "builds-final", name), { recursive: true });
}
await cp(resolve(root, "docs/PHASE7B-EMPLOYEES-REPORT.md"), resolve(output, "PHASE7B-REPORT.md"));
await writeFile(resolve(output, "changed-files.txt"), `${git("show", "--format=", "--name-only", "HEAD")}\n`);
const archive = spawnSync("git", ["archive", "--format=tar.gz", `--output=${resolve(output, "phase7b-source.tar.gz")}`, commit], { cwd: root, encoding: "utf8" });
if (archive.status !== 0) throw new Error(archive.stderr);
await writeFile(resolve(output, "release.json"), JSON.stringify({ commit, branch: git("branch", "--show-current"), migration: "p7c_employee_roles_permissions", backend: backend.trim().split("\n").at(-1), frontendCommandsPassed: 22, responsiveChecksPassed: 24, productionDeployment: false, androidBuild: false, generatedAt: new Date().toISOString() }, null, 2));
async function files(directory) {
  const result = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) {
      if (directory === output && entry.name === "builds") continue;
      result.push(...await files(path));
    } else if (entry.isFile() && entry.name !== "SHA256SUMS") result.push(path);
  }
  return result;
}
const entries = [];
for (const file of (await files(output)).sort()) entries.push(`${createHash("sha256").update(await readFile(file)).digest("hex")}  ${relative(output, file)}`);
await writeFile(resolve(output, "SHA256SUMS"), `${entries.join("\n")}\n`);
console.log(JSON.stringify({ commit, filesHashed: entries.length, output }, null, 2));
