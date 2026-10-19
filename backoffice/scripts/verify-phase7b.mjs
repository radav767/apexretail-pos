import { readFile, mkdir, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const output = resolve(process.env.PHASE7B_TEST_OUTPUT || "../../artifacts/phase7b-20261019");
await mkdir(output, { recursive: true });
const results = [];
for (const project of ["pos-web", "backoffice"]) {
  const path = resolve(root, project);
  const packageFile = JSON.parse(await readFile(resolve(path, "package.json"), "utf8"));
  const scripts = [...Object.keys(packageFile.scripts).filter(name => name.startsWith("test:")), "lint", "build"];
  for (const script of scripts) {
    const result = spawnSync("npm", ["run", script], { cwd: path, env: process.env, encoding: "utf8", maxBuffer: 20 * 1024 * 1024 });
    const log = `${result.stdout || ""}\n${result.stderr || ""}`;
    await writeFile(resolve(output, `${project}-${script.replaceAll(":", "-")}.log`), log);
    results.push({ project, script, exitCode: result.status, status: result.status === 0 ? "PASS" : "FAIL" });
    console.log(`${project} ${script}: ${result.status === 0 ? "PASS" : "FAIL"}`);
    if (result.status !== 0) console.log(log.slice(-6000));
  }
}
await writeFile(resolve(output, "frontend-test-results.json"), JSON.stringify(results, null, 2));
if (results.some(result => result.status !== "PASS")) process.exitCode = 1;
