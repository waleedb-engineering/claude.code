"""Editor-Agent: Regel-Planer (Beispielsätze), Validierung, gleiche Speicherwege
wie der Editor, Rückgängig, Bestätigungen, Kostenfreigabe, LLM-Abwehr."""

import pytest

from clipforge.agent import planner
from clipforge.agent.tools import TOOLS, validate
from clipforge.studio.errors import StudioError
from studio_helpers import clear_env, make_client, wait_task

SCRIPT = ("Hallo und willkommen zu diesem Video. Heute zeige ich dir drei Tricks. "
          "Der erste Trick spart Zeit. Der zweite Trick spart Geld. Folge für mehr.")


def test_rule_planner_understands_examples():
    steps, notes = planner.rule_plan("Nimm Clip 3, entferne die ersten vier Sekunden", "stream", 5)
    assert steps == [{"tool": "trim_clip", "args": {"clip": 3, "cut_start": 4.0}}]
    steps, _ = planner.rule_plan("Analysiere diesen dreistündigen Stream und erstelle fünf TikToks "
                                 "aus den lustigsten Momenten.", "stream", 0)
    assert steps[0] == {"tool": "find_highlights", "args": {"count": 5, "focus": "funny"}}
    steps, notes = planner.rule_plan("Füge animierte gelbe Untertitel hinzu.", "project", 4)
    assert {"tool": "change_caption_style", "args": {"style": "karaoke"}} in steps
    assert {"tool": "set_caption_appearance", "args": {"color": "gelb"}} in steps   # seit Final: echte Farbe
    steps, notes = planner.rule_plan("Zoome beim Schreien auf mein Gesicht.", "project", 4)
    assert steps[0]["tool"] == "zoom_scene" and steps[0]["args"]["focus"] == "face"
    steps, notes = planner.rule_plan("Verfolge die Person mit der Kamera", "project", 4)
    assert steps == [] and any("Tracking" in n for n in notes)
    steps, _ = planner.rule_plan("Erstelle aus dem Video drei Versionen mit unterschiedlichen Hooks.", "project", 4)
    assert steps == [{"tool": "generate_hook_variants", "args": {"count": 3}}]
    steps, _ = planner.rule_plan("Entferne langweilige Pausen, aber lass die Pointe vollständig.", "project", 4)
    assert {"tool": "remove_silence", "args": {}} in steps
    steps, notes = planner.rule_plan("Mache den Schnitt dynamischer, ohne dass das Video hektisch wirkt.", "project", 4)
    assert any(s["tool"] == "add_transition" for s in steps) and notes
    steps, notes = planner.rule_plan("Erstelle eine deutsche Version mit synchronisierter Stimme.", "project", 4)
    assert steps == [{"tool": "translate_video", "args": {"target": "de", "mode": "dub", "engine": "argos"}}]
    assert any("Argos" in n for n in notes)              # seit Production-Runde: echtes Werkzeug
    steps, _ = planner.rule_plan("Setze Szene 4 an den Anfang", "project", 5)
    assert steps == [{"tool": "move_scene", "args": {"scene": 4, "to": 1}}]


def test_validation_rejects_bad_arguments():
    with pytest.raises(StudioError):
        validate(TOOLS["trim_scene"], {"scene": "drei"})
    with pytest.raises(StudioError):
        validate(TOOLS["change_caption_style"], {"style": "comic sans"})
    with pytest.raises(StudioError):
        validate(TOOLS["trim_scene"], {"scene": 1, "rm -rf": True})
    with pytest.raises(StudioError):
        validate(TOOLS["adjust_audio"], {"music_volume": 5})


def test_ollama_only_localhost(monkeypatch):
    monkeypatch.setenv("CLIPFORGE_OLLAMA_URL", "http://evil.example:11434")
    with pytest.raises(StudioError):
        planner.ollama_url()


def test_agent_edits_project_like_the_editor_and_can_undo(tmp_path, monkeypatch):
    client, app_module = make_client(str(tmp_path))
    try:
        r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT})
        pid = r.json()["project"]["id"]
        wait_task(client, r.json()["task_id"])
        before = client.get(f"/api/studio/projects/{pid}").json()["project"]
        n = len(before["scenes"])
        assert n >= 2
        msg = client.post(f"/api/studio/agent/project/{pid}", json={
            "message": f"Setze Szene {n} an den Anfang und füge animierte Untertitel hinzu"}).json()["message"]
        steps = msg["plan"]["steps"]
        assert [s["tool"] for s in steps] == ["move_scene", "change_caption_style"]
        assert msg["plan"]["status"] == "pending"
        # nichts passiert ohne Ausführung
        assert client.get(f"/api/studio/projects/{pid}").json()["project"]["version"] == before["version"]
        done = client.post(f"/api/studio/agent/project/{pid}/{msg['id']}/execute", json={}).json()["message"]
        assert done["plan"]["status"] == "done" and all(x["ok"] for x in done["plan"]["results"])
        after = client.get(f"/api/studio/projects/{pid}").json()["project"]
        assert after["scenes"][0]["text"] == before["scenes"][-1]["text"]
        assert after["captions"]["style"] == "karaoke"
        # derselbe Plan nicht zweimal
        assert client.post(f"/api/studio/agent/project/{pid}/{msg['id']}/execute", json={}).status_code == 409
        # Rückgängig über die normale Versionsgeschichte
        undone = client.post(f"/api/studio/agent/project/{pid}/undo").json()["project"]
        assert undone["scenes"][0]["text"] == before["scenes"][0]["text"]
        hist = client.get(f"/api/studio/agent/project/{pid}").json()["messages"]
        assert [m["role"] for m in hist][:2] == ["user", "assistant"] and "Rückgängig" in hist[-1]["text"]
        # Export verlangt Bestätigung
        exp = client.post(f"/api/studio/agent/project/{pid}", json={"message": "Exportiere das Video"}).json()["message"]
        assert exp["plan"]["needs_confirmation"]
        assert client.post(f"/api/studio/agent/project/{pid}/{exp['id']}/execute", json={}).status_code == 400
        # bezahlte Engine: Kostenfreigabe + Budget
        r = client.post(f"/api/studio/agent/project/{pid}", json={"message": "kürzer", "engine": "anthropic"})
        assert r.status_code == 402
        r = client.post(f"/api/studio/agent/project/{pid}", json={"message": "kürzer", "engine": "anthropic",
                                                                  "confirm_cost": True})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "budget_exceeded"
        # LLM schlägt ein nicht freigegebenes Werkzeug vor → abgewiesen
        monkeypatch.setattr(planner, "LLM_CALL", lambda e, s, u, t: [
            {"tool": "shell", "args": {"cmd": "rm -rf /"}}, {"tool": "delete_scene", "args": {"scene": 99}},
            {"tool": "change_caption_style", "args": {"style": "bold"}}])
        m = client.post(f"/api/studio/agent/project/{pid}", json={"message": "x", "engine": "ollama"}).json()["message"]
        assert [s["tool"] for s in m["plan"]["steps"]] == ["delete_scene", "change_caption_style"]
        assert any("nicht freigegeben" in n for n in m["notes"])
        res = client.post(f"/api/studio/agent/project/{pid}/{m['id']}/execute", json={}).json()["message"]
        assert res["plan"]["status"] == "partial" and "gibt es nicht" in res["plan"]["results"][0]["error"]
        eng = client.get("/api/studio/agent/engines").json()
        assert {e["id"] for e in eng["engines"]} == {"rules", "ollama", "anthropic", "openai", "gemini"}
    finally:
        clear_env()


def test_agent_drives_stream_workflow(tmp_path):
    from test_stream_intelligence import _stream, _twitch_chat
    client, app_module = make_client(str(tmp_path))
    try:
        sid = client.post("/api/studio/streams", json={"title": "S", "platform": "twitch",
                                                       "rights_confirmed": True}).json()["stream"]["id"]
        with open(_stream(str(tmp_path / "v.mp4")), "rb") as fh:
            client.post(f"/api/studio/streams/{sid}/video", files={"file": ("v.mp4", fh, "video/mp4")})
        client.post(f"/api/studio/streams/{sid}/chat", files={"file": ("c.json", _twitch_chat(), "application/json")})
        app_module.studio.streams.transcriber = None

        def say(text, confirm=False):
            m = client.post(f"/api/studio/agent/stream/{sid}", json={"message": text}).json()["message"]
            return client.post(f"/api/studio/agent/stream/{sid}/{m['id']}/execute",
                               json={"confirm": confirm}).json()["message"]
        r = say("Finde die zwei lustigsten Highlights in diesem Stream")
        assert r["plan"]["steps"][0]["args"] == {"count": 2, "focus": "funny"}
        wait_task(client, r["plan"]["results"][0]["task_id"])
        r = say("Nimm Clip 1 und entferne die ersten 2 Sekunden")
        assert r["plan"]["results"][0]["ok"], r
        a = client.get(f"/api/studio/streams/{sid}").json()["analysis"]["highlights"][0]
        assert a["edited"]
        m = client.post(f"/api/studio/agent/stream/{sid}", json={"message": "Rendere Clip 1"}).json()["message"]
        assert m["plan"]["needs_confirmation"] and m["plan"]["steps"][0]["args"]["clips"] == [1]
        r = client.post(f"/api/studio/agent/stream/{sid}/{m['id']}/execute", json={"confirm": True}).json()["message"]
        t = wait_task(client, r["plan"]["results"][0]["task_id"], 300)
        assert t["status"] == "succeeded" and t["result"]["job_id"]
    finally:
        clear_env()
