import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
const root = resolve(import.meta.dirname, "..");
const output = resolve(root, ".recovery-tests-build");
mkdirSync(output, { recursive: true });
const compiled = spawnSync(resolve(root, "node_modules/.bin/tsc"), [
  "--ignoreConfig", "--target", "ES2023", "--module", "NodeNext", "--moduleResolution", "NodeNext",
  "--lib", "ES2023,DOM", "--types", "node,vite/client", "--skipLibCheck", "--allowImportingTsExtensions",
  "--rewriteRelativeImportExtensions", "--outDir", output, resolve(root, "tests/authLifecycle.test.ts"),
], { cwd: root, stdio: "inherit" });
if (compiled.status !== 0) process.exit(compiled.status || 1);
const result = spawnSync(process.execPath, [resolve(output, "tests/authLifecycle.test.js")], { cwd: root, stdio: "inherit" });
process.exitCode = result.status ?? 1;
