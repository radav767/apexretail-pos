import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const output = mkdtempSync(resolve(tmpdir(), "apex-currency-checkout-"));
writeFileSync(resolve(output, "package.json"), JSON.stringify({ type: "module" }));
try {
  const compile = spawnSync(resolve(root, "node_modules/.bin/tsc"), [
    "--ignoreConfig", "--target", "ES2023", "--module", "NodeNext",
    "--moduleResolution", "NodeNext", "--lib", "ES2023,DOM", "--types", "node",
    "--skipLibCheck", "--allowImportingTsExtensions", "--rewriteRelativeImportExtensions",
    "--outDir", output, resolve(root, "src/decimal.ts"), resolve(root, "src/printing/types.ts"),
    resolve(root, "src/printing/receiptFormatter.ts"), resolve(root, "tests/currencyCheckout.test.ts"),
  ], { cwd: root, stdio: "inherit" });
  if (compile.status !== 0) throw new Error("Currency checkout test compilation failed");
  const run = spawnSync(process.execPath, [resolve(output, "tests/currencyCheckout.test.js")], {
    cwd: root, stdio: "inherit",
  });
  process.exitCode = run.status ?? 1;
} finally {
  rmSync(output, { recursive: true, force: true });
}
