/**
 * Kopiert die wasm-Dateien von sql.js nach public/sql-wasm/.
 *
 * Warum ein Skript und keine eingecheckte Kopie: sql.js fordert im Browser
 * `sql-wasm-browser.wasm` an, in Node `sql-wasm.wasm`. Eine von Hand kopierte
 * Datei geht beim naechsten Versionswechsel still kaputt — und Vites
 * SPA-Fallback liefert dann index.html mit Status 200 statt eines 404.
 * Genau das hat hier eine Stunde gekostet.
 */
import { createRequire } from 'node:module';
import { copyFile, mkdir, readdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const distDir = dirname(require.resolve('sql.js/dist/sql-wasm.js'));
const target = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'sql-wasm');

await mkdir(target, { recursive: true });
const files = (await readdir(distDir)).filter((f) => f.endsWith('.wasm') && !f.includes('debug'));
if (files.length === 0) throw new Error(`Keine wasm-Datei in ${distDir} gefunden.`);
for (const f of files) await copyFile(join(distDir, f), join(target, f));
console.log(`sql.js wasm kopiert: ${files.join(', ')}`);
