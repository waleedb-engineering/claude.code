"""Tests für Caption-Styles, Brand Kit und brand-aware Rendering (Prompt 18)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.captions import STYLES, make_captions
from clipforge.config import Settings
from clipforge.models import ScoreBreakdown, ScoredClip, Word
from clipforge.render import render_clip

_HERE = os.path.dirname(os.path.abspath(__file__))
_API_DIR = os.path.dirname(_HERE)
_SAMPLE = os.path.join(_API_DIR, "testdata", "sample.mp4")
_TRANSCRIPT = os.path.join(_API_DIR, "testdata", "transcript.json")


def _ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _words() -> list[Word]:
    # kleine Wortfolge mit Timestamps für Karaoke
    return [
        Word(text="Warum", start=0.0, end=0.4),
        Word(text="scheitern", start=0.4, end=0.9),
        Word(text="die", start=0.9, end=1.1),
        Word(text="meisten", start=1.1, end=1.6),
        Word(text="Leute", start=1.6, end=2.1),
    ]


def _clip(words) -> ScoredClip:
    b = ScoreBreakdown(hook=70, clarity=65, emotion=60, pacing=55, payoff=50)
    text = " ".join(w.text for w in words)
    return ScoredClip(start=0.0, end=6.0, text=text, score=70.0, breakdown=b,
                      reason="", words=words)


# ------------------------- Caption-Styles ---------------------------------

def test_five_styles_exist():
    for sid in ("clean", "bold_creator", "high_energy", "podcast", "minimal"):
        assert sid in STYLES, sid
    assert len(STYLES) >= 5


def test_make_captions_each_style_produces_valid_ass():
    words = _words()
    for sid in STYLES:
        ass, info = make_captions(words, 0.0, 6.0, mode="karaoke", style=sid)
        assert "[V4+ Styles]" in ass and "Dialogue:" in ass
        assert info["caption_style"] == sid
        assert info["fallback"] is False


def test_unknown_style_falls_back_to_clean():
    ass, info = make_captions(_words(), 0.0, 6.0, mode="karaoke", style="does_not_exist")
    assert info["caption_style"] == "clean"
    assert info["fallback"] is True


def test_brand_overrides_apply_color_keywords_watermark():
    overrides = {
        "highlight_color": "&H0000FF&",   # rot (inline)
        "outline_color": "&H00FF0000",    # blau (header)
        "highlight_keywords": {"geld"},
        "watermark_text": "@acme",
        "brand_kit_used": True,
        "brand_kit_name": "Acme",
    }
    words = [Word("Mehr", 0.0, 0.4), Word("Geld", 0.4, 0.9), Word("heute", 0.9, 1.4)]
    ass, info = make_captions(words, 0.0, 4.0, mode="karaoke", style="clean",
                              overrides=overrides)
    assert "&H0000FF&" in ass            # highlight-Farbe
    assert "&H00FF0000" in ass           # outline in Style-Zeile
    assert "@acme" in ass                # Watermark-Event
    assert info["brand_kit_used"] is True
    assert info["brand_kit_name"] == "Acme"


def test_special_chars_do_not_break_ass():
    # Anführungszeichen, geschweifte Klammern, Backslash → dürfen ASS nicht killen
    words = [Word('{böse}', 0.0, 0.5), Word('\\pfad', 0.5, 1.0), Word('"zitat"', 1.0, 1.5)]
    ass, _ = make_captions(words, 0.0, 3.0, mode="standard", style="clean")
    # geschweifte Klammern → runde (sonst würde ASS sie als Override lesen)
    assert "(böse)" in ass
    assert "{böse}" not in ass
    # Backslash wird verdoppelt (escaped)
    assert "\\\\pfad" in ass
    # valides Dokument
    assert "[V4+ Styles]" in ass and "Dialogue:" in ass


# ------------------------- Brand Kit --------------------------------------

def _brand_env(tmp: str):
    path = os.path.join(tmp, "brand_kit.json")
    os.environ["CLIPFORGE_BRAND_KIT"] = path
    # brand_kit-Modul frisch laden, damit es den Pfad neu liest
    for m in ("clipforge.brand_kit",):
        sys.modules.pop(m, None)
    import importlib
    bk = importlib.import_module("clipforge.brand_kit")
    return bk


def test_brand_kit_defaults_when_no_file():
    tmp = tempfile.mkdtemp(prefix="brand_")
    try:
        bk = _brand_env(tmp)
        data = bk.load_brand_kit()
        assert data["_exists"] is False
        assert data["caption_style_default"] == "clean"
        # ohne Datei → keine Overrides (unveränderte Ausgabe)
        assert bk.to_caption_overrides(data) == {}
    finally:
        os.environ.pop("CLIPFORGE_BRAND_KIT", None)
        shutil.rmtree(tmp, ignore_errors=True)


def test_brand_kit_save_load_and_overrides():
    tmp = tempfile.mkdtemp(prefix="brand_")
    try:
        bk = _brand_env(tmp)
        saved = bk.save_brand_kit({
            "brand_name": "Acme", "primary_color": "#FF0000",
            "secondary_color": "#0000FF", "caption_style_default": "bold_creator",
            "highlight_keywords": ["Geld", "Hook"], "watermark_text": "@acme",
            "watermark_enabled": True,
        })
        assert saved["_exists"] is True
        loaded = bk.load_brand_kit()
        assert loaded["brand_name"] == "Acme"
        ov = bk.to_caption_overrides(loaded)
        assert ov["brand_kit_used"] is True
        assert ov["brand_kit_name"] == "Acme"
        assert ov["highlight_color"] == "&H0000FF&"   # #FF0000 → rot inline (bb gg rr)
        assert "geld" in ov["highlight_keywords"]
        assert ov["watermark_text"] == "@acme"
    finally:
        os.environ.pop("CLIPFORGE_BRAND_KIT", None)
        shutil.rmtree(tmp, ignore_errors=True)


def test_brand_kit_invalid_color_and_style_raise():
    tmp = tempfile.mkdtemp(prefix="brand_")
    try:
        bk = _brand_env(tmp)
        for bad in ({"primary_color": "red"}, {"secondary_color": "#12"},
                    {"caption_style_default": "nope"},
                    {"watermark_text": "x" * 41}):
            try:
                bk.validate_brand_kit(bad)
                assert False, f"sollte werfen: {bad}"
            except bk.BrandKitError:
                pass
    finally:
        os.environ.pop("CLIPFORGE_BRAND_KIT", None)
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------- Render mit jedem Style (ffmpeg) ----------------

def test_render_each_style_produces_valid_mp4():
    if not _ffmpeg() or not os.path.exists(_SAMPLE):
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    settings = Settings(anthropic_api_key=None, use_llm=False)
    for sid in STYLES:
        out = tempfile.mkdtemp(prefix=f"rst_{sid}_")
        try:
            clip = _clip(_words())
            out_path = os.path.join(out, "clip.mp4")
            render_clip(_SAMPLE, clip, out_path, settings,
                        remove_silence=False, caption_mode="karaoke",
                        caption_style=sid, reframe_mode="center")
            assert os.path.exists(out_path) and os.path.getsize(out_path) > 5000, sid
        finally:
            shutil.rmtree(out, ignore_errors=True)


def test_render_with_brand_colors_does_not_crash_ffmpeg():
    if not _ffmpeg() or not os.path.exists(_SAMPLE):
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    settings = Settings(anthropic_api_key=None, use_llm=False)
    overrides = {
        "highlight_color": "&H0000FF&", "outline_color": "&H00FF0000",
        "highlight_keywords": {"leute"}, "watermark_text": "@acme",
        "brand_kit_used": True, "brand_kit_name": "Acme",
    }
    out = tempfile.mkdtemp(prefix="rbrand_")
    try:
        clip = _clip(_words())
        out_path = os.path.join(out, "clip.mp4")
        info = render_clip(_SAMPLE, clip, out_path, settings,
                           remove_silence=True, caption_mode="karaoke",
                           caption_style="high_energy", reframe_mode="smart",
                           brand_overrides=overrides)
        assert os.path.exists(out_path) and os.path.getsize(out_path) > 5000
        assert clip.caption_info["brand_kit_used"] is True
        # Silence-Removal + Reframe liefen (Infos gesetzt)
        assert clip.silence_info is not None and clip.reframe_info is not None
    finally:
        shutil.rmtree(out, ignore_errors=True)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
