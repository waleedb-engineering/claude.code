"""Lokales Brand Kit — optionale, projektweite Marken-Defaults für Captions.

Bewusst simpel: eine JSON-Datei (kein Account, keine DB). Fehlt sie, gelten
Defaults und es wird KEIN Brand-Effekt aufs Rendering angewandt (bestehende
Ausgabe bleibt unverändert). Validierung ist streng genug, dass ungültige Werte
FFmpeg nie erreichen.
"""

from __future__ import annotations

import json
import os
import re

from .captions import STYLES, _norm_kw

# Speicherort (überschreibbar für Tests / eigene Setups).
BRAND_KIT_PATH = os.environ.get(
    "CLIPFORGE_BRAND_KIT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "config", "brand_kit.json"),
)

MAX_WATERMARK_LEN = 40
MAX_BRAND_NAME_LEN = 60
MAX_KEYWORDS = 20
MAX_KEYWORD_LEN = 30

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

DEFAULT_BRAND_KIT: dict = {
    "brand_name": "",
    "primary_color": "#FFDD00",
    "secondary_color": "#000000",
    "font_family": None,
    "caption_style_default": "clean",
    "highlight_keywords": [],
    "watermark_text": "",
    "watermark_enabled": False,
}


class BrandKitError(ValueError):
    """Ungültiges Brand Kit (→ HTTP 400)."""


def _expand_hex(value: str) -> str:
    """#RGB → #RRGGBB (sonst unverändert)."""
    if len(value) == 4:  # '#abc'
        return "#" + "".join(c * 2 for c in value[1:])
    return value


def _valid_hex(value) -> bool:
    return isinstance(value, str) and bool(_HEX_RE.match(value))


def brand_kit_exists() -> bool:
    return os.path.isfile(BRAND_KIT_PATH)


def load_brand_kit() -> dict:
    """Lädt das Brand Kit (Defaults + Datei-Overlay). Crasht nie."""
    data = dict(DEFAULT_BRAND_KIT)
    if brand_kit_exists():
        try:
            with open(BRAND_KIT_PATH, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                for k in DEFAULT_BRAND_KIT:
                    if k in stored:
                        data[k] = stored[k]
        except (OSError, ValueError):
            pass  # defekte Datei → Defaults
    data["_exists"] = brand_kit_exists()
    return data


def validate_brand_kit(payload: dict) -> dict:
    """Validiert + normalisiert ein Brand-Kit-dict. Wirft BrandKitError."""
    if not isinstance(payload, dict):
        raise BrandKitError("Brand Kit muss ein Objekt sein.")

    out = dict(DEFAULT_BRAND_KIT)

    brand_name = str(payload.get("brand_name", "") or "").strip()
    if len(brand_name) > MAX_BRAND_NAME_LEN:
        raise BrandKitError(f"brand_name zu lang (max {MAX_BRAND_NAME_LEN}).")
    out["brand_name"] = brand_name

    for key in ("primary_color", "secondary_color"):
        val = payload.get(key, DEFAULT_BRAND_KIT[key])
        if not _valid_hex(val):
            raise BrandKitError(
                f"{key} ist keine gültige Hex-Farbe (z. B. #FFCC00): {val!r}"
            )
        out[key] = _expand_hex(val).upper()

    font = payload.get("font_family")
    out["font_family"] = str(font).strip() if font else None

    style = payload.get("caption_style_default", DEFAULT_BRAND_KIT["caption_style_default"])
    if style not in STYLES:
        raise BrandKitError(
            f"caption_style_default unbekannt: {style!r}. "
            f"Erlaubt: {', '.join(sorted(STYLES))}."
        )
    out["caption_style_default"] = style

    kws = payload.get("highlight_keywords", []) or []
    if not isinstance(kws, list):
        raise BrandKitError("highlight_keywords muss eine Liste sein.")
    if len(kws) > MAX_KEYWORDS:
        raise BrandKitError(f"Zu viele highlight_keywords (max {MAX_KEYWORDS}).")
    clean_kws: list[str] = []
    for k in kws:
        s = str(k).strip()
        if not s:
            continue
        if len(s) > MAX_KEYWORD_LEN:
            raise BrandKitError(f"Keyword zu lang (max {MAX_KEYWORD_LEN}): {s!r}")
        clean_kws.append(s)
    out["highlight_keywords"] = clean_kws

    wm = str(payload.get("watermark_text", "") or "").strip()
    if len(wm) > MAX_WATERMARK_LEN:
        raise BrandKitError(f"watermark_text zu lang (max {MAX_WATERMARK_LEN}).")
    out["watermark_text"] = wm
    out["watermark_enabled"] = bool(payload.get("watermark_enabled", False))

    return out


def save_brand_kit(payload: dict) -> dict:
    """Validiert und speichert das Brand Kit. Gibt das gespeicherte dict zurück."""
    validated = validate_brand_kit(payload)
    os.makedirs(os.path.dirname(BRAND_KIT_PATH), exist_ok=True)
    with open(BRAND_KIT_PATH, "w", encoding="utf-8") as fh:
        json.dump(validated, fh, ensure_ascii=False, indent=2)
    result = dict(validated)
    result["_exists"] = True
    return result


def _hex_to_ass_inline(hexc: str) -> str:
    """#RRGGBB → ASS-Inline-Farbe &Hbbggrr& (für \\1c-Override)."""
    h = _expand_hex(hexc).lstrip("#")
    rr, gg, bb = h[0:2], h[2:4], h[4:6]
    return f"&H{bb}{gg}{rr}&".upper()


def _hex_to_ass_header(hexc: str) -> str:
    """#RRGGBB → ASS-Style-Farbe &H00BBGGRR (opak)."""
    h = _expand_hex(hexc).lstrip("#")
    rr, gg, bb = h[0:2], h[2:4], h[4:6]
    return f"&H00{bb}{gg}{rr}".upper()


def to_caption_overrides(brand: dict | None = None) -> dict:
    """Wandelt ein Brand Kit in Caption-Overrides für make_captions().

    Liefert **nur dann** Overrides, wenn eine Brand-Kit-Datei existiert — sonst
    ein leeres dict (kein Brand-Effekt, unveränderte Ausgabe).
    """
    brand = brand or load_brand_kit()
    if not brand.get("_exists"):
        return {}
    try:
        overrides: dict = {
            "highlight_color": _hex_to_ass_inline(brand["primary_color"]),
            "outline_color": _hex_to_ass_header(brand["secondary_color"]),
            "highlight_keywords": {
                _norm_kw(k) for k in (brand.get("highlight_keywords") or []) if _norm_kw(k)
            },
            "brand_kit_used": True,
            "brand_kit_name": brand.get("brand_name") or None,
        }
        if brand.get("watermark_enabled") and brand.get("watermark_text"):
            overrides["watermark_text"] = brand["watermark_text"]
        return overrides
    except Exception:  # noqa: BLE001 — Brand darf Rendering nie crashen
        return {}
