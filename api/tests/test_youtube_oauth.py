"""Tests für das YouTube-OAuth-Flow-Skelett (Phase 2b).

Kein echter Google-Call, kein echter Upload, kein automatisches Browser-Öffnen.
Der Token-Exchange wird gemockt; das Keychain wird durch ein Fake-Modul
ersetzt (kein OS-Keychain, kein Netz). Getestet wird v. a.: State/CSRF-Schutz,
sichere Consent-URL (ohne client_secret), Callback-Speicherung nur über den
Token-Store, und dass NIE Tokens/Secrets in Antworten/Logs landen.

Läuft ohne pytest: `python tests/test_youtube_oauth.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import types
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.config import Settings
from clipforge.platforms import YouTubeAdapter
from clipforge.platforms.youtube_auth import YouTubeTokenStore
from clipforge.platforms.youtube_oauth import (
    OAuthClientSecretsMissing,
    OAuthDependencyMissing,
    OAuthExchangeFailed,
    OAuthStateStore,
    YouTubeOAuthConfig,
    YouTubeOAuthService,
    real_google_token_exchange,
    sanitize_token_payload,
)

_FFMPEG = shutil.which("ffmpeg") is not None

# Sentinel-Werte, die — falls sie je in einer Antwort auftauchen — ein Leak wären.
_SENTINEL_ACCESS = "ACCESS_TOKEN_SENTINEL_zzz"
_SENTINEL_REFRESH = "REFRESH_TOKEN_SENTINEL_zzz"
_SENTINEL_SECRET = "CLIENT_SECRET_SENTINEL_zzz"

# Value-Marker: NUR echte Secret-Werte, keine legitimen Feld-NAMEN
# (z. B. "client_secrets_configured" ist erlaubt). Reale client_secret-Leaks
# fängt zusätzlich der Sentinel `_SENTINEL_SECRET` über `forbidden` ab.
_VALUE_MARKERS = ("access_token", "refresh_token", "bearer ")


def _assert_no_secret_values(obj, *forbidden: str) -> None:
    blob = json.dumps(obj, ensure_ascii=False).lower()
    for m in _VALUE_MARKERS:
        assert m not in blob, f"möglicher Secret-Wert/-Key in Antwort: {m}"
    for f in forbidden:
        assert f.lower() not in blob, f"geleakter Wert in Antwort: {f}"


def _install_fake_keyring(token: dict | None = None,
                          service: str = "clipforge-youtube",
                          account: str = "default") -> dict:
    """Injiziert ein Fake-`keyring`-Modul (kein OS-Keychain, kein Netz)."""
    fake = types.ModuleType("keyring")
    store: dict = {}
    if token is not None:
        store[(service, account)] = json.dumps(token)

    class _Backend:  # nicht das 'fail'-Backend → gilt als verfügbar
        pass

    fake.get_keyring = lambda: _Backend()
    fake.get_password = lambda s, a: store.get((s, a))
    fake.set_password = lambda s, a, v: store.__setitem__((s, a), v)

    def _del(s, a):
        if (s, a) in store:
            del store[(s, a)]
        else:
            raise RuntimeError("no password")

    fake.delete_password = _del
    sys.modules["keyring"] = fake
    return store


def _write_client_secrets(with_secret: bool = True, path: str | None = None) -> str:
    section = {
        "client_id": "1234567890-abc.apps.googleusercontent.com",
        "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://127.0.0.1:8000/api/youtube/oauth/callback"],
    }
    if with_secret:
        section["client_secret"] = _SENTINEL_SECRET
    fh = (open(path, "w", encoding="utf-8") if path
          else tempfile.NamedTemporaryFile("w", suffix=".json", delete=False))
    name = path or fh.name
    json.dump({"installed": section}, fh)
    fh.close()
    return name


def _oauth_settings(enabled: bool = True, creds: str | None = None,
                    ttl: int = 600) -> Settings:
    return Settings(
        enable_youtube_oauth=enabled,
        youtube_client_secrets_file=creds,
        youtube_oauth_state_ttl_seconds=ttl,
    )


def _fake_exchanger(config, code, code_verifier):
    """Mock: liefert ein Fake-Token (inkl. client_secret, der beim Sanitizen
    verworfen werden MUSS). Verifier muss durchgereicht werden."""
    assert code and code_verifier, "code/verifier müssen ankommen"
    return {
        "access_token": _SENTINEL_ACCESS,
        "refresh_token": _SENTINEL_REFRESH,
        "token_type": "Bearer",
        "scope": "https://www.googleapis.com/auth/youtube.upload",
        "client_secret": _SENTINEL_SECRET,  # darf NICHT gespeichert werden
    }


def _service(settings: Settings, state_store: OAuthStateStore | None = None,
             exchanger=_fake_exchanger) -> YouTubeOAuthService:
    return YouTubeOAuthService(
        config=YouTubeOAuthConfig.from_settings(settings),
        token_store=YouTubeTokenStore(settings.youtube_token_service_name,
                                      settings.youtube_token_account),
        state_store=state_store or OAuthStateStore(),
        exchanger=exchanger,
    )


# ---------------------- State-Store (5,6,7) -------------------------------

def test_state_store_create_validate_consume():
    ss = OAuthStateStore()
    state, challenge, exp = ss.create(600)
    assert state and challenge and exp > 0
    assert ss.active_count() == 1
    entry = ss.consume(state)
    assert entry is not None and entry.code_verifier
    # nach Consume: entwertet
    assert ss.active_count() == 0


def test_state_store_reused_state_blocked():
    ss = OAuthStateStore()
    state, _, _ = ss.create(600)
    assert ss.consume(state) is not None
    assert ss.consume(state) is None  # Wiederverwendung geblockt


def test_state_store_expired_state_blocked():
    ss = OAuthStateStore()
    state, _, _ = ss.create(600)
    ss._states[state].expires_at = 0.0  # in die Vergangenheit zwingen
    assert ss.consume(state) is None


def test_state_store_unknown_and_none():
    ss = OAuthStateStore()
    assert ss.consume("nope") is None
    assert ss.consume(None) is None


# ---------------------- Sanitizing ----------------------------------------

def test_sanitize_rejects_invalid_payloads():
    assert sanitize_token_payload({}) is None
    assert sanitize_token_payload(None) is None
    assert sanitize_token_payload("str") is None
    assert sanitize_token_payload({"foo": "bar"}) is None
    assert sanitize_token_payload({"access_token": ""}) is None


def test_sanitize_keeps_whitelist_drops_secret():
    clean = sanitize_token_payload({
        "access_token": "A", "refresh_token": "R", "token_type": "Bearer",
        "scope": "s", "client_secret": _SENTINEL_SECRET, "weird": {"x": 1},
    })
    assert clean is not None
    assert "client_secret" not in clean
    assert "weird" not in clean
    assert clean["access_token"] == "A" and "stored_at" in clean


# ---------------------- Service: readiness / start ------------------------

def test_oauth_status_disabled_by_default():
    sys.modules.pop("keyring", None)
    svc = _service(_oauth_settings(enabled=False, creds=None))
    rd = svc.readiness()
    assert rd["oauth_enabled"] is False
    assert rd["can_start_auth"] is False
    assert rd["can_attempt_upload"] is False
    assert rd["no_secrets"] is True
    assert "oauth_disabled" in rd["blocked_reasons"]
    _assert_no_secret_values(rd)


def test_start_disabled_returns_blocked_no_url():
    sys.modules.pop("keyring", None)
    svc = _service(_oauth_settings(enabled=False, creds=None))
    res = svc.start_auth()
    assert res["state_created"] is False
    assert res["auth_url"] is None
    assert "oauth_disabled" in res["blocked_reasons"]


def test_start_enabled_without_secrets_blocked():
    _install_fake_keyring()
    try:
        svc = _service(_oauth_settings(enabled=True, creds=None))
        res = svc.start_auth()
        assert res["auth_url"] is None
        assert "client_secrets_missing" in res["blocked_reasons"]
    finally:
        sys.modules.pop("keyring", None)


def test_start_enabled_with_fake_secrets_creates_url_and_state():
    _install_fake_keyring()
    creds = _write_client_secrets(with_secret=True)
    try:
        svc = _service(_oauth_settings(enabled=True, creds=creds))
        res = svc.start_auth()
        assert res["state_created"] is True
        assert res["auth_url"] and res["expires_at"]
        q = parse_qs(urlparse(res["auth_url"]).query)
        # sichere, korrekte Consent-URL
        assert q["response_type"] == ["code"]
        assert q["access_type"] == ["offline"]
        assert q["code_challenge_method"] == ["S256"]
        assert q["code_challenge"] and q["state"]
        assert q["redirect_uri"] == ["http://127.0.0.1:8000/api/youtube/oauth/callback"]
        assert q["scope"] == ["https://www.googleapis.com/auth/youtube.upload"]
        # client_id gehört per Design in die URL; client_secret NIEMALS
        assert q["client_id"][0].endswith(".apps.googleusercontent.com")
        assert _SENTINEL_SECRET not in res["auth_url"]
        _assert_no_secret_values(res, _SENTINEL_SECRET)
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_start_blocked_when_token_store_unavailable():
    sys.modules.pop("keyring", None)  # kein keyring → Store nicht verfügbar
    creds = _write_client_secrets()
    try:
        svc = _service(_oauth_settings(enabled=True, creds=creds))
        res = svc.start_auth()
        assert res["auth_url"] is None
        assert "token_store_unavailable" in res["blocked_reasons"]
    finally:
        os.unlink(creds)


# ---------------------- Service: callback ---------------------------------

def test_callback_error_param_safe_response():
    svc = _service(_oauth_settings())
    res = svc.handle_callback(code=None, state=None, error="access_denied<script>")
    assert res["success"] is False and res["token_stored"] is False
    assert res["reason"] == "oauth_error"
    assert "<script>" not in res["message"]
    _assert_no_secret_values(res)


def test_callback_invalid_state_stores_nothing():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        svc = _service(_oauth_settings(enabled=True, creds=creds))
        res = svc.handle_callback(code="C", state="does-not-exist")
        assert res["reason"] == "invalid_state"
        assert res["token_stored"] is False
        assert store == {}  # nichts gespeichert
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_callback_reused_state_stores_nothing():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        svc = _service(_oauth_settings(enabled=True, creds=creds), state_store=ss)
        state, _, _ = ss.create(600)
        first = svc.handle_callback(code="C", state=state)
        assert first["token_stored"] is True
        store.clear()  # simulieren: prüfen, dass 2. Versuch NICHTS neu speichert
        second = svc.handle_callback(code="C", state=state)
        assert second["reason"] == "invalid_state"
        assert store == {}
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_callback_expired_state_stores_nothing():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        svc = _service(_oauth_settings(enabled=True, creds=creds), state_store=ss)
        state, _, _ = ss.create(600)
        ss._states[state].expires_at = 0.0
        res = svc.handle_callback(code="C", state=state)
        assert res["reason"] == "invalid_state"
        assert store == {}
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_callback_valid_state_stores_token_via_fake_keyring():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        svc = _service(_oauth_settings(enabled=True, creds=creds), state_store=ss)
        state, _, _ = ss.create(600)
        res = svc.handle_callback(code="AUTHCODE", state=state)
        assert res["success"] is True and res["token_stored"] is True
        # Token liegt im (Fake-)Keychain, aber NICHT in der Antwort
        assert store, "Token hätte gespeichert werden müssen"
        raw = next(iter(store.values()))
        assert _SENTINEL_REFRESH in raw  # gespeichert
        assert _SENTINEL_SECRET not in raw  # client_secret verworfen
        _assert_no_secret_values(res, _SENTINEL_ACCESS, _SENTINEL_REFRESH, _SENTINEL_SECRET)
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_callback_invalid_token_payload_stores_nothing():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        # Exchanger liefert unbrauchbare Payload → nichts speichern
        svc = _service(_oauth_settings(enabled=True, creds=creds),
                       state_store=ss, exchanger=lambda c, code, v: {"foo": "bar"})
        state, _, _ = ss.create(600)
        res = svc.handle_callback(code="C", state=state)
        assert res["reason"] == "invalid_token_payload"
        assert res["token_stored"] is False
        assert store == {}
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_callback_default_exchange_unavailable():
    _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        # KEIN Exchanger → sauber blockiert (Phase 3), kein Netzwerk-Call
        svc = _service(_oauth_settings(enabled=True, creds=creds),
                       state_store=ss, exchanger=None)
        state, _, _ = ss.create(600)
        res = svc.handle_callback(code="C", state=state)
        assert res["reason"] == "exchange_unavailable"
        assert res["token_stored"] is False
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_status_token_present_after_mock_callback():
    _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        svc = _service(_oauth_settings(enabled=True, creds=creds), state_store=ss)
        assert svc.readiness()["token_present"] is False
        state, _, _ = ss.create(600)
        assert svc.handle_callback(code="C", state=state)["token_stored"] is True
        rd = svc.readiness()
        assert rd["token_present"] is True
        assert rd["token_status"] == "authenticated"
        _assert_no_secret_values(rd, _SENTINEL_REFRESH)
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_path_traversal_in_secrets_path_not_leaked():
    # Pfad mit Traversal-Anteil → readiness zeigt nur den Basename, nie den Pfad
    weird = "../../../etc/clipforge_secret_file.json"
    cfg = YouTubeOAuthConfig(
        client_secrets_path=weird,
        redirect_uri="http://127.0.0.1:8000/api/youtube/oauth/callback",
        scopes=("https://www.googleapis.com/auth/youtube.upload",),
        enabled=True, state_ttl_seconds=600,
    )
    assert cfg.client_secrets_basename() == "clipforge_secret_file.json"
    sys.modules.pop("keyring", None)
    svc = YouTubeOAuthService(cfg, YouTubeTokenStore("s", "a"), OAuthStateStore())
    rd = svc.readiness()
    blob = json.dumps(rd)
    assert "../" not in blob and "/etc/" not in blob


# ---------------------- Draft-Readiness nutzt OAuth-Status ----------------

def test_draft_readiness_uses_oauth_status():
    _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        adapter = YouTubeAdapter(Settings(
            enable_youtube_oauth=True, youtube_client_secrets_file=creds))
        rd = adapter.overall_readiness()
        assert rd["can_start_auth"] is True
        assert rd["can_attempt_oauth"] is True
        assert rd["oauth_flow_status"] == "ready_to_start"
        assert rd["redirect_uri"].startswith("http://127.0.0.1")
        assert rd["can_attempt_upload"] is False
        assert rd["upload_status"] == "not_implemented"
        _assert_no_secret_values(rd, _SENTINEL_SECRET)
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


# ---------------------- API (TestClient) ----------------------------------

def _make_client():
    from clipforge.publishing import PLATFORMS  # noqa: F401 (ensure import ok)
    tmp = tempfile.mkdtemp(prefix="oauth_api_")
    jobs_dir = os.path.join(tmp, "jobs")
    os.makedirs(jobs_dir)
    os.environ["CLIPFORGE_JOBS_DIR"] = jobs_dir
    sys.modules.pop("app", None)
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app), tmp, app_module


def test_api_oauth_status_disabled_by_default():
    os.environ.pop("CLIPFORGE_ENABLE_YOUTUBE_OAUTH", None)
    os.environ.pop("CLIPFORGE_YOUTUBE_CLIENT_SECRETS", None)
    sys.modules.pop("keyring", None)
    client, tmp, _ = _make_client()
    try:
        r = client.get("/api/youtube/oauth/status")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["oauth_enabled"] is False
        assert body["can_start_auth"] is False
        assert body["can_attempt_upload"] is False
        assert body["no_secrets"] is True
        _assert_no_secret_values(body)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_api_oauth_start_disabled_blocked():
    os.environ.pop("CLIPFORGE_ENABLE_YOUTUBE_OAUTH", None)
    sys.modules.pop("keyring", None)
    client, tmp, _ = _make_client()
    try:
        r = client.post("/api/youtube/oauth/start")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["auth_url"] is None
        assert "oauth_disabled" in body["blocked_reasons"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_api_oauth_full_flow_start_then_callback_with_mock_exchange():
    creds = _write_client_secrets()
    _install_fake_keyring()
    os.environ["CLIPFORGE_ENABLE_YOUTUBE_OAUTH"] = "true"
    os.environ["CLIPFORGE_YOUTUBE_CLIENT_SECRETS"] = creds
    client, tmp, app_module = _make_client()
    # Token-Exchanger im App-Modul mocken (kein echter Google-Call).
    app_module._youtube_token_exchanger = (
        lambda config, code, verifier: {
            "access_token": _SENTINEL_ACCESS, "refresh_token": _SENTINEL_REFRESH,
            "token_type": "Bearer",
            "scope": "https://www.googleapis.com/auth/youtube.upload",
        })
    try:
        # start → Consent-URL + state
        r = client.post("/api/youtube/oauth/start")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state_created"] is True and body["auth_url"]
        _assert_no_secret_values(body, _SENTINEL_SECRET)
        state = parse_qs(urlparse(body["auth_url"]).query)["state"][0]

        # callback (valid state) → Token gespeichert, keine Secrets in Response
        r = client.get("/api/youtube/oauth/callback",
                       params={"code": "AUTHCODE", "state": state})
        assert r.status_code == 200, r.text
        cb = r.json()
        assert cb["success"] is True and cb["token_stored"] is True
        _assert_no_secret_values(cb, _SENTINEL_ACCESS, _SENTINEL_REFRESH)

        # status danach → token_present true, weiterhin kein Upload
        r = client.get("/api/youtube/oauth/status")
        st = r.json()
        assert st["token_present"] is True
        assert st["can_attempt_upload"] is False
        _assert_no_secret_values(st, _SENTINEL_REFRESH)

        # reused state → 400, nichts Neues gespeichert
        r = client.get("/api/youtube/oauth/callback",
                       params={"code": "AUTHCODE", "state": state})
        assert r.status_code == 400, r.text
    finally:
        os.environ.pop("CLIPFORGE_ENABLE_YOUTUBE_OAUTH", None)
        os.environ.pop("CLIPFORGE_YOUTUBE_CLIENT_SECRETS", None)
        os.unlink(creds)
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("keyring", None)
        sys.modules.pop("app", None)


def test_api_oauth_callback_invalid_state_is_400():
    os.environ["CLIPFORGE_ENABLE_YOUTUBE_OAUTH"] = "true"
    _install_fake_keyring()
    client, tmp, _ = _make_client()
    try:
        r = client.get("/api/youtube/oauth/callback",
                       params={"code": "x", "state": "invalid"})
        assert r.status_code == 400, r.text
    finally:
        os.environ.pop("CLIPFORGE_ENABLE_YOUTUBE_OAUTH", None)
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("keyring", None)
        sys.modules.pop("app", None)


def test_api_oauth_callback_error_param_is_safe_200():
    client, tmp, _ = _make_client()
    try:
        r = client.get("/api/youtube/oauth/callback",
                       params={"error": "access_denied"})
        assert r.status_code == 200, r.text
        assert r.json()["success"] is False
        _assert_no_secret_values(r.json())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


# ---------------------- Prompt 26: echter Token-Exchange ------------------
# Kein einziger echter Google-Call: entweder die Library-Absenz wird
# deterministisch erzwungen, oder der Exchange wird komplett gemockt.

import contextlib


@contextlib.contextmanager
def _block_google_library():
    """Erzwingt deterministisch einen ImportError für google_auth_oauthlib —
    unabhängig davon, ob die Library installiert ist (kein echter Call)."""
    saved = {k: sys.modules.get(k) for k in (
        "google_auth_oauthlib", "google_auth_oauthlib.flow")}
    sys.modules["google_auth_oauthlib"] = None  # → import wirft ImportError
    sys.modules["google_auth_oauthlib.flow"] = None
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _google_exchanger(**token):
    """Baut einen Fake-Exchanger, der `token` zurückgibt (kein echter Call)."""
    def _ex(config, code, code_verifier):
        assert code and code_verifier  # PKCE-Verifier muss ankommen
        return dict(token)
    return _ex


def test_real_exchange_dependency_missing_safe_error():
    creds = _write_client_secrets()
    try:
        cfg = YouTubeOAuthConfig.from_settings(_oauth_settings(enabled=True, creds=creds))
        with _block_google_library():
            try:
                real_google_token_exchange(cfg, "code", "verifier")
                assert False, "sollte OAuthDependencyMissing werfen"
            except OAuthDependencyMissing as e:
                assert e.reason == "exchange_dependency_missing"
    finally:
        os.unlink(creds)


def test_real_exchange_client_secrets_missing_safe_error():
    cfg = YouTubeOAuthConfig.from_settings(_oauth_settings(enabled=True, creds=None))
    try:
        real_google_token_exchange(cfg, "code", "verifier")
        assert False, "sollte OAuthClientSecretsMissing werfen"
    except OAuthClientSecretsMissing as e:
        assert e.reason == "client_secrets_missing"


def test_callback_dependency_missing_stores_nothing():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        # Prod-Exchanger (echte Library) — aber Library ist geblockt.
        svc = _service(_oauth_settings(enabled=True, creds=creds),
                       state_store=ss, exchanger=real_google_token_exchange)
        state, _, _ = ss.create(600)
        with _block_google_library():
            res = svc.handle_callback(code="C", state=state)
        assert res["reason"] == "exchange_dependency_missing"
        assert res["token_stored"] is False and store == {}
        _assert_no_secret_values(res)
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_exchange_success_stores_token_and_drops_client_secret_and_id_token():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        ex = _google_exchanger(
            access_token=_SENTINEL_ACCESS, refresh_token=_SENTINEL_REFRESH,
            token_uri="https://oauth2.googleapis.com/token", client_id="cid",
            client_secret=_SENTINEL_SECRET,  # muss verworfen werden
            id_token="ID_TOKEN_SENTINEL",    # muss verworfen werden
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
        svc = _service(_oauth_settings(enabled=True, creds=creds),
                       state_store=ss, exchanger=ex)
        state, _, _ = ss.create(600)
        res = svc.handle_callback(code="C", state=state)
        assert res["success"] is True and res["token_stored"] is True
        assert res["token_status"] == "authenticated"
        raw = next(iter(store.values()))
        keys = set(json.loads(raw).keys())
        assert "client_secret" not in keys and "id_token" not in keys
        assert {"access_token", "refresh_token", "token_uri", "scopes"} <= keys
        _assert_no_secret_values(res, _SENTINEL_ACCESS, _SENTINEL_REFRESH,
                                 _SENTINEL_SECRET, "ID_TOKEN_SENTINEL")
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_exchange_without_refresh_token_warns_but_stores():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        ex = _google_exchanger(
            access_token=_SENTINEL_ACCESS,
            scope="https://www.googleapis.com/auth/youtube.upload")
        svc = _service(_oauth_settings(enabled=True, creds=creds),
                       state_store=ss, exchanger=ex)
        state, _, _ = ss.create(600)
        res = svc.handle_callback(code="C", state=state)
        assert res["success"] is True and res["token_stored"] is True
        assert "no_refresh_token" in res["warnings"]
        assert store  # gespeichert
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_exchange_wrong_scope_blocks_and_stores_nothing():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        ex = _google_exchanger(
            access_token=_SENTINEL_ACCESS,
            scopes=["https://www.googleapis.com/auth/drive"])  # kein Upload-Scope
        svc = _service(_oauth_settings(enabled=True, creds=creds),
                       state_store=ss, exchanger=ex)
        state, _, _ = ss.create(600)
        res = svc.handle_callback(code="C", state=state)
        assert res["reason"] == "invalid_scope"
        assert res["token_stored"] is False and store == {}
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_exchange_missing_access_token_blocks():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()
        ex = _google_exchanger(  # nur refresh_token, kein access_token
            refresh_token=_SENTINEL_REFRESH,
            scope="https://www.googleapis.com/auth/youtube.upload")
        svc = _service(_oauth_settings(enabled=True, creds=creds),
                       state_store=ss, exchanger=ex)
        state, _, _ = ss.create(600)
        res = svc.handle_callback(code="C", state=state)
        assert res["reason"] == "invalid_token_payload"
        assert store == {}
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_exchange_google_error_no_token_stored():
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()

        def _boom(config, code, verifier):
            raise OAuthExchangeFailed()

        svc = _service(_oauth_settings(enabled=True, creds=creds),
                       state_store=ss, exchanger=_boom)
        state, _, _ = ss.create(600)
        res = svc.handle_callback(code="C", state=state)
        assert res["reason"] == "exchange_failed"
        assert res["token_stored"] is False and store == {}
        _assert_no_secret_values(res)
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_exchange_raw_exception_is_sanitized():
    """Eine rohe Exception aus dem Exchanger darf NIE mit Details durchschlagen."""
    store = _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        ss = OAuthStateStore()

        def _leak(config, code, verifier):
            raise RuntimeError(f"boom {_SENTINEL_SECRET} {code}")

        svc = _service(_oauth_settings(enabled=True, creds=creds),
                       state_store=ss, exchanger=_leak)
        state, _, _ = ss.create(600)
        res = svc.handle_callback(code="SECRETCODE", state=state)
        assert res["reason"] == "exchange_failed"
        assert res["token_stored"] is False and store == {}
        _assert_no_secret_values(res, _SENTINEL_SECRET, "SECRETCODE")
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_sanitize_drops_id_token_keeps_token_uri_and_scopes():
    clean = sanitize_token_payload({
        "access_token": "A", "refresh_token": "R",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid", "client_secret": _SENTINEL_SECRET,
        "id_token": "IDT", "scopes": ["s1", "s2"],
    })
    assert clean is not None
    assert "id_token" not in clean and "client_secret" not in clean
    assert clean["token_uri"].endswith("/token")
    assert clean["scopes"] == ["s1", "s2"]


def test_logout_removes_token_and_readiness_false():
    _install_fake_keyring()
    creds = _write_client_secrets()
    try:
        settings = _oauth_settings(enabled=True, creds=creds)
        ss = OAuthStateStore()
        svc = _service(settings, state_store=ss)  # default _fake_exchanger
        state, _, _ = ss.create(600)
        assert svc.handle_callback(code="C", state=state)["token_stored"] is True
        assert svc.readiness()["token_present"] is True
        # Logout über den Adapter (nutzt denselben TokenStore).
        adapter = YouTubeAdapter(Settings(
            enable_youtube_oauth=True, youtube_client_secrets_file=creds))
        assert adapter.logout()["deleted"] is True
        assert svc.readiness()["token_present"] is False
        assert svc.readiness()["token_status"] == "not_authenticated"
    finally:
        sys.modules.pop("keyring", None)
        os.unlink(creds)


def test_api_callback_dependency_missing_is_safe_200():
    creds = _write_client_secrets()
    _install_fake_keyring()
    os.environ["CLIPFORGE_ENABLE_YOUTUBE_OAUTH"] = "true"
    os.environ["CLIPFORGE_YOUTUBE_CLIENT_SECRETS"] = creds
    client, tmp, app_module = _make_client()
    # Prod-Default-Exchanger (echte Library) beibehalten, aber Library blocken.
    try:
        r = client.post("/api/youtube/oauth/start")
        state = parse_qs(urlparse(r.json()["auth_url"]).query)["state"][0]
        with _block_google_library():
            r = client.get("/api/youtube/oauth/callback",
                           params={"code": "C", "state": state})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is False
        assert body["reason"] == "exchange_dependency_missing"
        assert body["token_stored"] is False
        _assert_no_secret_values(body)
    finally:
        os.environ.pop("CLIPFORGE_ENABLE_YOUTUBE_OAUTH", None)
        os.environ.pop("CLIPFORGE_YOUTUBE_CLIENT_SECRETS", None)
        os.unlink(creds)
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("keyring", None)
        sys.modules.pop("app", None)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
