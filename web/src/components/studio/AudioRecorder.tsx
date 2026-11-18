"use client";

import { useEffect, useRef, useState } from "react";
import { useT } from "@/lib/i18n";
import { btnCls } from "./ui";

/** Sprachprobe direkt im Browser aufnehmen (MediaRecorder). Liefert eine Datei. */
export default function AudioRecorder({ onRecorded, maxSeconds = 120 }: { onRecorded: (f: File) => void; maxSeconds?: number }) {
  const t = useT();
  const [state, setState] = useState<"idle" | "recording" | "unsupported">("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current);
      rec.current?.stream.getTracks().forEach((tr) => tr.stop());
    },
    [],
  );

  async function start() {
    setError(null);
    if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setState("unsupported");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const chunks: Blob[] = [];
      recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((tr) => tr.stop());
        if (timer.current) clearInterval(timer.current);
        const type = recorder.mimeType || "audio/webm";
        const ext = type.includes("mp4") ? "mp4" : "webm";
        const stamp = new Date().toISOString().slice(11, 19).replace(/:/g, "");
        onRecorded(new File(chunks, `aufnahme_${stamp}.${ext}`, { type }));
        setState("idle");
      };
      rec.current = recorder;
      recorder.start();
      setSeconds(0);
      setState("recording");
      timer.current = setInterval(() => {
        setSeconds((s) => {
          if (s + 1 >= maxSeconds) recorder.stop();
          return s + 1;
        });
      }, 1000);
    } catch {
      setError(t("rec.denied"));
    }
  }

  if (state === "unsupported") return <p className="text-xs text-amber-300">{t("rec.unsupported")}</p>;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {state === "recording" ? (
        <button type="button" className={btnCls} onClick={() => rec.current?.stop()}>
          ■ {t("rec.stop")} ({seconds}s)
        </button>
      ) : (
        <button type="button" className={btnCls} onClick={() => void start()}>
          ● {t("rec.start")}
        </button>
      )}
      <span className="text-[11px] text-neutral-400">{t("rec.hint")}</span>
      {error && (
        <p role="alert" className="w-full text-xs text-rose-300">
          {error}
        </p>
      )}
    </div>
  );
}
