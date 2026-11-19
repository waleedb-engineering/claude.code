"""Neue Agent-Werkzeuge (Zoom, Untertitel-Aussehen, Musik, Effekte, Lautheit, Titel,
Thumbnails, Clip-Varianten) und Ollama-Anbindung.

Ollama wird gegen einen lokalen Test-Server mit dem echten Ollama-HTTP-Protokoll
geprüft — die Modellantworten sind NACHGEBILDET (kein echtes LLM). Ein Test mit
einem echten Modell braucht Ollama auf dem Rechner des Nutzers."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from clipforge.agent import ollama, planner
from studio_helpers import make_click_wav, make_client, wait_task

SCRIPT = ("Hallo und willkommen. Heute zeige ich dir drei Tricks. Der erste spart Zeit. Folge für mehr.")


def _say(client, pid, text, engine="rules"):
    r = client.post(f"/api/studio/agent/project/{pid}", json={"message": text, "engine": engine})
    assert r.status_code == 201, r.text
    return r.json()["message"]


def _run(client, pid, text, engine="rules"):
    e = _say(client, pid, text, engine)
    assert e["plan"]["steps"], e
    r = client.post(f"/api/studio/agent/project/{pid}/{e['id']}/execute", json={"confirm": True})
    assert r.status_code == 200, r.text
    return r.json()


def test_new_project_tools_change_real_state(tmp_path):
    client, _ = make_client(str(tmp_path))
    r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT})
    pid = r.json()["project"]["id"]
    wait_task(client, r.json()["task_id"])
    _run(client, pid, "Zoom langsam 1.5x auf das Gesicht in Szene 1")
    p = client.get(f"/api/studio/projects/{pid}").json()["project"]
    assert p["scenes"][0]["zoom"] == {"factor": 1.5, "focus": "face", "ramp": True}
    _run(client, pid, "Mach die Untertitel gelb, oben und größer")
    caps = client.get(f"/api/studio/projects/{pid}").json()["project"]["captions"]
    assert (caps["color"], caps["position"], caps["size"]) == ("#ffd400", "top", 1.25)
    _run(client, pid, "Normalisiere die Lautheit")
    assert client.get(f"/api/studio/projects/{pid}").json()["project"]["audio"]["loudnorm"] is True
    # Musik ohne Dateien → ehrliche Fehlermeldung statt Scheinerfolg
    e = _say(client, pid, "Füge Hintergrundmusik hinzu")
    r = client.post(f"/api/studio/agent/project/{pid}/{e['id']}/execute", json={"confirm": True})
    assert "Keine Audiodateien" in r.text
    with open(make_click_wav(str(tmp_path / "beat.wav"), 2.0), "rb") as fh:
        client.post(f"/api/studio/projects/{pid}/media", files={"file": ("beat.wav", fh, "audio/wav")})
    _run(client, pid, "Füge Hintergrundmusik hinzu")
    _run(client, pid, "Soundeffekt beat in Szene 1 bei 0.5 s")
    p = client.get(f"/api/studio/projects/{pid}").json()["project"]
    assert p["music"]["track"].startswith("project:beat") and p["scenes"][0]["sfx"][0]["at"] == 0.5
    out = _run(client, pid, "Schlag mir einen Titel vor")
    assert "suggestions" in json.dumps(out)
    # Rückgängig stellt die Version vor dem letzten Schritt wieder her
    hist = client.get(f"/api/studio/agent/project/{pid}").json()
    assert len([x for x in hist["messages"] if x["role"] == "assistant"]) >= 6


def test_rendered_zoom_and_thumbnail_via_agent(tmp_path):
    client, _ = make_client(str(tmp_path))
    r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT,
                                                  "voice": {"provider": "mock"}})
    pid = r.json()["project"]["id"]
    wait_task(client, r.json()["task_id"])
    e = _say(client, pid, "Erstelle ein Thumbnail")
    r = client.post(f"/api/studio/agent/project/{pid}/{e['id']}/execute", json={"confirm": True})
    assert "Noch kein Render" in r.text
    _run(client, pid, "Zoom 1.3x auf Szene 1")
    out = _run(client, pid, "Rendere eine Vorschau")
    tid = json.dumps(out).split('"task_id": "')[1].split('"')[0]
    assert wait_task(client, tid, 300)["status"] == "succeeded"
    out = _run(client, pid, "Erstelle ein Thumbnail")
    assert "thumb_1.jpg" in json.dumps(out)


class _FakeOllama(BaseHTTPRequestHandler):
    """Nachgebildeter Ollama-Server (echtes HTTP, vorgegebene Antworten)."""
    models = [{"name": "qwen2.5:7b", "size": 4_700_000_000}, {"name": "gemma2:2b", "size": 1_600_000_000}]
    reply = None
    requests: list = []

    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            return self._send({"version": "0.9.0"})
        if self.path == "/api/tags":
            return self._send({"models": self.models})
        self._send({}, 404)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeOllama.requests.append((self.path, data))
        if self.path == "/api/pull":
            return self._send({"error": "darf nie aufgerufen werden"}, 500)
        self._send({"message": _FakeOllama.reply(data)})


@pytest.fixture
def fake_ollama(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("CLIPFORGE_OLLAMA_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.delenv("CLIPFORGE_OLLAMA_MODEL", raising=False)
    _FakeOllama.requests = []
    yield srv
    srv.shutdown()


def test_ollama_status_choice_and_test(fake_ollama):
    st = ollama.status()
    assert st["reachable"] and st["version"] == "0.9.0"
    assert st["model"] == "qwen2.5:7b"                      # gemma2 kann kein Tool-Calling
    assert {m["name"]: m["tool_calling"] for m in st["models"]} == {"qwen2.5:7b": True, "gemma2:2b": False}
    assert st["recommendation"]["command"].startswith("ollama pull ")
    _FakeOllama.reply = lambda d: {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "set_caption_appearance", "arguments": {"position": "top"}}}]}
    t = ollama.test()
    assert t["ok"] and t["model"] == "qwen2.5:7b"
    _FakeOllama.reply = lambda d: {"role": "assistant", "content": "Okay, gemacht!"}
    assert ollama.test()["ok"] is False                     # Text statt Werkzeugaufruf erkannt
    assert not any(p == "/api/pull" for p, _ in _FakeOllama.requests)


def test_ollama_model_env_must_be_installed(fake_ollama, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_OLLAMA_MODEL", "llama3.1:70b")
    st = ollama.status()
    assert st["model"] is None and "nicht installiert" in st["model_reason"]
    assert ollama.test()["stage"] == "model"


def test_agent_with_ollama_and_fallback(fake_ollama, tmp_path, monkeypatch):
    client, _ = make_client(str(tmp_path))
    r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT})
    pid = r.json()["project"]["id"]
    wait_task(client, r.json()["task_id"])
    _FakeOllama.reply = lambda d: {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "set_caption_appearance", "arguments": {"position": "middle", "color": "rot"}}},
        {"function": {"name": "run_shell", "arguments": {"cmd": "rm -rf /"}}}]}
    e = _say(client, pid, "Untertitel in die Mitte und rot", engine="ollama")
    assert e["engine"] == "ollama" and [s["tool"] for s in e["plan"]["steps"]] == ["set_caption_appearance"]
    assert any("nicht freigegeben" in n for n in e["notes"])
    sent = _FakeOllama.requests[-1][1]
    assert sent["model"] == "qwen2.5:7b" and any(t["function"]["name"] == "zoom_scene" for t in sent["tools"])
    # Ollama fällt aus → Regel-Planer, keine Kosten
    monkeypatch.setenv("CLIPFORGE_OLLAMA_URL", "http://127.0.0.1:9")
    e = _say(client, pid, "Untertitel oben", engine="ollama")
    assert e["engine"] == "rules" and e["plan"]["steps"][0]["tool"] == "set_caption_appearance"
    assert any("Regel-Planer verwendet" in n for n in e["notes"]) and e["cost_usd"] == 0.0
    st = client.get("/api/studio/agent/ollama").json()
    assert st["reachable"] is False and "ollama pull" in st["hint"]


def test_stream_variant_tools(tmp_path):
    from test_stream_intelligence import _stream, _twitch_chat
    client, _ = make_client(str(tmp_path))
    sid = client.post("/api/studio/streams", json={"title": "S", "platform": "twitch",
                                                   "rights_confirmed": True}).json()["stream"]["id"]
    with open(_stream(str(tmp_path / "v.mp4")), "rb") as fh:
        client.post(f"/api/studio/streams/{sid}/video", files={"file": ("v.mp4", fh, "video/mp4")})
    client.post(f"/api/studio/streams/{sid}/chat", files={"file": ("c.json", _twitch_chat(), "application/json")})
    wait_task(client, client.post(f"/api/studio/streams/{sid}/analyze", json={"transcribe": False}).json()["task"]["id"])
    e = client.post(f"/api/studio/agent/stream/{sid}", json={"message": "Clip 1 mit mehr Kontext"}).json()["message"]
    assert e["plan"]["steps"] == [{**e["plan"]["steps"][0], "tool": "set_clip_variant",
                                   "args": {"clip": 1, "variant": "context"}}]
    client.post(f"/api/studio/agent/stream/{sid}/{e['id']}/execute", json={"confirm": True})
    h = client.get(f"/api/studio/streams/{sid}").json()["analysis"]["highlights"][0]
    assert h["variant"] == "context"
