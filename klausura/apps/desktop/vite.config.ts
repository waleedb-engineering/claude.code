import { defineConfig, type Plugin, type ViteDevServer } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * Ein fehlender wasm-Pfad muss LAUT scheitern. Ohne dieses Plugin liefert der
 * SPA-Fallback index.html mit Status 200, und der Fehler taucht erst tief in
 * der WebAssembly-Instanziierung als "expected magic word" auf — weit weg von
 * seiner Ursache.
 */
function failLoudlyOnMissingWasm(): Plugin {
  return {
    name: 'klausura-wasm-404',
    configureServer(server: ViteDevServer) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? '';
        if (url.startsWith('/sql-wasm/') && !url.endsWith('.wasm')) {
          res.statusCode = 404;
          res.end(`Unbekannter wasm-Pfad: ${url}`);
          return;
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), failLoudlyOnMissingWasm()],
  // sql.js ist ein CommonJS-Bündel mit eigenem wasm-Loader.
  optimizeDeps: { include: ['sql.js'] },
  server: { port: 5183, strictPort: true },
  build: { target: 'es2022' },
});
