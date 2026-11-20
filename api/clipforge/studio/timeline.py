"""Mehrspur-Timeline (nicht-linear) für Studio-Projekte.

Schema (``project["timeline"]``, Version 1)::

    {"version": 1, "tracks": [
       {"id", "kind": "video"|"overlay"|"audio"|"caption", "name",
        "muted": bool, "locked": bool, "hidden": bool,
        "items": [{"id", "start", "duration", "group"?, ...art-spezifisch}]}]}

- Spuren liegen in Listenreihenfolge übereinander (erste = unten).
- Hat das Projekt Szenen, ist das gerenderte Szenenprogramm die Grundebene;
  Timeline-Spuren werden darüber gelegt bzw. dazugemischt. Ohne Szenen ist
  die Timeline allein das Video (schwarzer Grund, Länge = letztes Element).
- Video-/Overlay-Elemente: ``src`` (Projektmedium), ``in`` (Quell-Offset),
  ``x``/``y`` (Mittelpunkt als Anteil 0–1), ``scale`` (Breite als Anteil der
  Bildbreite), ``rotation`` (Grad), ``opacity`` (0–1), ``crop`` (Ränder als
  Anteile), ``blur`` (statisch), ``fade_in``/``fade_out``, ``audio`` (Ton des
  Videos mitmischen), ``volume``.
- Audio-Elemente: ``src`` (Projektmedium oder ``library:<titel>``), ``in``,
  ``volume``, ``fade_in``/``fade_out``.
- Untertitel-Elemente: ``text``, ``color``, ``size``, ``position``.
- Keyframes: ``keyframes[eigenschaft] = [{"t": Sekunde ab Elementbeginn,
  "v": Wert, "ease": linear|ease_in|ease_out|ease_in_out}]`` für x, y, scale,
  rotation, opacity, volume. Sie werden beim Rendern in FFmpeg-Ausdrücke
  übersetzt (``keyframe_expr``) — UI und KI-Assistent erzeugen dieselben Daten.

Alle Operationen sind reine Funktionen auf einer Kopie und werfen
``StudioError`` bei ungültigen Eingaben oder gesperrten Spuren.
"""

from __future__ import annotations

import copy
import math
import os

from .errors import StudioError
from .storage import new_id

VERSION = 1
TRACK_KINDS = ("video", "overlay", "audio", "caption")
EASES = ("linear", "ease_in", "ease_out", "ease_in_out")
KEYFRAME_PROPS = {
    "video": ("x", "y", "scale", "rotation", "opacity", "volume"),
    "overlay": ("x", "y", "scale", "rotation", "opacity", "volume"),
    "audio": ("volume",),
    "caption": (),
}
RANGES = {"x": (-1.0, 2.0), "y": (-1.0, 2.0), "scale": (0.02, 4.0), "rotation": (-360.0, 360.0),
          "opacity": (0.0, 1.0), "volume": (0.0, 3.0)}
DEFAULTS = {"video": {"x": 0.5, "y": 0.5, "scale": 1.0, "rotation": 0.0, "opacity": 1.0, "volume": 1.0},
            "overlay": {"x": 0.5, "y": 0.5, "scale": 0.4, "rotation": 0.0, "opacity": 1.0, "volume": 1.0},
            "audio": {"volume": 1.0}, "caption": {}}
CAPTION_POS = ("top", "middle", "bottom")
MAX_TRACKS, MAX_ITEMS, MAX_KEYFRAMES = 16, 400, 64
MAX_TIME = 4 * 3600.0


def _num(v, lo, hi, default):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return max(lo, min(hi, f))


def empty() -> dict:
    return {"version": VERSION, "tracks": []}


def has_content(tl: dict | None) -> bool:
    return bool(tl and any(t["items"] for t in tl.get("tracks", [])))


# ----------------------------------------------------------------- Prüfen
def _check_src(src: str, project_dir: str | None, kind: str) -> str:
    from .audio import AUDIO_EXT
    from .projects import IMAGE_EXT, VIDEO_EXT, resolve_music
    from .storage import safe_child, safe_filename
    src = str(src or "")
    if kind == "audio" and src.startswith(("library:", "project:")):
        if project_dir is not None:
            resolve_music(project_dir, src)
        return src[:200]
    name = safe_filename(src)
    if not name or name != src:
        raise StudioError("validation_error", f"Ungültige Mediendatei '{src[:60]}'.")
    ext = os.path.splitext(name)[1].lower()
    allowed = AUDIO_EXT | VIDEO_EXT if kind == "audio" else IMAGE_EXT | VIDEO_EXT
    if ext not in allowed:
        raise StudioError("validation_error", f"Dateityp {ext or '?'} passt nicht auf eine {kind}-Spur.")
    if project_dir is not None and not os.path.isfile(safe_child(os.path.join(project_dir, "media"), name)):
        raise StudioError("media_not_found", f"Mediendatei '{name}' gibt es in diesem Projekt nicht.", 404)
    return name


def _norm_keyframes(raw, kind: str) -> dict:
    out = {}
    if not isinstance(raw, dict):
        return out
    for prop, kfs in raw.items():
        if prop not in KEYFRAME_PROPS[kind] or not isinstance(kfs, list):
            continue
        lo, hi = RANGES[prop]
        clean, seen = [], set()
        for k in kfs[:MAX_KEYFRAMES]:
            if not isinstance(k, dict):
                continue
            t = round(_num(k.get("t"), 0.0, MAX_TIME, 0.0), 3)
            if t in seen:
                continue
            seen.add(t)
            clean.append({"t": t, "v": round(_num(k.get("v"), lo, hi, DEFAULTS[kind].get(prop, 0.0)), 4),
                          "ease": k.get("ease") if k.get("ease") in EASES else "linear"})
        if clean:
            out[prop] = sorted(clean, key=lambda k: k["t"])
    return out


def _norm_item(raw: dict, kind: str, project_dir: str | None) -> dict:
    if not isinstance(raw, dict):
        raise StudioError("validation_error", "Timeline-Element hat ein ungültiges Format.")
    from .storage import is_safe_id
    item = {"id": raw["id"] if is_safe_id(raw.get("id")) else new_id(),
            "start": round(_num(raw.get("start"), 0.0, MAX_TIME, 0.0), 3),
            "duration": round(_num(raw.get("duration"), 0.05, MAX_TIME, 3.0), 3)}
    if is_safe_id(raw.get("group")):
        item["group"] = raw["group"]
    if kind == "caption":
        item["text"] = str(raw.get("text") or "").strip()[:300]
        from .projects import _HEX
        item["color"] = raw.get("color") if _HEX.match(str(raw.get("color") or "")) else "#ffffff"
        item["size"] = round(_num(raw.get("size"), 0.4, 3.0, 1.0), 2)
        item["position"] = raw.get("position") if raw.get("position") in CAPTION_POS else "bottom"
        return item
    item["src"] = _check_src(raw.get("src"), project_dir, kind)
    item["in"] = round(_num(raw.get("in"), 0.0, MAX_TIME, 0.0), 3)
    item["fade_in"] = round(_num(raw.get("fade_in"), 0.0, 10.0, 0.0), 2)
    item["fade_out"] = round(_num(raw.get("fade_out"), 0.0, 10.0, 0.0), 2)
    for prop, default in DEFAULTS[kind].items():
        lo, hi = RANGES[prop]
        item[prop] = round(_num(raw.get(prop), lo, hi, default), 4)
    if kind in ("video", "overlay"):
        crop = raw.get("crop") if isinstance(raw.get("crop"), dict) else {}
        c = {k: round(_num(crop.get(k), 0.0, 0.45, 0.0), 3) for k in ("left", "right", "top", "bottom")}
        if any(c.values()):
            item["crop"] = c
        item["blur"] = round(_num(raw.get("blur"), 0.0, 40.0, 0.0), 1)
        item["audio"] = bool(raw.get("audio", kind == "video"))
    item["keyframes"] = _norm_keyframes(raw.get("keyframes"), kind)
    return item


def normalize(raw, project_dir: str | None = None) -> dict:
    """Validiert/normalisiert eine Timeline (auch ältere oder fehlende)."""
    if not isinstance(raw, dict):
        return empty()
    tracks_raw = raw.get("tracks") if isinstance(raw.get("tracks"), list) else []
    if len(tracks_raw) > MAX_TRACKS:
        raise StudioError("validation_error", f"Höchstens {MAX_TRACKS} Spuren.")
    from .storage import is_safe_id
    tracks, total_items, ids = [], 0, set()
    for t in tracks_raw:
        if not isinstance(t, dict) or t.get("kind") not in TRACK_KINDS:
            raise StudioError("validation_error", "Spur mit unbekannter Art.")
        kind = t["kind"]
        tid = t["id"] if is_safe_id(t.get("id")) else new_id()
        items = []
        for it in (t.get("items") if isinstance(t.get("items"), list) else []):
            items.append(_norm_item(it, kind, project_dir))
        total_items += len(items)
        if total_items > MAX_ITEMS:
            raise StudioError("validation_error", f"Höchstens {MAX_ITEMS} Elemente in der Timeline.")
        for x in [tid] + [i["id"] for i in items]:
            if x in ids:
                raise StudioError("validation_error", "Spur- und Element-IDs müssen eindeutig sein.")
            ids.add(x)
        tracks.append({"id": tid, "kind": kind, "name": str(t.get("name") or kind.capitalize())[:40],
                       "muted": bool(t.get("muted")), "locked": bool(t.get("locked")),
                       "hidden": bool(t.get("hidden")),
                       "items": sorted(items, key=lambda i: i["start"])})
    return {"version": VERSION, "tracks": tracks}


def end_time(tl: dict) -> float:
    return max([i["start"] + i["duration"] for t in tl.get("tracks", []) for i in t["items"]] or [0.0])


# ----------------------------------------------------------- Keyframes
def value_at(item: dict, prop: str, u: float, kind: str = "overlay") -> float:
    """Wert einer Eigenschaft zur lokalen Zeit u (gleiche Kurve wie im Render)."""
    kfs = (item.get("keyframes") or {}).get(prop)
    if not kfs:
        return float(item.get(prop, DEFAULTS.get(kind, {}).get(prop, 0.0)))
    if u <= kfs[0]["t"]:
        return kfs[0]["v"]
    for a, b in zip(kfs, kfs[1:]):
        if u < b["t"]:
            p = (u - a["t"]) / (b["t"] - a["t"])
            return a["v"] + (b["v"] - a["v"]) * _ease(a["ease"], p)
    return kfs[-1]["v"]


def _ease(name: str, p: float) -> float:
    if name == "ease_in":
        return p * p
    if name == "ease_out":
        return 1 - (1 - p) * (1 - p)
    if name == "ease_in_out":
        return 2 * p * p if p < 0.5 else 1 - 2 * (1 - p) * (1 - p)
    return p


def _ease_expr(name: str, p: str) -> str:
    if name == "ease_in":
        return f"({p})*({p})"
    if name == "ease_out":
        return f"(1-(1-({p}))*(1-({p})))"
    if name == "ease_in_out":
        return f"if(lt({p},0.5),2*({p})*({p}),1-2*(1-({p}))*(1-({p})))"
    return f"({p})"


def keyframe_expr(item: dict, prop: str, tvar: str, default: float) -> str:
    """FFmpeg-Ausdruck der Eigenschaft über der lokalen Zeitvariable ``tvar``."""
    kfs = (item.get("keyframes") or {}).get(prop)
    if not kfs:
        return f"{float(item.get(prop, default)):.6g}"
    expr = f"{kfs[-1]['v']:.6g}"
    for a, b in reversed(list(zip(kfs, kfs[1:]))):
        span = max(1e-3, b["t"] - a["t"])
        p = f"(({tvar})-{a['t']:.4f})/{span:.4f}"
        seg = f"({a['v']:.6g}+({b['v'] - a['v']:.6g})*{_ease_expr(a['ease'], p)})"
        expr = f"if(lt({tvar},{b['t']:.4f}),{seg},{expr})"
    return f"if(lt({tvar},{kfs[0]['t']:.4f}),{kfs[0]['v']:.6g},{expr})"


# ------------------------------------------------------------ Operationen
def _find(tl: dict, item_id: str) -> tuple[dict, dict]:
    for t in tl["tracks"]:
        for i in t["items"]:
            if i["id"] == item_id:
                return t, i
    raise StudioError("not_found", "Timeline-Element nicht gefunden.", 404)


def _track(tl: dict, track_id: str) -> dict:
    for t in tl["tracks"]:
        if t["id"] == track_id:
            return t
    raise StudioError("not_found", "Spur nicht gefunden.", 404)


def _unlocked(track: dict) -> None:
    if track.get("locked"):
        raise StudioError("track_locked", f"Spur „{track['name']}“ ist gesperrt.", 409)


def _members(tl: dict, item: dict) -> list[tuple[dict, dict]]:
    if not item.get("group"):
        return [_find(tl, item["id"])]
    return [(t, i) for t in tl["tracks"] for i in t["items"] if i.get("group") == item["group"]]


def snap_points(tl: dict, exclude: set, playhead: float | None = None) -> list[float]:
    pts = {0.0}
    for t in tl["tracks"]:
        for i in t["items"]:
            if i["id"] not in exclude:
                pts.update((i["start"], i["start"] + i["duration"]))
    if playhead is not None:
        pts.add(playhead)
    return sorted(pts)


def _snap(value: float, points: list[float], threshold: float) -> float:
    best = min(points, key=lambda p: abs(p - value), default=None)
    return best if best is not None and abs(best - value) <= threshold else value


def add_track(tl: dict, kind: str, name: str = "") -> tuple[dict, dict]:
    if kind not in TRACK_KINDS:
        raise StudioError("validation_error", f"Spurart: {', '.join(TRACK_KINDS)}.")
    tl = copy.deepcopy(tl)
    if len(tl["tracks"]) >= MAX_TRACKS:
        raise StudioError("validation_error", f"Höchstens {MAX_TRACKS} Spuren.")
    n = sum(1 for t in tl["tracks"] if t["kind"] == kind) + 1
    track = {"id": new_id(), "kind": kind, "name": (name or f"{kind.capitalize()} {n}")[:40],
             "muted": False, "locked": False, "hidden": False, "items": []}
    tl["tracks"].append(track)
    return tl, track


def add_item(tl: dict, track_id: str, item: dict, project_dir: str | None = None) -> tuple[dict, dict]:
    tl = copy.deepcopy(tl)
    track = _track(tl, track_id)
    _unlocked(track)
    new = _norm_item({k: v for k, v in item.items() if k != "id"}, track["kind"], project_dir)
    track["items"].append(new)
    track["items"].sort(key=lambda i: i["start"])
    return tl, new


def move_item(tl: dict, item_id: str, start: float, *, track_id: str | None = None, snap: bool = True,
              threshold: float = 0.15, playhead: float | None = None) -> dict:
    """Verschiebt ein Element (mit seiner Gruppe), optional mit Einrasten an Kanten/Abspielkopf."""
    tl = copy.deepcopy(tl)
    track, item = _find(tl, item_id)
    members = _members(tl, item)
    for t, _ in members:
        _unlocked(t)
    start = max(0.0, float(start))
    if snap:
        excl = {i["id"] for _, i in members}
        pts = snap_points(tl, excl, playhead)
        cands = [c for c in (_snap(start, pts, threshold),
                             _snap(start + item["duration"], pts, threshold) - item["duration"])
                 if abs(c - start) > 1e-9]
        if cands:  # nur Kanten, die wirklich eingerastet sind; die nächste gewinnt
            start = min(cands, key=lambda c: abs(c - start))
    delta = max(-min(i["start"] for _, i in members), start - item["start"])
    for _, i in members:
        i["start"] = round(i["start"] + delta, 3)
    if track_id and track_id != track["id"]:
        if item.get("group"):
            raise StudioError("validation_error", "Gruppierte Elemente nur gemeinsam auf ihrer Spur verschieben.")
        dest = _track(tl, track_id)
        _unlocked(dest)
        if not _compatible(track["kind"], dest["kind"]):
            raise StudioError("validation_error", f"Ein {track['kind']}-Element passt nicht auf eine {dest['kind']}-Spur.")
        track["items"].remove(item)
        dest["items"].append(item)
    for t in tl["tracks"]:
        t["items"].sort(key=lambda i: i["start"])
    return tl


def _compatible(a: str, b: str) -> bool:
    return a == b or {a, b} == {"video", "overlay"}


def trim_item(tl: dict, item_id: str, edge: str, time: float, *, snap: bool = True,
              threshold: float = 0.15) -> dict:
    """Kante auf eine Timeline-Zeit setzen. Vorne trimmen verschiebt auch den Quell-Offset."""
    tl = copy.deepcopy(tl)
    track, item = _find(tl, item_id)
    _unlocked(track)
    if snap:
        time = _snap(float(time), snap_points(tl, {item_id}), threshold)
    end = item["start"] + item["duration"]
    if edge == "start":
        time = max(0.0, min(float(time), end - 0.05))
        shift = time - item["start"]
        if "in" in item:
            if item["in"] + shift < 0:
                shift = -item["in"]
                time = item["start"] + shift
            item["in"] = round(item["in"] + shift, 3)
        _shift_keyframes(item, -shift)
        item["start"], item["duration"] = round(time, 3), round(end - time, 3)
    elif edge == "end":
        time = max(item["start"] + 0.05, float(time))
        item["duration"] = round(time - item["start"], 3)
    else:
        raise StudioError("validation_error", "edge: start oder end.")
    return tl


def _shift_keyframes(item: dict, delta: float) -> None:
    """Keyframes relativ zum Elementbeginn verschieben (bei vorderem Trim/Split)."""
    for prop, kfs in list((item.get("keyframes") or {}).items()):
        moved = [{**k, "t": round(k["t"] + delta, 3)} for k in kfs]
        keep = [k for k in moved if k["t"] >= 0]
        if len(keep) < len(moved) and moved:
            # Wert am neuen Anfang erhalten, damit die Kurve gleich bleibt
            v0 = value_at({"keyframes": {prop: kfs}}, prop, -delta)
            keep = [{"t": 0.0, "v": round(v0, 4), "ease": "linear"}] + [k for k in keep if k["t"] > 0]
        item["keyframes"][prop] = keep


def split_item(tl: dict, item_id: str, at: float) -> tuple[dict, dict]:
    """Teilt am Zeitpunkt ``at`` (Timeline-Zeit) in zwei Elemente."""
    tl = copy.deepcopy(tl)
    track, item = _find(tl, item_id)
    _unlocked(track)
    end = item["start"] + item["duration"]
    if not item["start"] + 0.05 <= at <= end - 0.05:
        raise StudioError("validation_error", "Teilungspunkt liegt nicht im Element.")
    right = copy.deepcopy(item)
    right["id"] = new_id()
    right.pop("group", None)
    local = at - item["start"]
    item["duration"] = round(local, 3)
    right["start"], right["duration"] = round(at, 3), round(end - at, 3)
    if "in" in right:
        right["in"] = round(right["in"] + local, 3)
    if "fade_out" in item:
        item["fade_out"], right["fade_in"] = 0.0, 0.0
    _shift_keyframes(right, -local)
    for prop, kfs in list((item.get("keyframes") or {}).items()):
        inside = [k for k in kfs if k["t"] <= local]
        if len(inside) < len(kfs):
            inside.append({"t": round(local, 3), "v": round(value_at({"keyframes": {prop: kfs}}, prop, local), 4),
                           "ease": "linear"})
        item["keyframes"][prop] = inside
    track["items"].append(right)
    track["items"].sort(key=lambda i: i["start"])
    return tl, right


def slip_item(tl: dict, item_id: str, delta: float, source_duration: float | None = None) -> dict:
    """Quellausschnitt verschieben, Position und Länge auf der Timeline bleiben."""
    tl = copy.deepcopy(tl)
    track, item = _find(tl, item_id)
    _unlocked(track)
    if "in" not in item:
        raise StudioError("validation_error", "Nur Medien-Elemente lassen sich slippen.")
    new_in = max(0.0, item["in"] + float(delta))
    if source_duration:
        new_in = min(new_in, max(0.0, source_duration - item["duration"]))
    item["in"] = round(new_in, 3)
    return tl


def ripple_delete(tl: dict, item_id: str) -> dict:
    """Löscht und schließt die Lücke auf derselben Spur."""
    tl = copy.deepcopy(tl)
    track, item = _find(tl, item_id)
    _unlocked(track)
    track["items"].remove(item)
    for i in track["items"]:
        if i["start"] >= item["start"] + item["duration"] - 1e-6:
            i["start"] = round(max(0.0, i["start"] - item["duration"]), 3)
    return tl


def delete_item(tl: dict, item_id: str) -> dict:
    tl = copy.deepcopy(tl)
    track, item = _find(tl, item_id)
    _unlocked(track)
    track["items"].remove(item)
    return tl


def duplicate_item(tl: dict, item_id: str) -> tuple[dict, dict]:
    tl = copy.deepcopy(tl)
    track, item = _find(tl, item_id)
    _unlocked(track)
    dup = copy.deepcopy(item)
    dup["id"] = new_id()
    dup.pop("group", None)
    dup["start"] = round(item["start"] + item["duration"], 3)
    track["items"].append(dup)
    track["items"].sort(key=lambda i: i["start"])
    return tl, dup


def group_items(tl: dict, item_ids: list[str]) -> tuple[dict, str]:
    tl = copy.deepcopy(tl)
    if len(item_ids) < 2:
        raise StudioError("validation_error", "Zum Gruppieren mindestens zwei Elemente wählen.")
    gid = new_id()
    for iid in item_ids:
        t, i = _find(tl, iid)
        _unlocked(t)
        i["group"] = gid
    return tl, gid


def ungroup(tl: dict, item_id: str) -> dict:
    tl = copy.deepcopy(tl)
    _, item = _find(tl, item_id)
    gid = item.get("group")
    for t in tl["tracks"]:
        for i in t["items"]:
            if gid and i.get("group") == gid:
                i.pop("group", None)
    return tl


def set_track(tl: dict, track_id: str, **flags) -> dict:
    tl = copy.deepcopy(tl)
    t = _track(tl, track_id)
    for k in ("muted", "locked", "hidden"):
        if flags.get(k) is not None:
            t[k] = bool(flags[k])
    if flags.get("name"):
        t["name"] = str(flags["name"])[:40]
    return tl


def set_item(tl: dict, item_id: str, props: dict, project_dir: str | None = None) -> dict:
    """Eigenschaften setzen (gleiche Validierung wie beim Laden)."""
    tl = copy.deepcopy(tl)
    track, item = _find(tl, item_id)
    _unlocked(track)
    merged = {**item, **{k: v for k, v in props.items() if k not in ("id",)}}
    new = _norm_item(merged, track["kind"], project_dir)
    track["items"][track["items"].index(item)] = new
    track["items"].sort(key=lambda i: i["start"])
    return tl


def set_keyframe(tl: dict, item_id: str, prop: str, t: float, v: float, ease: str = "linear") -> dict:
    tl = copy.deepcopy(tl)
    track, item = _find(tl, item_id)
    _unlocked(track)
    if prop not in KEYFRAME_PROPS[track["kind"]]:
        raise StudioError("validation_error",
                          f"Eigenschaft '{prop}' lässt sich auf {track['kind']}-Spuren nicht animieren.")
    if ease not in EASES:
        raise StudioError("validation_error", f"Übergang: {', '.join(EASES)}.")
    t = round(max(0.0, min(float(t), item["duration"])), 3)
    kfs = [k for k in (item.setdefault("keyframes", {}).get(prop) or []) if abs(k["t"] - t) > 1e-6]
    if len(kfs) >= MAX_KEYFRAMES:
        raise StudioError("validation_error", f"Höchstens {MAX_KEYFRAMES} Keyframes je Eigenschaft.")
    lo, hi = RANGES[prop]
    kfs.append({"t": t, "v": round(max(lo, min(hi, float(v))), 4), "ease": ease})
    item["keyframes"][prop] = sorted(kfs, key=lambda k: k["t"])
    return tl


def remove_keyframe(tl: dict, item_id: str, prop: str, t: float) -> dict:
    tl = copy.deepcopy(tl)
    track, item = _find(tl, item_id)
    _unlocked(track)
    kfs = [k for k in (item.get("keyframes") or {}).get(prop, []) if abs(k["t"] - float(t)) > 1e-3]
    if kfs:
        item["keyframes"][prop] = kfs
    else:
        (item.get("keyframes") or {}).pop(prop, None)
    return tl


# --------------------------------------------- gemeinsame Op-Schnittstelle
OPS = ("add_track", "add_item", "move", "trim", "split", "slip", "delete", "ripple_delete", "duplicate",
       "group", "ungroup", "set_track", "set_item", "set_keyframe", "remove_keyframe")


def apply_op(tl: dict, op: dict, project_dir: str | None = None) -> tuple[dict, dict]:
    """Eine Bearbeitung ausführen — dieselbe Funktion für Editor-UI und KI-Assistent.

    → (neue Timeline, Ergebnis-Info)."""
    if not isinstance(op, dict) or op.get("op") not in OPS:
        raise StudioError("validation_error", f"Unbekannte Timeline-Operation. Erlaubt: {', '.join(OPS)}.")
    name = op["op"]
    iid = op.get("item")
    if name == "add_track":
        tl, t = add_track(tl, op.get("kind", ""), op.get("name", ""))
        return tl, {"track": t["id"]}
    if name == "add_item":
        track = op.get("track")
        if not track and op.get("track_kind") in TRACK_KINDS:
            # erste nicht gesperrte Spur dieser Art, sonst neue Spur anlegen
            found = next((t for t in tl["tracks"] if t["kind"] == op["track_kind"] and not t["locked"]), None)
            if found is None:
                tl, found = add_track(tl, op["track_kind"])
            track = found["id"]
        tl, it = add_item(tl, track or "", op.get("item") or {}, project_dir)
        return tl, {"item": it["id"], "track": track}
    if name == "move":
        return move_item(tl, iid, float(op.get("start", 0)), track_id=op.get("track"),
                         snap=bool(op.get("snap", True)), playhead=op.get("playhead")), {"item": iid}
    if name == "trim":
        return trim_item(tl, iid, op.get("edge", ""), float(op.get("time", 0)),
                         snap=bool(op.get("snap", True))), {"item": iid}
    if name == "split":
        tl, right = split_item(tl, iid, float(op.get("at", 0)))
        return tl, {"item": iid, "new_item": right["id"]}
    if name == "slip":
        return slip_item(tl, iid, float(op.get("delta", 0)), op.get("source_duration")), {"item": iid}
    if name == "delete":
        return delete_item(tl, iid), {}
    if name == "ripple_delete":
        return ripple_delete(tl, iid), {}
    if name == "duplicate":
        tl, dup = duplicate_item(tl, iid)
        return tl, {"new_item": dup["id"]}
    if name == "group":
        tl, gid = group_items(tl, list(op.get("items") or []))
        return tl, {"group": gid}
    if name == "ungroup":
        return ungroup(tl, iid), {}
    if name == "set_track":
        return set_track(tl, op.get("track", ""), muted=op.get("muted"), locked=op.get("locked"),
                         hidden=op.get("hidden"), name=op.get("name")), {}
    if name == "set_item":
        return set_item(tl, iid, op.get("props") or {}, project_dir), {"item": iid}
    if name == "set_keyframe":
        return set_keyframe(tl, iid, op.get("prop", ""), float(op.get("t", 0)), float(op.get("v", 0)),
                            op.get("ease", "linear")), {"item": iid}
    return remove_keyframe(tl, iid, op.get("prop", ""), float(op.get("t", 0))), {"item": iid}
