"""Titel-/Hashtag-Vorschläge (lokal echt, Claude nachgebildet) und YouTube-Trends (API nachgebildet)."""

import json

import pytest

from clipforge.studio import social_copy, trends
from clipforge.studio.errors import StudioError
from clipforge.studio.projects import migrate, new_project, normalize_scene
from studio_helpers import clear_env, make_client


def _project():
    p = new_project(title="Neues Video", workflow="script")
    p["scenes"] = [normalize_scene(x) for x in (
        {"kind": "hook", "text": "Warum Kaffee am Morgen nicht sofort wach macht."},
        {"text": "Kaffee blockiert Adenosin, aber erst nach etwa zwanzig Minuten."},
        {"kind": "cta", "text": "Folge für mehr Kaffee-Wissen."})]
    return migrate(p)


def test_local_suggestions_respect_platform_limits():
    out = social_copy.local(_project())
    assert out["engine"] == "local" and out["cost_usd"] == 0
    assert "kaffee" in out["keywords"][:3]
    for platform, (tmax, dmax, hmax) in social_copy.LIMITS.items():
        s = out["platforms"][platform]
        assert len(s["title"]) <= tmax and len(s["description"]) <= dmax
        assert len(s["hashtags"]) <= hmax and all(" " not in h for h in s["hashtags"])
    assert "shorts" in out["platforms"]["youtube_shorts"]["hashtags"]
    assert out["platforms"]["tiktok"]["title"].startswith("Warum Kaffee")


def test_llm_suggestions_are_clamped(monkeypatch):
    long = "x" * 999
    monkeypatch.setattr(social_copy, "LLM_CALL", lambda s, p: json.dumps({
        "keywords": ["kaffee"], "platforms": {"x": {"title": long, "description": long,
                                                    "hashtags": ["a b", "#c", "d", "e"]}}}))
    out = social_copy.with_llm(_project())
    assert len(out["platforms"]["x"]["description"]) == 280
    assert out["platforms"]["x"]["hashtags"] == ["ab", "c"]
    assert out["platforms"]["tiktok"]["title"]   # fehlende Plattform → lokaler Vorschlag


def test_social_copy_route_needs_cost_confirmation_and_budget(tmp_path, monkeypatch):
    client, _ = make_client(str(tmp_path))
    try:
        monkeypatch.setattr(social_copy, "LLM_CALL", lambda s, p: "{}")
        pid = client.post("/api/studio/projects", json={
            "workflow": "script", "script": "Kaffee am Morgen macht wach. Wirklich.",
            "auto_ingest": False}).json()["project"]["id"]
        assert client.post(f"/api/studio/projects/{pid}/social-copy", json={}).status_code == 200
        r = client.post(f"/api/studio/projects/{pid}/social-copy", json={"engine": "anthropic"})
        assert r.status_code == 402
        r = client.post(f"/api/studio/projects/{pid}/social-copy",
                        json={"engine": "anthropic", "confirm_cost": True})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "budget_exceeded"  # Budget 0
    finally:
        clear_env()


def test_youtube_trends_from_api(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(StudioError) as err:
        trends.youtube_trends()
    assert err.value.code == "credential_not_set"
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")
    seen = []
    monkeypatch.setattr(trends, "API_GET", lambda url: seen.append(url) or {"items": [
        {"id": "a1", "snippet": {"title": "Kaffee Experiment am Morgen", "channelTitle": "C",
                                 "tags": ["kaffee", "experiment"]}, "statistics": {"viewCount": "1200"}},
        {"id": "b2", "snippet": {"title": "Kaffee Fakten"}, "statistics": {}}]})
    out = trends.youtube_trends("DE", "28")
    assert "chart=mostPopular" in seen[0] and "videoCategoryId=28" in seen[0]
    assert out["videos"][0]["views"] == 1200 and out["videos"][1]["views"] is None
    assert out["keywords"][0] == {"keyword": "kaffee", "count": 2}
    with pytest.raises(StudioError):
        trends.youtube_trends("Deutschland")
    st = trends.status()["platforms"]
    assert st["tiktok"]["available"] is False and "Keine offizielle" in st["tiktok"]["note"]
