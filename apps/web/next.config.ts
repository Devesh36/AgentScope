import type { NextConfig } from "next";
const config: NextConfig = {
  devIndicators: false,
  allowedDevOrigins: ["127.0.0.1"],
  poweredByHeader: false,
  output: "standalone",
};
export default config;
