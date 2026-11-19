import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const projectDirectory = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
);
const outputDirectory = mkdtempSync(
  resolve(tmpdir(), "apex-refund-tests-"),
);
const outputFile = resolve(
  outputDirectory,
  "tests/refundCommand.test.js",
);
writeFileSync(
  resolve(outputDirectory, "package.json"),
  JSON.stringify({ type: "module" }),
);

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
      resolve(projectDirectory, "src/refundCommand.ts"),
      resolve(projectDirectory, "tests/refundCommand.test.ts"),
    ],
    {
      cwd: projectDirectory,
      stdio: "inherit",
    },
  );
  if (compileResult.error) {
    throw compileResult.error;
  }
  if (compileResult.status !== 0) {
    throw new Error("Refund test compilation failed.");
  }
  const result = spawnSync(
    process.execPath,
    [outputFile],
    {
    cwd: projectDirectory,
    stdio: "inherit",
    },
  );
  if (result.error) {
    throw result.error;
  }
  process.exitCode = result.status ?? 1;
} finally {
  rmSync(outputDirectory, { recursive: true, force: true });
}
