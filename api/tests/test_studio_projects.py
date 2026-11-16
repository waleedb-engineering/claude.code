"""Studio: Projektspeicher, Versionierung, Migration alter Dateien, Pfadsicherheit."""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from studio_helpers import clear_env, make_png, make_service, run_all

from clipforge.studio import storage
from clipforge.studio.errors import StudioError
from clipforge.studio.projects import ProjectStore, apply_patch, migrate, normalize_scene


def _code(fn) -> str:
    try:
        fn()
    except StudioError as exc:
        return exc.code
    return "no_error"


def _project(svc, **extra):
    return svc.create_project({"workflow": "script", "title": "T",
                               "script": "Eins zwei drei vier. Fünf sechs sieben acht.", **extra})


def test_ids_and_paths_are_validated():
    tmp = tempfile.mkdtemp(prefix="proj_")
    try:
        store = ProjectStore(tmp)
        for bad in ("../etc", "..", "a/b", "ABCDEF123456", "", "abc", "0123456789ab/..", "%2e%2e"):
            assert _code(lambda b=bad: store.load(b)) == "invalid_id", bad
        for parts in (("..", "x"), ("/etc/passwd",), ("a", "..", "..", "b"), ("",)):
            assert _code(lambda p=parts: storage.safe_child(tmp, *p)) == "unsafe_path", parts
        assert storage.safe_filename("../../evil.sh") == "evil.sh"
        assert storage.safe_filename("C:\\x\\..\\boot.ini") == "boot.ini"
        assert "/" not in storage.safe_filename("a/b/c d?.MP4")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_symlink_escape_is_blocked():
    tmp = tempfile.mkdtemp(prefix="proj_")
    try:
        inside, outside = os.path.join(tmp, "in"), os.path.join(tmp, "out")
        os.makedirs(inside)
        os.makedirs(outside)
        os.symlink(outside, os.path.join(inside, "link"))
        assert _code(lambda: storage.safe_child(inside, "link", "f.txt")) == "unsafe_path"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_version_conflict_and_snapshots():
    tmp = tempfile.mkdtemp(prefix="proj_")
    try:
        svc, _ = make_service(tmp)
        p = _project(svc)
        v1 = p["version"]
        a = svc.update_project(p["id"], {"title": "A"}, v1)
        assert a["version"] == v1 + 1 and a["title"] == "A"
        # zweiter Editor mit veralteter Version → Konflikt, nichts überschrieben
        try:
            svc.update_project(p["id"], {"title": "B"}, v1)
            raise AssertionError("Konflikt erwartet")
        except StudioError as exc:
            assert exc.code == "version_conflict" and exc.status == 409
            assert exc.details["current_version"] == v1 + 1
        assert svc.store.load(p["id"])["title"] == "A"
        assert _code(lambda: svc.update_project(p["id"], {"title": "C"}, None)) == "version_required"
        versions = svc.store.versions(p["id"])
        assert [v["version"] for v in versions][0] == v1
        restored = svc.store.restore_version(p["id"], v1)
        assert restored["title"] == "T" and restored["version"] == v1 + 2
        assert _code(lambda: svc.store.restore_version(p["id"], 999)) == "version_not_found"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_atomic_write_leaves_no_partial_file():
    tmp = tempfile.mkdtemp(prefix="proj_")
    try:
        path = os.path.join(tmp, "x", "data.json")
        storage.write_json_atomic(path, {"a": 1})

        class Boom:
            pass
        try:
            storage.write_json_atomic(path, {"a": Boom()})  # nicht serialisierbar
        except TypeError:
            pass
        assert storage.read_json(path) == {"a": 1}  # alte Datei intakt
        assert os.listdir(os.path.dirname(path)) == ["data.json"]  # keine .tmp-Reste
        assert storage.read_json(os.path.join(tmp, "missing.json"), "dflt") == "dflt"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_old_and_broken_project_files_still_load():
    tmp = tempfile.mkdtemp(prefix="proj_")
    try:
        store = ProjectStore(tmp)
        pid = "0123456789ab"
        os.makedirs(os.path.join(store.base, pid))
        # sehr altes Format: nur Titel + Szenen als einfache Texte/Fremdfelder
        with open(os.path.join(store.base, pid, "project.json"), "w", encoding="utf-8") as fh:
            json.dump({"title": "Alt", "workflow": "gibt_es_nicht", "aspect_ratio": "21:9",
                       "scenes": [{"text": "Hallo", "unknown": 1,
                                   "visual": {"mode": "hologram", "media": "../../x.png"}},
                                  "kaputt", {"text": "Zwei", "duration": "abc"}],
                       "captions": "karaoke", "music": None, "budget_limit_usd": "viel",
                       "version": "x"}, fh)
        p = store.load(pid)
        assert p["id"] == pid and p["title"] == "Alt"
        assert p["workflow"] == "script" and p["aspect_ratio"] == "9:16"
        assert len(p["scenes"]) == 2 and p["scenes"][0]["visual"]["mode"] == "motion"
        assert "/" not in (p["scenes"][0]["visual"]["media"] or "")
        assert p["captions"]["style"] == "karaoke" and p["music"]["volume"] == 0.25
        assert p["budget_limit_usd"] == 0.0 and p["version"] == 0
        assert migrate(p) == migrate(migrate(p))  # idempotent
        saved = store.save(p)  # und wieder speicherbar
        assert saved["version"] == 1
        assert any(s["id"] == pid for s in store.list())
        # defekte Datei → sauberer Fehler statt Crash, Liste überspringt sie
        bad = "ba0123456789"
        os.makedirs(os.path.join(store.base, bad))
        with open(os.path.join(store.base, bad, "project.json"), "w") as fh:
            fh.write("{not json")
        assert _code(lambda: store.load(bad)) == "project_not_found"
        assert all(s["id"] != bad for s in store.list())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_scene_validation_and_media_references():
    tmp = tempfile.mkdtemp(prefix="proj_")
    try:
        svc, _ = make_service(tmp)
        p = _project(svc)
        pdir = svc.store.dir(p["id"])
        s = normalize_scene({"text": "x" * 5000, "duration": 999, "pause_after": -3,
                             "visual": {"mode": "static", "color": "red; rm -rf", "seed": "z"}})
        assert len(s["text"]) == 1200 and s["duration"] == 120.0 and s["pause_after"] == 0.0
        assert s["visual"]["color"] is None and s["visual"]["seed"] == 0
        missing = {"scenes": [{"text": "a", "visual": {"mode": "media", "media": "nope.png"}}]}
        assert _code(lambda: apply_patch(p, missing, pdir)) == "media_not_found"
        traversal = {"scenes": [{"text": "a", "visual": {"mode": "media",
                                                         "media": "../project.json"}}]}
        assert _code(lambda: apply_patch(p, traversal, pdir)) == "media_not_found"
        make_png(os.path.join(pdir, "media", "bild.png"))
        ok = apply_patch(p, {"scenes": [{"text": "a", "visual": {"mode": "media",
                                                                 "media": "bild.png"}}]}, pdir)
        assert ok["scenes"][0]["visual"]["media"] == "bild.png"
        dup = {"scenes": [{"id": "aaaaaaaaaaaa", "text": "a"}, {"id": "aaaaaaaaaaaa", "text": "b"}]}
        assert _code(lambda: apply_patch(p, dup, pdir)) == "validation_error"
        for patch in ({"aspect_ratio": "3:2"}, {"resolution": "8k"}, {"language": "fr"},
                      {"captions": {"style": "comic"}}, {"title": "  "},
                      {"voice": {"provider": "does_not_exist"}},
                      {"music": {"track": "library:../../etc/passwd"}}):
            assert _code(lambda pt=patch: apply_patch(p, pt, pdir)) in (
                "validation_error", "provider_unknown", "music_not_found"), patch
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_scene_operations_persist_and_reorder():
    tmp = tempfile.mkdtemp(prefix="proj_")
    try:
        svc, _ = make_service(tmp)
        p = _project(svc)
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        p = svc.store.load(p["id"])
        p = svc.scene_operation(p["id"], "add", p["version"], None, {"text": "Dritte Szene"})
        p = svc.scene_operation(p["id"], "add", p["version"], None, {"text": "Vierte Szene"})
        ids = [s["id"] for s in p["scenes"]]
        order = list(reversed(ids))
        p = svc.scene_operation(p["id"], "reorder", p["version"], None, {"order": order})
        assert [s["id"] for s in svc.store.load(p["id"])["scenes"]] == order  # von Platte
        assert _code(lambda: svc.scene_operation(p["id"], "reorder", p["version"], None,
                                                 {"order": order[:-1]})) == "validation_error"
        p = svc.scene_operation(p["id"], "duplicate", p["version"], order[0])
        assert len(p["scenes"]) == len(ids) + 1 and p["scenes"][1]["text"] == p["scenes"][0]["text"]
        assert p["scenes"][1]["id"] != p["scenes"][0]["id"]
        p = svc.scene_operation(p["id"], "update", p["version"], order[0],
                                {"text": "Neu", "voice_text": "Gesprochen", "duration": 4})
        first = svc.store.load(p["id"])["scenes"][0]
        assert (first["text"], first["voice_text"], first["duration"]) == ("Neu", "Gesprochen", 4.0)
        p = svc.scene_operation(p["id"], "move", p["version"], order[0], {"to": 2})
        assert p["scenes"][2]["id"] == order[0]
        p = svc.scene_operation(p["id"], "delete", p["version"], order[0])
        assert order[0] not in [s["id"] for s in p["scenes"]]
        assert _code(lambda: svc.scene_operation(p["id"], "delete", p["version"],
                                                 "ffffffffffff")) == "scene_not_found"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_duplicate_copies_media_and_resets_exports():
    tmp = tempfile.mkdtemp(prefix="proj_")
    try:
        svc, _ = make_service(tmp)
        p = _project(svc)
        make_png(os.path.join(svc.store.dir(p["id"]), "media", "bild.png"))
        svc.store.mutate(p["id"], lambda x: x["exports"].append({"job_id": "j", "render_id": "r"}))
        copy = svc.store.duplicate(p["id"])
        assert copy["id"] != p["id"] and copy["exports"] == []
        assert copy["lineage"]["parent_id"] == p["id"]
        assert os.path.isfile(os.path.join(svc.store.dir(copy["id"]), "media", "bild.png"))
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_all(globals())
