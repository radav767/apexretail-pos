import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const projectDirectory = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
);
const publicKeyPath = resolve(
  projectDirectory,
  "../backend/secrets/entitlement_public.pem",
);

if (!existsSync(publicKeyPath)) {
  throw new Error(
    "POS production build cannot continue: entitlement_public.pem is missing.",
  );
}

const publicKey = readFileSync(publicKeyPath, "utf8").trim();
if (
  !publicKey.includes("-----BEGIN PUBLIC KEY-----") ||
  publicKey.includes("PRIVATE KEY")
) {
  throw new Error(
    "POS production build cannot continue: entitlement_public.pem is not a public PEM key.",
  );
}

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: projectDirectory,
    env: {
      ...process.env,
      VITE_ENTITLEMENT_PUBLIC_KEY: publicKey,
    },
    stdio: "inherit",
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

run(resolve(projectDirectory, "node_modules/.bin/tsc"), ["-b"]);
run(resolve(projectDirectory, "node_modules/.bin/vite"), ["build"]);
