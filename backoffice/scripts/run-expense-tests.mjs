import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const projectRoot = resolve(import.meta.dirname, "..");
const outputDir = mkdtempSync(resolve(tmpdir(), "apex-expense-tests-"));
try {
  const compile = spawnSync(resolve(projectRoot, "node_modules/.bin/tsc"), [
    "tests/expenses.test.ts", "src/pages/expenseLogic.ts", "--ignoreConfig", "--outDir", outputDir,
    "--module", "commonjs", "--moduleResolution", "node", "--target", "ES2022", "--esModuleInterop",
    "--skipLibCheck", "--types", "node", "--ignoreDeprecations", "6.0",
  ], { cwd: projectRoot, stdio: "inherit" });
  if (compile.status !== 0) throw new Error("Expense test compilation failed");
  const nodePath = [resolve(projectRoot, "node_modules"), process.env.NODE_PATH].filter(Boolean).join(delimiter);
  const run = spawnSync(process.execPath, [resolve(outputDir, "tests/expenses.test.js")], { cwd: projectRoot, env: { ...process.env, NODE_PATH: nodePath }, stdio: "inherit" });
  process.exitCode = run.status ?? 1;
} finally { rmSync(outputDir, { recursive: true, force: true }); }
