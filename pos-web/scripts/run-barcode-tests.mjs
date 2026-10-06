import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const projectDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputDirectory = mkdtempSync(resolve(tmpdir(), "apex-barcode-tests-"));
const outputFile = resolve(outputDirectory, "tests/barcodeScanner.test.js");
writeFileSync(resolve(outputDirectory, "package.json"), JSON.stringify({ type: "module" }));

try {
  const compileResult = spawnSync(
    resolve(projectDirectory, "node_modules/.bin/tsc"),
    [
      "--ignoreConfig", "--target", "ES2023", "--module", "NodeNext",
      "--moduleResolution", "NodeNext", "--lib", "ES2023,DOM",
      "--types", "node", "--skipLibCheck", "--allowImportingTsExtensions",
      "--rewriteRelativeImportExtensions", "--outDir", outputDirectory,
      resolve(projectDirectory, "src/barcode/barcode.ts"),
      resolve(projectDirectory, "src/barcode/keyboardWedge.ts"),
      resolve(projectDirectory, "src/barcode/cameraLifecycle.ts"),
      resolve(projectDirectory, "tests/barcodeScanner.test.ts"),
    ],
    { cwd: projectDirectory, stdio: "inherit" },
  );
  if (compileResult.error) throw compileResult.error;
  if (compileResult.status !== 0) throw new Error("Barcode test compilation failed.");
  const result = spawnSync(process.execPath, [outputFile], {
    cwd: projectDirectory,
    stdio: "inherit",
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exitCode = result.status ?? 1;
  const uiResult = spawnSync(process.execPath, ["--test", "tests/barcodeUi.test.mjs"], {
    cwd: projectDirectory,
    stdio: "inherit",
  });
  if (uiResult.error) throw uiResult.error;
  if (uiResult.status !== 0) process.exitCode = uiResult.status ?? 1;
} finally {
  rmSync(outputDirectory, { recursive: true, force: true });
}
