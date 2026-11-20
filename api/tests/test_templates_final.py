"""Vorlagen-Bibliothek: jede Vorlage wirkt messbar auf Projekt und Render."""

from studio_helpers import make_service

from clipforge.studio import templates as tpl
from clipforge.studio.projects import migrate

REQUIRED = {"gaming", "twitch_clip", "youtube_shorts", "reddit_story", "podcast_clip", "interview",
            "knowledge", "product_ad", "cinematic", "motivation"}


def test_library_covers_requested_genres_and_differs():
    ids = {t["id"] for t in tpl.BUILTIN}
    assert REQUIRED <= ids
    base = migrate({"scenes": [{"kind": "hook", "text": "a"}, {"kind": "body", "text": "b"}]})
    fingerprints = set()
    for t in tpl.BUILTIN:
        p = tpl.apply_template(base, t)
        fp = (p["aspect_ratio"], p["style"], p["captions"]["style"], p["captions"]["position"],
              p["transitions"]["style"], p["music"]["volume"], p["voice"]["speed"], p["audio"]["loudnorm"],
              str(p["scenes"][0].get("zoom")))
        fingerprints.add(fp)
    assert len(fingerprints) == len(tpl.BUILTIN)        # keine zwei Vorlagen sind identisch


def test_twitch_template_sets_effects():
    base = migrate({"scenes": [{"kind": "body", "text": "x"}, {"kind": "hook", "text": "y"}]})
    p = tpl.apply_template(base, tpl.get_template("twitch_clip"))
    assert p["captions"]["position"] == "top" and p["captions"]["highlight_color"] == "#9146ff"
    assert p["audio"]["loudnorm"] is True and p["music"]["volume"] == 0.0
    assert p["scenes"][1]["zoom"] == {"factor": 1.3, "focus": "face", "ramp": True}
    assert "zoom" not in p["scenes"][0]
    draft = tpl.from_project(p)
    assert draft["settings"]["hook_zoom"]["focus"] == "face" and draft["settings"]["audio"]["loudnorm"]


def test_template_render_report_shows_effects(tmp_path):
    svc, _ = make_service(str(tmp_path))
    p = svc.create_project({"workflow": "script", "title": "T", "script": "Achtung. Das war knapp. Folgen!",
                            "voice": {"provider": "mock"}, "resolution": "720p"})
    svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
    p = svc.store.load(p["id"])
    applied = tpl.apply_template(p, tpl.get_template("youtube_shorts"))
    svc.update_project(p["id"], {k: applied[k] for k in ("captions", "audio", "transitions", "music", "voice")},
                       p["version"])
    t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
    assert t["status"] == "succeeded", t
    rep = svc.list_renders(p["id"])[0]
    assert rep["captions"]["layout"]["position"] == "middle"
    assert rep["loudness"]["applied"] is True
