import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next 16 blockt Dev-Ressourcen (HMR, RSC-Hydration) standardmäßig für
  // Cross-Origin-Hosts. Lokale Entwicklung läuft sowohl über "localhost" als
  // auch "127.0.0.1" — beide müssen erlaubt sein, sonst hydriert die App nicht.
  allowedDevOrigins: ["localhost", "127.0.0.1"],
};

export default nextConfig;
