import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
const root = resolve(import.meta.dirname, "..");
const output = mkdtempSync(resolve(tmpdir(), "apex-split-receipts-"));
writeFileSync(resolve(output, "package.json"), JSON.stringify({ type: "module" }));
try {
  const compile = spawnSync(resolve(root, "node_modules/.bin/tsc"), ["--ignoreConfig", "--target", "ES2023", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--lib", "ES2023,DOM", "--types", "node", "--skipLibCheck", "--allowImportingTsExtensions", "--rewriteRelativeImportExtensions", "--outDir", output, resolve(root, "src/printing/receiptFormatter.ts"), resolve(root, "tests/splitReceipts.test.ts")], { cwd: root, stdio: "inherit" });
  if (compile.status !== 0) throw Error("Split receipt test compilation failed");
  const run = spawnSync(process.execPath, [resolve(output, "tests/splitReceipts.test.js")], { cwd: root, stdio: "inherit", env: { ...process.env, PHASE11_SPLIT_RECEIPT_FIXTURES: process.env.PHASE11_SPLIT_RECEIPT_FIXTURES || resolve(root, "../artifacts/phase11-split-receipts-20261121/fixtures.json") } });
  process.exitCode = run.status ?? 1;
} finally { rmSync(output, { recursive: true, force: true }); }
