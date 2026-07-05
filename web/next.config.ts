import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next 16 blockt Dev-Ressourcen (HMR, RSC-Hydration) standardmäßig für
  // Cross-Origin-Hosts. Lokale Entwicklung läuft sowohl über "localhost" als
  // auch "127.0.0.1" — beide müssen erlaubt sein, sonst hydriert die App nicht.
  allowedDevOrigins: ["localhost", "127.0.0.1"],
  // Das Next-eigene Dev-Tools-Overlay ausblenden — für Beta-Tester, die über
  // start_local.sh im Dev-Modus (Hot Reload) laufen, ist das reine
  // Framework-Debug-UI ohne Nutzen. Compile-/Runtime-Fehler werden weiterhin
  // angezeigt (nur das kosmetische Badge verschwindet).
  devIndicators: false,
};

export default nextConfig;
