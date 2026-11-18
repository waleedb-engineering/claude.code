"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n";
import { errorMessage, studio, type DraftState } from "@/lib/studio";
import { btnCls, inputCls, labelCls, primaryCls } from "./ui";

const DIRECT = ["tiktok", "instagram_reels", "x"];
const PRIVACY: Record<string, [string, string]> = {
  PUBLIC_TO_EVERYONE: ["Öffentlich", "Public"],
  MUTUAL_FOLLOW_FRIENDS: ["Freunde", "Friends"],
  FOLLOWER_OF_CREATOR: ["Follower", "Followers"],
  SELF_ONLY: ["Nur ich (privat)", "Only me (private)"],
};

/** Direkt veröffentlichen oder planen — immer mit ausdrücklicher Bestätigung. */
export default function PublishControls({ d, onChanged, onError }: { d: DraftState; onChanged: () => void; onError: (m: string) => void }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [privacyOptions, setPrivacyOptions] = useState<string[] | null>(null);
  const [audited, setAudited] = useState(true);
  const [opts, setOpts] = useState({ privacy_level: "", disable_comment: false, disable_duet: false, disable_stitch: false, share_to_feed: true });
  const [costOk, setCostOk] = useState(false);
  const [when, setWhen] = useState("");
  const [approve, setApprove] = useState(false);
  const [busy, setBusy] = useState(false);
  const lang = t("tl.target") === "Zielsprache" ? 0 : 1;

  if (!DIRECT.includes(d.platform)) return null;
  if (d.state === "scheduled" && d.auto_publish) {
    return (
      <button
        type="button"
        className={btnCls}
        onClick={async () => {
          try {
            await studio.unschedule(d.job_id, d.publishing_id);
            onChanged();
          } catch (e) {
            onError(errorMessage(e));
          }
        }}
      >
        {t("pub.unschedule")}
      </button>
    );
  }
  if (!["ready", "failed", "scheduled", "due"].includes(d.state)) return null;

  async function openPanel() {
    setOpen(true);
    if (d.platform === "tiktok") {
      try {
        const info = await studio.tiktokCreatorInfo();
        setPrivacyOptions(info.privacy_level_options);
        setAudited(info.audited_app);
        setOpts((o) => ({ ...o, privacy_level: info.audited_app ? "" : "SELF_ONLY" }));
      } catch (e) {
        onError(errorMessage(e));
        setOpen(false);
      }
    }
  }

  const options =
    d.platform === "tiktok"
      ? { privacy_level: opts.privacy_level, disable_comment: opts.disable_comment, disable_duet: opts.disable_duet, disable_stitch: opts.disable_stitch }
      : d.platform === "instagram_reels"
        ? { share_to_feed: opts.share_to_feed }
        : {};
  const needsCost = d.platform === "x";
  const valid = (d.platform !== "tiktok" || !!opts.privacy_level) && (!needsCost || costOk);

  async function run(kind: "now" | "schedule") {
    setBusy(true);
    try {
      if (kind === "now") {
        if (!window.confirm(t("pub.confirmNow"))) return;
        await studio.directPublish(d.job_id, d.publishing_id, options, costOk);
      } else {
        await studio.schedulePublish(d.job_id, d.publishing_id, new Date(when).toISOString(), options, costOk);
      }
      setOpen(false);
      onChanged();
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className={primaryCls} onClick={() => void openPanel()}>
        {t("pub.open")}
      </button>
    );
  }
  return (
    <div className="w-full space-y-2 rounded-xl border border-neutral-700 p-3 text-sm" role="group" aria-label={t("pub.open")}>
      {d.error && <p className="text-xs text-rose-300">{d.error}</p>}
      {d.platform === "tiktok" && (
        <>
          <label htmlFor={`pv-${d.publishing_id}`} className={labelCls}>
            {t("pub.privacy")}
          </label>
          <select
            id={`pv-${d.publishing_id}`}
            className={inputCls}
            value={opts.privacy_level}
            onChange={(e) => setOpts({ ...opts, privacy_level: e.target.value })}
          >
            <option value="">{t("pub.choose")}</option>
            {(privacyOptions ?? []).map((p) => (
              <option key={p} value={p} disabled={!audited && p !== "SELF_ONLY"}>
                {PRIVACY[p]?.[lang] ?? p}
              </option>
            ))}
          </select>
          {!audited && <p className="text-xs text-amber-300">{t("pub.tiktokAudit")}</p>}
          {(["disable_comment", "disable_duet", "disable_stitch"] as const).map((k) => (
            <label key={k} className="mr-3 inline-flex items-center gap-1 text-xs text-neutral-300">
              <input type="checkbox" checked={opts[k]} onChange={(e) => setOpts({ ...opts, [k]: e.target.checked })} />
              {t(`pub.${k}` as Parameters<typeof t>[0])}
            </label>
          ))}
        </>
      )}
      {d.platform === "instagram_reels" && (
        <label className="flex items-center gap-2 text-xs text-neutral-300">
          <input type="checkbox" checked={opts.share_to_feed} onChange={(e) => setOpts({ ...opts, share_to_feed: e.target.checked })} />
          {t("pub.shareToFeed")}
        </label>
      )}
      {needsCost && (
        <label className="flex items-start gap-2 text-xs text-amber-200">
          <input type="checkbox" className="mt-0.5" checked={costOk} onChange={(e) => setCostOk(e.target.checked)} />
          {t("pub.xCost")}
        </label>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={primaryCls} disabled={!valid || busy} onClick={() => void run("now")}>
          {t("pub.now")}
        </button>
        <button type="button" className={btnCls} onClick={() => setOpen(false)}>
          {t("common.cancel")}
        </button>
      </div>
      <div className="flex flex-wrap items-end gap-2 border-t border-neutral-800 pt-2">
        <div>
          <label htmlFor={`when-${d.publishing_id}`} className={labelCls}>
            {t("pub.when")}
          </label>
          <input id={`when-${d.publishing_id}`} type="datetime-local" className={inputCls} value={when} onChange={(e) => setWhen(e.target.value)} />
        </div>
        <label className="flex max-w-xs items-start gap-2 text-xs text-neutral-300">
          <input type="checkbox" className="mt-0.5" checked={approve} onChange={(e) => setApprove(e.target.checked)} />
          {t("pub.approve")}
        </label>
        <button type="button" className={btnCls} disabled={!valid || !when || !approve || busy} onClick={() => void run("schedule")}>
          {t("pub.schedule")}
        </button>
      </div>
      <p className="text-[11px] text-neutral-500">{t("pub.untested")}</p>
    </div>
  );
}
