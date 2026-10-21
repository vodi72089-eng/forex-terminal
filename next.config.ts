import type { NextConfig } from "next";

// Export statique obligatoire : le front est embarque dans le .exe Tauri
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
