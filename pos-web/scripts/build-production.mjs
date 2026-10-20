import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const projectDirectory = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
);
const publicKeyringPath = process.env.ENTITLEMENT_PUBLIC_KEYRING_FILE
  ? resolve(process.env.ENTITLEMENT_PUBLIC_KEYRING_FILE)
  : resolve(projectDirectory, "../backend/secrets/entitlement_public_keyring.json");

if (!existsSync(publicKeyringPath)) {
  throw new Error(
    "POS production build cannot continue: entitlement public keyring is missing.",
  );
}

const publicKeyring = readFileSync(publicKeyringPath, "utf8").trim();
let parsedKeyring;
try {
  parsedKeyring = JSON.parse(publicKeyring);
} catch {
  throw new Error("POS production build cannot continue: public keyring is invalid JSON.");
}
if (publicKeyring.includes("PRIVATE KEY") || parsedKeyring?.version !== 1 ||
    !Number.isInteger(parsedKeyring.max_token_lifetime_seconds) || parsedKeyring.max_token_lifetime_seconds <= 0 ||
    !Number.isInteger(parsedKeyring.max_offline_grace_seconds) || parsedKeyring.max_offline_grace_seconds <= 0 ||
    !Array.isArray(parsedKeyring?.keys) || parsedKeyring.keys.length === 0 ||
    parsedKeyring.keys.some((key) =>
      !key?.kid || !String(key.public_key_pem || "").includes("-----BEGIN PUBLIC KEY-----")
    )) {
  throw new Error(
    "POS production build cannot continue: entitlement keyring requires positive integer lifetime limits and public keys only.",
  );
}

function scanBuildInputs(directory) {
  if (!existsSync(directory)) return;
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) {
      scanBuildInputs(path);
      continue;
    }
    if (/^\.env(?:\.|$)/.test(entry.name) || /private.*key|\.pem$/i.test(entry.name)) {
      throw new Error(`POS build input contains a forbidden secret/key file: ${entry.name}`);
    }
    const source = readFileSync(path, "utf8");
    if (source.includes("-----BEGIN PRIVATE KEY-----") ||
        source.includes("-----BEGIN RSA PRIVATE KEY-----")) {
      throw new Error(`POS build input contains private key material: ${entry.name}`);
    }
  }
}

scanBuildInputs(resolve(projectDirectory, "src"));
scanBuildInputs(resolve(projectDirectory, "public"));
for (const entry of readdirSync(projectDirectory, { withFileTypes: true })) {
  if (entry.isFile() && /^\.env(?:\.|$)/.test(entry.name)) {
    throw new Error(
      `POS production build refuses environment files in the project root: ${entry.name}`,
    );
  }
}

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: projectDirectory,
    env: {
      ...process.env,
      VITE_ENTITLEMENT_PUBLIC_KEYRING: publicKeyring,
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
