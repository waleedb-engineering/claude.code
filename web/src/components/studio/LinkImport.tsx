"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { errorMessage, studio, type LinkImportStatus } from "@/lib/studio";
import { ErrorBox, btnCls, cardCls, inputCls, labelCls, primaryCls } from "./ui";

/** Link einfügen → ClipForge lädt, analysiert und schlägt Highlights vor. */
export default function LinkImport() {
  const router = useRouter();
  const [status, setStatus] = useState<LinkImportStatus | null>(null);
  const [ack, setAck] = useState(false);
  const [url, setUrl] = useState("");
  const [rights, setRights] = useState(false);
  const [maxClips, setMaxClips] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    studio
      .linkImportStatus()
      .then((s) => alive && setStatus(s))
      .catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, []);

  async function toggle(enabled: boolean) {
    setError(null);
    try {
      setStatus(await studio.setLinkImport(enabled, ack));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function start(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await studio.streamFromLink({
        url: url.trim(),
        rights_confirmed: rights,
        analyze: { max_clips: maxClips, transcribe: true },
      });
      router.push(`/studio/streams/${r.stream.id}?task=${r.task.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  if (!status) return error ? <ErrorBox message={error} /> : null;

  return (
    <section className={`${cardCls} space-y-3`} aria-labelledby="link-import-h">
      <h2 id="link-import-h" className="text-sm font-semibold text-neutral-200">
        Aus Link clippen (YouTube / Twitch)
      </h2>
      <ErrorBox message={error} />
      {!status.installed && (
        <p className="text-sm text-amber-200">
          yt-dlp fehlt. Im Ordner <code>api</code> installieren: <code>{status.install_hint}</code>
        </p>
      )}
      {!status.enabled ? (
        <div className="space-y-2">
          <p className="text-sm text-neutral-300">{status.terms}</p>
          <label className="flex items-start gap-2 text-sm text-neutral-200">
            <input type="checkbox" className="mt-1 accent-indigo-400" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            Verstanden — ich nutze den Link-Import nur für eigene Inhalte oder mit Erlaubnis.
          </label>
          <button type="button" className={btnCls} disabled={!ack || !status.installed} onClick={() => toggle(true)}>
            Link-Import einschalten
          </button>
        </div>
      ) : (
        <form onSubmit={start} className="grid gap-3 sm:grid-cols-4">
          <div className="sm:col-span-3">
            <label htmlFor="li-url" className={labelCls}>
              Link zum Video oder zur vergangenen Übertragung
            </label>
            <input
              id="li-url"
              type="url"
              required
              placeholder="https://www.youtube.com/watch?v=…  oder  https://www.twitch.tv/videos/…"
              className={inputCls}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="li-max" className={labelCls}>
              Clip-Vorschläge
            </label>
            <select id="li-max" className={inputCls} value={maxClips} onChange={(e) => setMaxClips(Number(e.target.value))}>
              {[5, 10, 20, 40].map((n) => (
                <option key={n} value={n}>
                  bis {n}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-start gap-2 text-sm text-neutral-200 sm:col-span-4">
            <input type="checkbox" className="mt-1 accent-indigo-400" checked={rights} onChange={(e) => setRights(e.target.checked)} />
            Das ist mein eigener Inhalt, oder ich habe die Erlaubnis der Rechteinhaber, daraus Clips zu machen.
          </label>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-4">
            <button type="submit" className={primaryCls} disabled={!rights || busy || !url.trim()}>
              {busy ? "Wird gestartet …" : "Laden und Highlights finden"}
            </button>
            <span className="text-xs text-neutral-400">
              max. {status.max_hours} h · bis {status.max_height}p · läuft lokal · YouTube-Chat-Replay wird mitgenommen
            </span>
            <button type="button" className="ml-auto text-xs text-neutral-400 underline" onClick={() => toggle(false)}>
              Link-Import ausschalten
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
