"""Online-Betrieb mit Benutzerkonten (CLIPFORGE_AUTH=accounts)."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import time

from studio_helpers import wait_task, clear_env, make_client, run_all

from clipforge import auth

PW = "ein-langes-passwort-123"
SCRIPT = "Erster Satz hier. Zweiter Satz hier. Folge für mehr."
ENV = ("CLIPFORGE_AUTH", "CLIPFORGE_AUTH_DIR", "CLIPFORGE_COOKIE_SECURE", "CLIPFORGE_SECRET_KEY",
       "CLIPFORGE_RATE_LIMIT_PER_MIN", "CLIPFORGE_ENV_FILE", "OPENAI_API_KEY", "CLIPFORGE_TRUST_PROXY",
       "CLIPFORGE_WORKSPACES", "CLIPFORGE_REGISTRATION", "CLIPFORGE_SHARE_SERVER_KEYS")


def _client(tmp, **extra):
    auth.limiter.reset()
    client, app_module = make_client(
        tmp, CLIPFORGE_AUTH="accounts", CLIPFORGE_AUTH_DIR=os.path.join(tmp, "auth"),
        CLIPFORGE_COOKIE_SECURE="0", CLIPFORGE_SECRET_KEY="x" * 40,
        CLIPFORGE_ENV_FILE=os.path.join(tmp, ".env"), **extra)
    return client, app_module


def _login(client, user="walid", pw=PW):
    r = client.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"X-ClipForge-Token": r.json()["token"]}


def test_password_hashing():
    h = auth.hash_password(PW)
    assert h.startswith("scrypt$") and PW not in h
    assert auth.verify_password(PW, h) and not auth.verify_password(PW + "x", h)
    assert auth.hash_password(PW) != h                         # Salt
    assert not auth.verify_password(PW, "kaputt") and not auth.verify_password(PW, "md5$x$y$z$a$b")


def test_everything_requires_login_and_csrf():
    tmp = tempfile.mkdtemp(prefix="acc_")
    try:
        client, _ = _client(tmp)
        auth.create_user("walid", PW)
        assert client.get("/health").status_code == 200           # Healthcheck frei
        for method, path in (("get", "/api/studio/projects"), ("get", "/api/jobs"),
                             ("get", "/api/studio/credentials"), ("post", "/api/studio/projects"),
                             ("get", "/api/studio/projects/aaaaaaaaaaaa/renders/bbbbbbbbbbbb/file")):
            r = getattr(client, method)(path)
            assert r.status_code == 401 and r.json()["detail"]["code"] == "login_required", path
        s = client.get("/api/session")
        assert s.status_code == 401 and s.json()["mode"] == "accounts"
        headers = _login(client)
        cookie = client.cookies.get(auth.COOKIE)
        assert cookie and len(cookie) > 30
        assert client.get("/api/session").json()["user"] == "walid"
        assert client.get("/api/auth/me").json() == {"mode": "accounts", "user": "walid"}
        # Mutation ohne CSRF-Token wird abgewiesen, mit Token erlaubt
        r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "csrf_invalid"
        r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT},
                        headers={"X-ClipForge-Token": "falsch"})
        assert r.status_code == 403
        r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT},
                        headers=headers)
        assert r.status_code == 201
        # fremde Herkunft bleibt gesperrt, auch angemeldet
        r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT},
                        headers={**headers, "Origin": "https://evil.example"})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "origin_not_allowed"
        # Sitzungen liegen nur gehasht auf der Platte
        raw = open(os.path.join(tmp, "auth", "sessions.json")).read()
        assert cookie not in raw and PW not in open(os.path.join(tmp, "auth", "users.json")).read()
        assert os.name == "nt" or stat.S_IMODE(os.stat(os.path.join(tmp, "auth", "users.json")).st_mode) == 0o600
        # Abmelden beendet die Sitzung serverseitig
        assert client.post("/api/auth/logout", headers=headers).status_code == 200
        client.cookies.set(auth.COOKIE, cookie)                    # altes Cookie wiederverwenden
        assert client.get("/api/studio/projects").status_code == 401
    finally:
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)


def test_login_errors_are_uniform_and_rate_limited():
    tmp = tempfile.mkdtemp(prefix="acc_")
    try:
        client, _ = _client(tmp)
        auth.create_user("walid", PW)
        a = client.post("/api/auth/login", json={"username": "walid", "password": "falsch"})
        b = client.post("/api/auth/login", json={"username": "niemand", "password": "falsch"})
        assert a.status_code == b.status_code == 401
        assert a.json() == b.json()                                # kein Hinweis, ob es das Konto gibt
        for _ in range(4):  # zusammen mit oben: 5 Fehlversuche für "walid"
            client.post("/api/auth/login", json={"username": "walid", "password": "falsch"})
        r = client.post("/api/auth/login", json={"username": "walid", "password": PW})
        assert r.status_code == 429                                # auch richtiges Passwort gesperrt
        assert r.json()["detail"]["code"] == "rate_limited"
    finally:
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)


def test_general_rate_limit_and_session_expiry():
    tmp = tempfile.mkdtemp(prefix="acc_")
    try:
        client, _ = _client(tmp, CLIPFORGE_RATE_LIMIT_PER_MIN=5)
        auth.create_user("walid", PW)
        _login(client)
        codes = [client.get("/api/studio/projects").status_code for _ in range(7)]
        assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
        # abgelaufene Sitzung
        import json
        path = os.path.join(tmp, "auth", "sessions.json")
        data = json.load(open(path))
        for v in data.values():
            v["expires"] = time.time() - 1
        json.dump(data, open(path, "w"))
        auth.limiter.reset()
        assert client.get("/api/studio/projects").status_code == 401
    finally:
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)


def test_password_change_logs_out_everywhere_and_validates():
    tmp = tempfile.mkdtemp(prefix="acc_")
    try:
        client, _ = _client(tmp)
        auth.create_user("walid", PW)
        headers = _login(client)
        r = client.post("/api/auth/password", headers=headers,
                        json={"old_password": "falsch", "new_password": "neues-langes-passwort"})
        assert r.status_code == 403
        r = client.post("/api/auth/password", headers=headers,
                        json={"old_password": PW, "new_password": "kurz"})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "weak_password"
        r = client.post("/api/auth/password", headers=headers,
                        json={"old_password": PW, "new_password": "neues-langes-passwort"})
        assert r.status_code == 200
        assert client.get("/api/studio/projects").status_code == 401
        _login(client, pw="neues-langes-passwort")
        for bad in ("A", "mit leerzeichen", "x" * 41):
            try:
                auth.create_user(bad, PW)
                raise AssertionError(bad)
            except auth.AuthError as exc:
                assert exc.code == "invalid_username"
        try:
            auth.create_user("walid", PW)
            raise AssertionError("user_exists erwartet")
        except auth.AuthError as exc:
            assert exc.code == "user_exists"
    finally:
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)


def test_api_keys_are_stored_encrypted_in_account_mode():
    """Gemeinsamer Bereich (CLIPFORGE_WORKSPACES=shared, altes Verhalten)."""
    tmp = tempfile.mkdtemp(prefix="acc_")
    secret = "sk-sentinel-encrypted-key-123"
    try:
        client, _ = _client(tmp, CLIPFORGE_WORKSPACES="shared")
        auth.create_user("walid", PW)
        headers = _login(client)
        r = client.put("/api/studio/credentials/openai", json={"api_key": secret}, headers=headers)
        assert r.status_code == 200
        vault = os.path.join(tmp, "auth", "credentials.enc")
        assert secret.encode() not in open(vault, "rb").read()      # verschlüsselt
        assert not os.path.exists(os.path.join(tmp, ".env"))        # nicht im Klartext
        assert os.environ["OPENAI_API_KEY"] == secret                # sofort wirksam
        # Neustart: Schlüssel wird entschlüsselt geladen
        os.environ.pop("OPENAI_API_KEY")
        client, _ = _client(tmp, CLIPFORGE_WORKSPACES="shared")
        assert os.environ.get("OPENAI_API_KEY") == secret
        # falscher Server-Schlüssel → kein Start-Abbruch, aber nichts geladen
        os.environ.pop("OPENAI_API_KEY")
        client, _ = _client(tmp, CLIPFORGE_WORKSPACES="shared")
        os.environ["CLIPFORGE_SECRET_KEY"] = "y" * 40
        from clipforge.studio.credentials import load_vault_into_env
        from clipforge.studio.errors import StudioError
        try:
            load_vault_into_env()
            raise AssertionError("vault_unreadable erwartet")
        except StudioError as exc:
            assert exc.code == "vault_unreadable"
        # ohne Server-Schlüssel: klare Meldung statt Klartext-Fallback
        os.environ["CLIPFORGE_SECRET_KEY"] = "kurz"
        headers = _login(client)
        r = client.put("/api/studio/credentials/openai", json={"api_key": secret}, headers=headers)
        assert r.status_code == 503 and r.json()["detail"]["code"] == "secret_key_missing"
    finally:
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)


def test_local_mode_is_unchanged():
    tmp = tempfile.mkdtemp(prefix="acc_")
    try:
        client, _ = make_client(tmp)
        assert client.get("/api/studio/projects").status_code == 200   # lesen ohne Login
        assert client.get("/api/session").json()["mode"] == "local"
        assert client.post("/api/auth/login", json={"username": "a", "password": "b"}).status_code == 404
        assert client.get("/api/auth/me").json() == {"mode": "local", "user": None}
    finally:
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)


def test_cli_creates_users_without_echoing_the_password():
    import subprocess
    import sys
    tmp = tempfile.mkdtemp(prefix="acc_")
    try:
        env = {**os.environ, "CLIPFORGE_AUTH_DIR": tmp, "CLIPFORGE_NEW_PASSWORD": PW,
               "PYTHONPATH": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}
        r = subprocess.run([sys.executable, "-m", "clipforge.auth", "create-user", "Walid"],
                           env=env, capture_output=True, text=True)
        assert r.returncode == 0 and "walid" in r.stdout and PW not in r.stdout + r.stderr
        r = subprocess.run([sys.executable, "-m", "clipforge.auth", "list-users"], env=env,
                           capture_output=True, text=True)
        assert r.stdout.startswith("walid ")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_all(globals())


def test_per_user_workspaces_are_isolated():
    """Getrennte Bereiche: Projekte, Aufgaben, Jobs, Schlüssel, Vorlagen je Benutzer."""
    tmp = tempfile.mkdtemp(prefix="acc_")
    try:
        client, app_module = _client(tmp, OPENAI_API_KEY="sk-server-key-of-operator")
        auth.create_user("anna", PW)            # erstes Konto → admin
        auth.create_user("bert", PW)
        assert auth.user_role("anna") == "admin" and auth.user_role("bert") == "user"
        ha = _login(client, "anna")
        r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT},
                        headers=ha)
        assert r.status_code == 201, r.text
        pid = r.json()["project"]["id"]
        wait_task(client, r.json()["task_id"])
        tid = r.json()["task_id"]
        r = client.put("/api/studio/credentials/elevenlabs",
                       json={"api_key": "sk-anna-eleven-123"}, headers=ha)
        assert r.status_code == 200
        client.post("/api/studio/templates", json={"name": "Annas Stil"}, headers=ha)
        job = client.post(f"/api/studio/projects/{pid}/render", json={"mode": "final"}, headers=ha)
        wait_task(client, job.json()["task"]["id"])
        exp = client.post(f"/api/studio/projects/{pid}/export", json={}, headers=ha).json()
        assert os.path.isdir(os.path.join(tmp, "studio", "users", "anna", "projects", pid))
        creds = {c["provider"]: c["configured"] for c in
                 client.get("/api/studio/credentials").json()["credentials"]}
        assert creds["elevenlabs"] and creds["openai"]          # Admin darf Server-Schlüssel nutzen
        client.post("/api/auth/logout")

        hb = _login(client, "bert")
        assert client.get("/api/studio/projects").json()["projects"] == []
        assert client.get(f"/api/studio/projects/{pid}").status_code == 404
        assert client.get(f"/api/studio/tasks/{tid}").status_code == 404
        assert client.get(f"/api/jobs/{exp['job_id']}").status_code == 404
        assert exp["job_id"] not in [j["id"] for j in client.get("/api/jobs").json()["jobs"]]
        assert client.delete(f"/api/jobs/{exp['job_id']}", headers=hb).status_code == 404
        creds = {c["provider"]: c["configured"] for c in
                 client.get("/api/studio/credentials").json()["credentials"]}
        assert not creds["elevenlabs"] and not creds["openai"]  # weder Annas noch Server-Schlüssel
        names = [t["name"] for t in client.get("/api/studio/templates").json()["templates"]]
        assert "Annas Stil" not in names
        assert client.get("/api/admin/users").status_code == 403
        assert os.environ.get("ELEVENLABS_API_KEY") is None     # nie prozessweit gesetzt
        vault = os.path.join(tmp, "auth", "vaults", "anna.enc")
        assert b"sk-anna-eleven-123" not in open(vault, "rb").read()
        client.post("/api/auth/logout")

        ha = _login(client, "anna")
        assert client.get(f"/api/studio/projects/{pid}").status_code == 200
        users = client.get("/api/admin/users").json()["users"]
        assert {u["username"]: u["role"] for u in users} == {"anna": "admin", "bert": "user"}
        r = client.post("/api/admin/users/bert/password", json={"password": "neues-passwort-456"},
                        headers=ha)
        assert r.json()["must_change_password"] is True
        client.post("/api/auth/logout")
        hb = _login(client, "bert", "neues-passwort-456")
        r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT}, headers=hb)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "password_change_required"
        r = client.post("/api/auth/password", json={"old_password": "neues-passwort-456",
                                                    "new_password": "bert-eigenes-pw-789"}, headers=hb)
        assert r.status_code == 200
        hb = _login(client, "bert", "bert-eigenes-pw-789")
        assert client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT},
                           headers=hb).status_code == 201
        assert len(client.get("/api/auth/sessions").json()["sessions"]) >= 1
    finally:
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)


def test_registration_and_migration():
    tmp = tempfile.mkdtemp(prefix="acc_")
    try:
        client, _ = _client(tmp)
        assert client.post("/api/auth/register", json={"username": "neu", "password": PW}).status_code == 403
        client, _ = _client(tmp, CLIPFORGE_REGISTRATION="open")
        auth.create_user("chef", PW)
        r = client.post("/api/auth/register", json={"username": "neu", "password": PW})
        assert r.status_code == 201 and auth.user_role("neu") == "user"
        # Altbestand im gemeinsamen Ordner → einem Benutzer zuordnen
        os.makedirs(os.path.join(tmp, "studio", "projects", "abc123abc123"))
        jobs = os.path.join(tmp, "jobs", "j1")
        os.makedirs(jobs)
        with open(os.path.join(jobs, "job.json"), "w") as fh:
            fh.write('{"id": "j1", "owner": null}')
        from clipforge.studio.workspace import migrate_shared
        res = migrate_shared("chef", os.path.join(tmp, "jobs"))
        assert "projects" in res["moved"] and res["jobs_assigned"] == 1
        assert os.path.isdir(os.path.join(tmp, "studio", "users", "chef", "projects", "abc123abc123"))
        assert '"owner": "chef"' in open(os.path.join(jobs, "job.json")).read()
    finally:
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)
