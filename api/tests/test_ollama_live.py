"""ECHTER Ollama-Integrationstest (keine nachgebildeten Antworten).

Läuft nur, wenn auf diesem Rechner Ollama erreichbar ist und ein Modell mit
Tool-Calling installiert ist (z. B. `ollama pull qwen2.5:7b`). Sonst wird der
Test als ÜBERSPRUNGEN gemeldet — mit Grund, nie als bestanden.
Lädt selbst nie Modelle herunter.

Lokal auf dem Mac:  cd api && python -m pytest tests/test_ollama_live.py -v -rs
"""

import json
import time

import pytest

from clipforge.agent import ollama, planner

STATUS = ollama.status(timeout=2.0)
pytestmark = pytest.mark.skipif(
    not (STATUS["reachable"] and STATUS["model"]),
    reason=("Ollama nicht erreichbar" if not STATUS["reachable"] else
            f"kein Tool-Calling-Modell installiert ({STATUS['model_reason']})") +
           " — extern blockiert, kein Erfolg")


def test_probe_tool_call_real_model():
    t0 = time.perf_counter()
    r = ollama.test()
    print(json.dumps({**r, "wall_s": round(time.perf_counter() - t0, 1)}, ensure_ascii=False))
    assert r["ok"], r


@pytest.mark.parametrize("message,expected_tool", [
    ("Setze die Untertitel nach oben und mache sie gelb.", "set_caption_appearance"),
    ("Mach die Musik leiser.", "adjust_audio"),
    ("Füge in Szene 1 einen Zoom auf das Gesicht ein.", "zoom_scene"),
])
def test_planner_with_real_model_returns_valid_tool_calls(message, expected_tool):
    from clipforge.agent.tools import TOOLS, validate
    state = {"title": "Test", "aspect_ratio": "9:16", "captions": "karaoke",
             "scenes": [{"index": 1, "kind": "hook", "text": "Hallo"}, {"index": 2, "kind": "body", "text": "Welt"}]}
    t0 = time.perf_counter()
    calls, text = planner.llm_plan("ollama", message, state, "project")
    dt = round(time.perf_counter() - t0, 1)
    print(f"{STATUS['model']}: {dt} s → {calls} {text[:80]}")
    assert calls, f"keine Werkzeugaufrufe (Antwort: {text[:200]})"
    for c in calls:
        assert c["tool"] in TOOLS, f"unbekanntes Werkzeug {c['tool']}"
        validate(TOOLS[c["tool"]], c["args"])             # JSON-Schema-konform
    assert any(c["tool"] == expected_tool for c in calls), calls
