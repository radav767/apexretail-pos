import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "cloud.apexpos.pos",
  appName: "ApexRetail POS",
  webDir: "dist",

  server: {
    androidScheme: "https",
  },

  android: {
    allowMixedContent: false,
  },
};

export default config;
