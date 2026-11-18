"""Übergänge (echtes FFmpeg-Rendering) und Vorlagen."""

import os

import pytest

from clipforge.studio import templates, transitions
from clipforge.studio.errors import StudioError
from clipforge.studio.projects import migrate, new_project, normalize_scene
from clipforge.studio.render import render_project


@pytest.fixture(autouse=True)
def _studio(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_STUDIO_DIR", str(tmp_path / "studio"))


def _project(**extra):
    p = new_project(title="T", workflow="script")
    p["scenes"] = [normalize_scene({"text": f"Szene {i} hat etwas Text.",
                                    "transition": tr})
                   for i, tr in enumerate(["auto", "fade", "zoom", "cut"])]
    p.update(extra)
    p["voice"]["provider"] = "none"
    return migrate(p)


def test_default_is_hard_cut_for_old_projects():
    p = migrate({"title": "alt", "scenes": [{"text": "a"}, {"text": "b"}]})
    assert p["transitions"] == {"style": "cut", "duration": 0.4}
    entries = [{"scene": s, "dur": 2.0} for s in p["scenes"]]
    assert transitions.plan(p, entries, 30) == [("cut", 0.0), ("cut", 0.0)]


def test_plan_limits_duration_and_resolves_auto():
    p = _project(transitions={"style": "auto", "duration": 1.5}, style="cinematic")
    entries = [{"scene": s, "dur": d} for s, d in zip(p["scenes"], [2.0, 1.0, 3.0, 3.0])]
    plan = transitions.plan(p, entries, 30)
    assert plan[0] == ("cut", 0.0)                 # erste Szene nie
    assert plan[1] == ("fade", pytest.approx(0.4))  # 40 % der kürzeren Szene (1 s)
    assert plan[2][0] == "zoom"
    assert plan[3] == ("cut", 0.0)
    assert transitions.extensions(plan) == [plan[1][1], plan[2][1], 0.0, 0.0]


def test_invalid_transition_is_normalized():
    assert normalize_scene({"text": "x", "transition": "explode"})["transition"] == "auto"


def test_render_with_transitions_keeps_duration(tmp_path):
    p = _project(transitions={"style": "fade", "duration": 0.5})
    os.makedirs(tmp_path / "media")
    report = render_project(p, str(tmp_path), mode="preview")
    assert [t["type"] for t in report["transitions"]] == ["fade", "zoom"]
    assert abs(report["duration"] - report["expected"]["duration"]) < 0.15


def test_builtin_templates_are_valid_and_readonly():
    ids = {t["id"] for t in templates.list_templates()}
    assert {"motivation", "reddit_story", "podcast_clip", "faceless"} <= ids
    with pytest.raises(StudioError):
        templates.delete_template("motivation")
    with pytest.raises(StudioError):
        templates.save_template({"name": "x"}, "motivation")


def test_apply_template_keeps_texts_and_sets_structure():
    p = _project()
    texts = [s["text"] for s in p["scenes"]]
    out = templates.apply_template(p, templates.get_template("gaming"))
    assert [s["text"] for s in out["scenes"]] == texts
    assert out["transitions"]["style"] == "zoom"
    assert out["music"]["beat_sync"] is True
    assert "Aufbau (Gaming-Clip)" in out["options"]["creative_instructions"]
    # erneutes Anwenden ersetzt die Aufbau-Anweisung statt sie zu stapeln
    again = templates.apply_template(out, templates.get_template("news"))
    assert again["options"]["creative_instructions"].count("Aufbau (") == 1


def test_empty_project_gets_scene_skeleton():
    p = migrate(new_project(title="leer", workflow="script"))
    out = templates.apply_template(p, templates.get_template("product_ad"))
    assert [s["kind"] for s in out["scenes"]] == ["hook", "body", "body", "cta"]


def test_custom_template_crud_and_validation():
    t = templates.save_template({"name": "Mein Stil", "settings": {
        "aspect_ratio": "1:1", "captions": {"style": "bold"}, "evil": 1,
        "transitions": {"style": "wipe", "duration": 99}}})
    assert t["settings"]["transitions"]["duration"] == 1.5
    assert "evil" not in t["settings"]
    updated = templates.save_template({"name": "Neu"}, t["id"])
    assert updated["name"] == "Neu"
    templates.delete_template(t["id"])
    with pytest.raises(StudioError):
        templates.get_template(t["id"])
    with pytest.raises(StudioError):
        templates.save_template({"name": "x", "settings": {"options": {"media_type": "bogus"}}})


def test_template_routes(tmp_path):
    from studio_helpers import clear_env, make_client
    client, _ = make_client(str(tmp_path))
    try:
        assert len(client.get("/api/studio/templates").json()["templates"]) >= 10
        r = client.post("/api/studio/projects", json={
            "workflow": "script", "script": "Hallo Welt. Zweiter Satz hier.",
            "template_id": "knowledge", "auto_ingest": False})
        assert r.status_code == 201, r.text
        proj = r.json()["project"]
        assert proj["template_id"] == "knowledge"
        assert proj["transitions"]["style"] == "smooth"
        saved = client.post("/api/studio/templates",
                            json={"name": "Aus Projekt", "from_project": proj["id"]})
        assert saved.status_code == 201
        assert saved.json()["template"]["settings"]["transitions"]["style"] == "smooth"
        r = client.post(f"/api/studio/projects/{proj['id']}/apply-template",
                        json={"template_id": "gaming", "expected_version": proj["version"]})
        assert r.status_code == 200, r.text
        assert r.json()["project"]["transitions"]["style"] == "zoom"
        stale = client.post(f"/api/studio/projects/{proj['id']}/apply-template",
                            json={"template_id": "news", "expected_version": proj["version"]})
        assert stale.status_code == 409
        assert client.delete("/api/studio/templates/motivation").status_code == 409
    finally:
        clear_env()
