import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const entitlementPublicKey = env.VITE_ENTITLEMENT_PUBLIC_KEY?.trim();

  if (command === "build" && !entitlementPublicKey) {
    throw new Error(
      "POS production build requires VITE_ENTITLEMENT_PUBLIC_KEY.",
    );
  }
  if (
    command === "build" &&
    (!entitlementPublicKey?.includes("-----BEGIN PUBLIC KEY-----") ||
      entitlementPublicKey.includes("PRIVATE KEY"))
  ) {
    throw new Error(
      "VITE_ENTITLEMENT_PUBLIC_KEY must contain an RSA public PEM key.",
    );
  }

  return {
    plugins: [react()],
  };
});
