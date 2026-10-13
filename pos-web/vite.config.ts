import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const entitlementPublicKeyring =
    env.VITE_ENTITLEMENT_PUBLIC_KEYRING?.trim();
  const secretLikeVariables = Object.keys(env).filter(
    (name) =>
      name !== "VITE_ENTITLEMENT_PUBLIC_KEYRING" &&
      /(PRIVATE|SECRET|PASSWORD|TOKEN|SIGNING_KEY)/i.test(name),
  );

  if (command === "build" && secretLikeVariables.length) {
    throw new Error(
      "POS production build refuses secret-like VITE environment variables.",
    );
  }

  if (command === "build" && !entitlementPublicKeyring) {
    throw new Error(
      "POS production build requires VITE_ENTITLEMENT_PUBLIC_KEYRING.",
    );
  }
  if (command === "build") {
    let parsedKeyring: {
      version?: number;
      keys?: Array<{ kid?: string; public_key_pem?: string }>;
    };
    try {
      parsedKeyring = JSON.parse(entitlementPublicKeyring || "");
    } catch {
      throw new Error(
        "VITE_ENTITLEMENT_PUBLIC_KEYRING must be valid JSON.",
      );
    }
    if (
      parsedKeyring.version !== 1 ||
      !Array.isArray(parsedKeyring.keys) ||
      parsedKeyring.keys.length === 0 ||
      parsedKeyring.keys.some(
        (key) =>
          !key.kid ||
          !key.public_key_pem?.includes("-----BEGIN PUBLIC KEY-----") ||
          key.public_key_pem.includes("PRIVATE KEY"),
      )
    ) {
      throw new Error(
        "VITE_ENTITLEMENT_PUBLIC_KEYRING must contain public RSA keys only.",
      );
    }
  }

  return {
    plugins: [react()],
  };
});
