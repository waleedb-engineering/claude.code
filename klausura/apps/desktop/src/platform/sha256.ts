/** Verhindert Doppelimporte derselben Datei (docs/klausura/03, Stufe 1). */
export async function sha256Hex(data: Uint8Array): Promise<string> {
  const buffer = new Uint8Array(data.length);
  buffer.set(data);
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
