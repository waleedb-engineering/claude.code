"""Rendert eine Mehrspur-Timeline über ein Grundvideo (oder schwarzen Grund).

Ein einziger FFmpeg-Durchgang: jedes sichtbare Element wird zeitlich an seinen
Platz gesetzt (setpts), transformiert (Zuschnitt, Unschärfe, Skalierung,
Drehung, Deckkraft — Keyframes als Ausdrücke) und per ``overlay`` in
Spurreihenfolge aufgelegt. Tonelemente werden verzögert (adelay), mit
Lautstärke-Keyframes versehen und mit dem Grundton gemischt. Untertitel-
Elemente landen als ASS-Ereignisse obenauf.
"""

from __future__ import annotations

import os

from ..ffmpeg_utils import filter_path, probe
from ..hwaccel import encode_args
from .audio import run_ffmpeg
from .errors import StudioError
from .projects import IMAGE_EXT, resolve_music
from .storage import safe_child
from .timeline import CROP_PROPS, keyframe_expr, static_value, value_at

ALIGN = {"bottom": 2, "middle": 5, "top": 8}


def _media_path(project_dir: str, src: str) -> str:
    if src.startswith(("library:", "project:")):
        return resolve_music(project_dir, src)
    path = safe_child(os.path.join(project_dir, "media"), src)
    if not os.path.isfile(path):
        raise StudioError("media_not_found", f"Timeline-Medium '{src}' fehlt.", 404)
    return path


def _ass_color(hexcolor: str) -> str:
    h = hexcolor.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def caption_ass(items: list[dict], w: int, h: int) -> str:
    base = int(min(w, h) * 0.06)
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, "
             "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
             f"Style: TL,Arial,{base},&H00FFFFFF,&H00000000,&H64000000,1,0,1,{max(2, base // 12)},1,2,"
             f"{int(w * 0.06)},{int(w * 0.06)},{int(h * 0.12)},1", "",
             "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for it in items:
        tags = (f"{{\\an{ALIGN[it.get('position', 'bottom')]}\\c{_ass_color(it.get('color', '#ffffff'))}"
                f"\\fs{int(base * float(it.get('size', 1.0)))}}}")
        lines.append(f"Dialogue: 5,{_ts(it['start'])},{_ts(it['start'] + it['duration'])},TL,,0,0,0,,"
                     f"{tags}{_escape_ass(it['text'])}")
    return "\n".join(lines) + "\n"


def composite(tl: dict, project_dir: str, out_path: str, *, base: str | None, total: float, w: int, h: int,
              fps: int, preset: str = "veryfast", crf: str = "23", audio_bitrate: str = "160k",
              work: str, warnings: list | None = None) -> dict:
    """Legt die Timeline über ``base`` (Video mit Ton) bzw. schwarzen Grund. → Bericht."""
    warnings = warnings if warnings is not None else []
    total = max(0.1, float(total))
    args: list[str] = ["ffmpeg", "-y"]
    if base:
        args += ["-i", base]
        vbase, abase, n = "[0:v]", "[0:a]", 1
        if not probe(base).has_audio:
            args += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
            abase, n = "[1:a]", 2
    else:
        args += ["-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}:d={total:.3f}",
                 "-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        vbase, abase, n = "[0:v]", "[1:a]", 2
    filters = [f"{vbase}fps={fps},format=yuv420p,setsar=1[v0]"]
    audio_labels = ["[abase]"]
    filters.append(f"{abase}aresample=44100,aformat=channel_layouts=stereo[abase]")
    cur, vcount, captions = "[v0]", 0, []
    report = {"tracks": 0, "visual_items": 0, "audio_items": 0, "caption_items": 0, "keyframed_props": 0}

    for track in tl.get("tracks", []):
        if not track["items"]:
            continue
        report["tracks"] += 1
        kind = track["kind"]
        for it in track["items"]:
            s, d = float(it["start"]), float(it["duration"])
            if s >= total:
                warnings.append(f"Element auf „{track['name']}“ beginnt nach dem Videoende — ausgelassen.")
                continue
            d = min(d, total - s)
            report["keyframed_props"] += len(it.get("keyframes") or {})
            if kind == "caption":
                if not track["hidden"] and it.get("text"):
                    captions.append({**it, "duration": d})
                    report["caption_items"] += 1
                continue
            path = _media_path(project_dir, it["src"])
            is_image = os.path.splitext(path)[1].lower() in IMAGE_EXT
            has_audio = False
            if kind in ("video", "overlay") and not is_image:
                try:
                    has_audio = probe(path).has_audio
                except Exception:  # noqa: BLE001
                    has_audio = False
            want_visual = kind in ("video", "overlay") and not track["hidden"]
            want_audio = not track["muted"] and (kind == "audio" or bool(it.get("audio") and has_audio))
            if not want_visual and not want_audio:
                continue
            if is_image:
                args += ["-loop", "1", "-framerate", str(fps), "-t", f"{d:.3f}", "-i", path]
            else:
                args += ["-ss", f"{float(it.get('in', 0)):.3f}", "-t", f"{d:.3f}", "-i", path]
            k = n
            n += 1
            if want_visual:
                filters.append(_visual_chain(it, k, kind, s, d, w, h, fps, f"[ov{vcount}]", work, vcount))
                x = keyframe_expr(it, "x", f"(t-{s:.3f})", 0.5)
                y = keyframe_expr(it, "y", f"(t-{s:.3f})", 0.5)
                nxt = f"[v{vcount + 1}]"
                filters.append(f"{cur}[ov{vcount}]overlay=x='{w}*({x})-w/2':y='{h}*({y})-h/2':eval=frame:"
                               f"enable='between(t,{s:.3f},{s + d:.3f})':eof_action=pass{nxt}")
                cur = nxt
                vcount += 1
                report["visual_items"] += 1
            if want_audio:
                lab = f"[a{k}]"
                vol = keyframe_expr(it, "volume", "t", 1.0)
                chain = (f"[{k}:a]aresample=44100,aformat=channel_layouts=stereo,"
                         f"volume='{vol}':eval=frame")
                if it.get("fade_in"):
                    chain += f",afade=t=in:st=0:d={it['fade_in']:.2f}"
                if it.get("fade_out"):
                    chain += f",afade=t=out:st={max(0.0, d - it['fade_out']):.3f}:d={it['fade_out']:.2f}"
                ms = int(round(s * 1000))
                chain += f",adelay={ms}|{ms}{lab}"
                filters.append(chain)
                audio_labels.append(lab)
                report["audio_items"] += 1
    vout = cur
    if captions:
        ass_path = os.path.join(work, "timeline_captions.ass")
        with open(ass_path, "w", encoding="utf-8") as fh:
            fh.write(caption_ass(captions, w, h))
        filters.append(f"{cur}ass={filter_path(ass_path)}[vcap]")
        vout = "[vcap]"
    if len(audio_labels) > 1:
        filters.append(f"{''.join(audio_labels)}amix=inputs={len(audio_labels)}:duration=first:"
                       f"normalize=0[aout]")
        aout = "[aout]"
    else:
        aout = "[abase]"
    tmp = out_path + ".tl.mp4"
    args += ["-filter_complex", ";".join(filters), "-map", vout, "-map", aout,
             *encode_args(preset, crf), "-pix_fmt", "yuv420p", "-r", str(fps),
             "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "44100", "-t", f"{total:.3f}",
             "-movflags", "+faststart", tmp]
    run_ffmpeg(args, "Timeline zusammensetzen")
    os.replace(tmp, out_path)
    report["duration"] = round(total, 3)
    return report


def _blur_commands(it: dict, kind: str, s: float, d: float, fps: int, path: str, target: str) -> None:
    """Unschärfe-Keyframes als sendcmd-Datei (gblur-Sigma je Bild, aus derselben Kurve)."""
    lines, last = [], None
    n = max(1, int(round(d * fps)))
    for i in range(n + 1):
        u = min(d, i / fps)
        sigma = round(value_at(it, "blur", u, kind) * BLUR_SIGMA, 2)
        if sigma != last:
            lines.append(f"{s + u:.4f} {target} sigma {sigma};")
            last = sigma
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


BLUR_SIGMA = 0.6  # Unschärfe-Wert → gblur-Sigma (statisch: boxblur-Radius)


def _visual_chain(it: dict, k: int, kind: str, s: float, d: float, w: int, h: int, fps: int, label: str,
                  work: str = "", n: int = 0) -> str:
    tv = f"(t-{s:.3f})"
    parts = [f"[{k}:v]setpts=PTS-STARTPTS+{s:.3f}/TB", f"fps={fps}", "format=rgba"]
    crop = it.get("crop")
    kfs_all = it.get("keyframes") or {}
    animated_crop = any(p in kfs_all for p in CROP_PROPS)
    if crop and not animated_crop:
        fw, fh = 1 - crop["left"] - crop["right"], 1 - crop["top"] - crop["bottom"]
        parts.append(f"crop=iw*{fw:.4f}:ih*{fh:.4f}:iw*{crop['left']:.4f}:ih*{crop['top']:.4f}")
    if "blur" in kfs_all and work:
        cmd_path = os.path.join(work, f"blur_{n}.cmd")
        _blur_commands(it, kind, s, d, fps, cmd_path, f"gblur@b{n}")
        sigma0 = round(value_at(it, "blur", 0.0, kind) * BLUR_SIGMA, 2)
        parts.append(f"sendcmd=f={filter_path(cmd_path)}")
        parts.append(f"gblur@b{n}=sigma={sigma0}")
    elif it.get("blur"):
        parts.append(f"boxblur={max(1, int(it['blur']))}:1")
    kfs = kfs_all
    default_scale = 1.0 if kind == "video" else 0.4
    sc = keyframe_expr(it, "scale", tv, default_scale)
    if "scale" in kfs:
        # Größe je Bild aus der Keyframe-Kurve (gerade Pixelzahl)
        parts.append(f"scale=w='max(2,trunc({w}*({sc})/2)*2)':h=-2:eval=frame")
    else:
        parts.append(f"scale={max(2, int(round(w * float(sc) / 2)) * 2)}:-2")
    if "rotation" in kfs or abs(float(it.get("rotation", 0))) > 1e-3:
        rot = keyframe_expr(it, "rotation", tv, 0.0)
        parts.append(f"rotate=a='({rot})*PI/180':c=none:ow='hypot(iw,ih)':oh=ow")
    if "opacity" in kfs or animated_crop:
        # Deckkraft- und Zuschnitt-Keyframes als Alphamaske (Zuschnitt „an Ort und Stelle“)
        tt = f"(T-{s:.3f})"
        op = keyframe_expr(it, "opacity", tt, 1.0) if "opacity" in kfs else f"{float(it.get('opacity', 1.0)):.4f}"
        mask = "1"
        if animated_crop:
            cl, cr, ct, cb = (keyframe_expr({**it, p: static_value(it, p, kind)}, p, tt, 0.0) for p in CROP_PROPS)
            mask = f"gte(X,W*({cl}))*lt(X,W*(1-({cr})))*gte(Y,H*({ct}))*lt(Y,H*(1-({cb})))"
        parts.append(f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({op})*({mask})'")
    elif float(it.get("opacity", 1.0)) < 0.999:
        parts.append(f"colorchannelmixer=aa={float(it['opacity']):.3f}")
    if it.get("fade_in"):
        parts.append(f"fade=t=in:st={s:.3f}:d={it['fade_in']:.2f}:alpha=1")
    if it.get("fade_out"):
        parts.append(f"fade=t=out:st={s + d - it['fade_out']:.3f}:d={it['fade_out']:.2f}:alpha=1")
    return ",".join(parts) + label
