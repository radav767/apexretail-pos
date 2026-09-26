import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const projectDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputDirectory = mkdtempSync(resolve(tmpdir(), "apex-credit-sale-tests-"));
const outputFile = resolve(outputDirectory, "tests/creditSale.test.js");
writeFileSync(resolve(outputDirectory, "package.json"), JSON.stringify({ type: "module" }));

try {
  const compileResult = spawnSync(
    resolve(projectDirectory, "node_modules/.bin/tsc"),
    [
      "--ignoreConfig",
      "--target", "ES2023",
      "--module", "NodeNext",
      "--moduleResolution", "NodeNext",
      "--lib", "ES2023,DOM",
      "--types", "node",
      "--skipLibCheck",
      "--allowImportingTsExtensions",
      "--rewriteRelativeImportExtensions",
      "--outDir", outputDirectory,
      resolve(projectDirectory, "src/creditSale.ts"),
      resolve(projectDirectory, "tests/creditSale.test.ts"),
    ],
    { cwd: projectDirectory, stdio: "inherit" },
  );
  if (compileResult.error) throw compileResult.error;
  if (compileResult.status !== 0) throw new Error("Credit sale test compilation failed.");

  const result = spawnSync(process.execPath, [outputFile], {
    cwd: projectDirectory,
    stdio: "inherit",
  });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally {
  rmSync(outputDirectory, { recursive: true, force: true });
}
