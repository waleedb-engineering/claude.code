"""Verbundene Plattform-Konten (OAuth 2.0 mit PKCE) und TikTok-Upload.

TikTok: Upload in die **Entwürfe/Inbox** des Kontos (Content Posting API,
Scope `video.upload`). Die endgültige Veröffentlichung macht der Nutzer in
der TikTok-App — ClipForge veröffentlicht nicht selbst.

Tokens liegen lokal (`<studio>/accounts/<plattform>.json`, Rechte 0600); ist
CLIPFORGE_SECRET_KEY gesetzt (Online-Betrieb), verschlüsselt.

UNGETESTET gegen den echten Dienst: Die TikTok-Entwicklerdokumentation war
während der Entwicklung nicht erreichbar. Endpunkte und Felder folgen der
bekannten Content Posting API v2; alle Aufrufe sind gegen nachgebildete
Antworten getestet.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from .errors import StudioError
from .storage import read_json, studio_dir, write_json_atomic

PLATFORMS = {
    "tiktok": {
        "label": "TikTok",
        "authorize_url": "https://www.tiktok.com/v2/auth/authorize/",
        "token_url": "https://open.tiktokapis.com/v2/oauth/token/",
        "scopes": ["user.info.basic", "video.upload"],
        # Direktveröffentlichung braucht den freigeschalteten Scope video.publish
        "extra_scopes_env": [("CLIPFORGE_TIKTOK_DIRECT_POST", ["video.publish"]),
                             ("CLIPFORGE_TIKTOK_METRICS", ["video.list"])],
        "client_param": "client_key", "scope_sep": ",", "pkce": True, "token_auth": "form",
        "account_field": "open_id",
        "client_id_env": "TIKTOK_CLIENT_KEY",
        "client_secret_env": "TIKTOK_CLIENT_SECRET",
        "redirect_env": "CLIPFORGE_TIKTOK_REDIRECT_URI",
        "redirect_default": "http://127.0.0.1:8000/api/studio/accounts/tiktok/callback",
    },
    "instagram": {
        # Instagram API mit Instagram-Login (Business/Creator-Konto nötig)
        "label": "Instagram",
        "authorize_url": "https://www.instagram.com/oauth/authorize",
        "token_url": "https://api.instagram.com/oauth/access_token",
        "scopes": ["instagram_business_basic", "instagram_business_content_publish",
                   "instagram_business_manage_insights"],
        "client_param": "client_id", "scope_sep": ",", "pkce": False, "token_auth": "form",
        "account_field": "user_id",
        "client_id_env": "INSTAGRAM_APP_ID",
        "client_secret_env": "INSTAGRAM_APP_SECRET",
        "redirect_env": "CLIPFORGE_INSTAGRAM_REDIRECT_URI",
        # Meta verlangt HTTPS-Weiterleitungen → lokal z. B. über einen Tunnel
        "redirect_default": "https://localhost:8000/api/studio/accounts/instagram/callback",
    },
    "x": {
        "label": "X",
        "authorize_url": "https://x.com/i/oauth2/authorize",
        "token_url": "https://api.x.com/2/oauth2/token",
        "scopes": ["tweet.read", "tweet.write", "users.read", "media.write", "offline.access"],
        "client_param": "client_id", "scope_sep": " ", "pkce": True, "token_auth": "basic",
        "account_field": None,
        "client_id_env": "X_CLIENT_ID",
        "client_secret_env": "X_CLIENT_SECRET",
        "redirect_env": "CLIPFORGE_X_REDIRECT_URI",
        "redirect_default": "http://127.0.0.1:8000/api/studio/accounts/x/callback",
    },
}
STATE_TTL = 600
API = "https://open.tiktokapis.com/v2"
CHUNK = 10 * 1024 * 1024           # TikTok: 5–64 MB je Stück, letztes Stück darf größer sein
MAX_VIDEO = 4 * 1024 * 1024 * 1024


# ------------------------------------------------------------------- HTTP

def _http(method: str, url: str, headers: dict, body: bytes | None = None,
          timeout: float = 120.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — feste Hosts
            return resp.status, resp.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(64 * 1024)


HTTP = _http  # in Tests ersetzbar
SLEEP = time.sleep


def _json(raw: bytes) -> dict:
    try:
        data = json.loads(raw or b"{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


# ---------------------------------------------------------------- Ablage

def _dir() -> str:
    path = os.path.join(studio_dir(), "accounts")
    os.makedirs(path, exist_ok=True)
    return path


def _spec(platform: str) -> dict:
    if platform not in PLATFORMS:
        raise StudioError("platform_unknown",
                          f"Für '{platform}' gibt es keine Kontoverbindung "
                          f"(verfügbar: {', '.join(PLATFORMS)}).", 404)
    return PLATFORMS[platform]


def _token_path(platform: str) -> str:
    return os.path.join(_dir(), f"{platform}.json")


def _save_token(platform: str, token: dict) -> None:
    raw = json.dumps(token).encode("utf-8")
    if len(os.environ.get("CLIPFORGE_SECRET_KEY", "")) >= 32:
        from .credentials import _fernet
        blob = {"encrypted": _fernet().encrypt(raw).decode("ascii")}
    else:
        blob = {"plain": token}
    write_json_atomic(_token_path(platform), blob)
    try:
        os.chmod(_token_path(platform), 0o600)
    except OSError:
        pass


def _load_token(platform: str) -> dict | None:
    blob = read_json(_token_path(platform), None)
    if not isinstance(blob, dict):
        return None
    if "encrypted" in blob:
        try:
            from .credentials import _fernet
            return json.loads(_fernet().decrypt(blob["encrypted"].encode("ascii")))
        except Exception:  # noqa: BLE001 — falscher Server-Schlüssel → wie nicht verbunden
            return None
    token = blob.get("plain")
    if isinstance(token, dict) and "account" not in token and token.get("open_id"):
        token["account"] = token["open_id"]  # Altbestand vor der Verallgemeinerung
    return token


# ----------------------------------------------------------------- OAuth

def configured(platform: str) -> bool:
    spec = _spec(platform)
    return bool(os.environ.get(spec["client_id_env"]) and os.environ.get(spec["client_secret_env"]))


def scopes(platform: str) -> list[str]:
    spec = _spec(platform)
    out = list(spec["scopes"])
    for env, extra in spec.get("extra_scopes_env") or []:
        if os.environ.get(env) == "1":
            out += extra
    return out


def status(platform: str) -> dict:
    spec = _spec(platform)
    token = _load_token(platform)
    if not configured(platform):
        state = "not_configured"
    elif not token:
        state = "not_connected"
    elif token.get("refresh_expires_at", 0) and token["refresh_expires_at"] < time.time():
        state = "expired"
    else:
        state = "connected"
    granted = str((token or {}).get("scope") or "").replace(",", " ").split()
    return {"platform": platform, "label": spec["label"], "state": state,
            "scopes": scopes(platform), "granted_scopes": granted if state == "connected" else [],
            "requires_env": [spec["client_id_env"], spec["client_secret_env"]],
            "account": (token or {}).get("account") if state == "connected" else None,
            "live_verified": False}


def has_scope(platform: str, scope: str) -> bool:
    token = _load_token(platform) or {}
    return scope in str(token.get("scope") or "").replace(",", " ").split()


def _redirect(spec: dict) -> str:
    return os.environ.get(spec["redirect_env"]) or spec["redirect_default"]


def start(platform: str) -> dict:
    spec = _spec(platform)
    if not configured(platform):
        raise StudioError("platform_not_configured",
                          f"Für {spec['label']} fehlen {spec['client_id_env']} und "
                          f"{spec['client_secret_env']} (eigene Entwickler-App nötig).", 409)
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)[:96]
    pending = read_json(os.path.join(_dir(), "pending.json"), {}) or {}
    pending = {k: v for k, v in pending.items() if v.get("expires", 0) > time.time()}
    pending[state] = {"platform": platform, "verifier": verifier, "expires": time.time() + STATE_TTL}
    write_json_atomic(os.path.join(_dir(), "pending.json"), pending)
    params = {spec["client_param"]: os.environ[spec["client_id_env"]], "response_type": "code",
              "scope": spec["scope_sep"].join(scopes(platform)), "redirect_uri": _redirect(spec),
              "state": state}
    if spec["pkce"]:
        params["code_challenge"] = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        params["code_challenge_method"] = "S256"
    return {"auth_url": f"{spec['authorize_url']}?{urllib.parse.urlencode(params)}",
            "expires_in": STATE_TTL}


def _client_form(spec: dict) -> dict:
    """Client-Angaben im Formular (TikTok/Instagram) — X nutzt Basic-Auth."""
    if spec["token_auth"] == "basic":
        return {"client_id": os.environ.get(spec["client_id_env"], "")}
    return {spec["client_param"]: os.environ.get(spec["client_id_env"], ""),
            "client_secret": os.environ.get(spec["client_secret_env"], "")}


def callback(platform: str, code: str | None, state: str | None, error: str | None = None) -> dict:
    spec = _spec(platform)
    pending = read_json(os.path.join(_dir(), "pending.json"), {}) or {}
    entry = pending.pop(state or "", None)
    write_json_atomic(os.path.join(_dir(), "pending.json"), pending)
    if error:
        raise StudioError("oauth_denied", f"{spec['label']} hat die Verbindung abgelehnt ({error[:60]}).")
    if not entry or entry["platform"] != platform or entry["expires"] < time.time():
        raise StudioError("oauth_state_invalid", "Die Anmeldung ist abgelaufen oder ungültig. Bitte neu starten.")
    if not code:
        raise StudioError("oauth_code_missing", "Die Plattform hat keinen Code geliefert.")
    form = {**_client_form(spec), "code": code, "grant_type": "authorization_code",
            "redirect_uri": _redirect(spec)}
    if spec["pkce"]:
        form["code_verifier"] = entry["verifier"]
    token = _token_request(spec, form)
    if platform == "instagram":
        token = _instagram_long_lived(token)
    if not token.get("scope"):
        token["scope"] = spec["scope_sep"].join(scopes(platform))
    _save_token(platform, token)
    return status(platform)


def _token_request(spec: dict, form: dict) -> dict:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if spec["token_auth"] == "basic":
        pair = f"{os.environ.get(spec['client_id_env'], '')}:{os.environ.get(spec['client_secret_env'], '')}"
        headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
    try:
        code, raw = HTTP("POST", spec["token_url"], headers, urllib.parse.urlencode(form).encode())
    except Exception as exc:  # noqa: BLE001
        raise StudioError("oauth_failed", f"Token-Anfrage fehlgeschlagen ({type(exc).__name__}).", 502) from None
    data = _json(raw)
    if code >= 400 or not data.get("access_token"):
        raise StudioError("oauth_failed", f"Token-Anfrage abgelehnt (HTTP {code}).", 502)
    now = time.time()
    field = spec.get("account_field")
    return {"access_token": data["access_token"], "refresh_token": data.get("refresh_token"),
            "account": str(data.get(field)) if field and data.get(field) else None,
            "scope": data.get("scope") if isinstance(data.get("scope"), str) else
            ",".join(data.get("permissions") or []) or None,
            "expires_at": now + float(data.get("expires_in") or 3600),
            # 0 = Anbieter nennt keine Laufzeit (z. B. X) → nicht als abgelaufen werten
            "refresh_expires_at": (now + float(data["refresh_expires_in"])
                                   if data.get("refresh_expires_in") else 0)}


IG_GRAPH = "https://graph.instagram.com"


def _instagram_long_lived(token: dict) -> dict:
    """Kurzlebiges Instagram-Token (1 h) gegen ein 60-Tage-Token tauschen."""
    q = urllib.parse.urlencode({"grant_type": "ig_exchange_token",
                                "client_secret": os.environ.get("INSTAGRAM_APP_SECRET", ""),
                                "access_token": token["access_token"]})
    code, raw = HTTP("GET", f"{IG_GRAPH}/access_token?{q}", {}, None)
    data = _json(raw)
    if code >= 400 or not data.get("access_token"):
        raise StudioError("oauth_failed", f"Instagram: Langzeit-Token abgelehnt (HTTP {code}).", 502)
    return {**token, "access_token": data["access_token"],
            "expires_at": time.time() + float(data.get("expires_in") or 5184000),
            "refresh_expires_at": 0}


def access_token(platform: str) -> str:
    """Gültiges Zugriffstoken; erneuert es bei Bedarf."""
    spec = _spec(platform)
    token = _load_token(platform)
    if not token:
        raise StudioError("platform_not_connected", f"{spec['label']} ist nicht verbunden.", 409)
    if platform == "instagram":
        # Langzeit-Token: ab 7 Tagen Restlaufzeit verlängern
        if token.get("expires_at", 0) > time.time() + 7 * 86400:
            return token["access_token"]
        if token.get("expires_at", 0) < time.time():
            raise StudioError("platform_reauth", "Instagram: bitte neu verbinden.", 409)
        q = urllib.parse.urlencode({"grant_type": "ig_refresh_token",
                                    "access_token": token["access_token"]})
        code, raw = HTTP("GET", f"{IG_GRAPH}/refresh_access_token?{q}", {}, None)
        data = _json(raw)
        if code < 400 and data.get("access_token"):
            token.update(access_token=data["access_token"],
                         expires_at=time.time() + float(data.get("expires_in") or 5184000))
            _save_token(platform, token)
        return token["access_token"]
    if token.get("expires_at", 0) > time.time() + 60:
        return token["access_token"]
    if not token.get("refresh_token"):
        raise StudioError("platform_reauth", f"{spec['label']}: bitte neu verbinden.", 409)
    form = {**_client_form(spec), "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"]}
    try:
        fresh = _token_request(spec, form)
    except StudioError as exc:
        raise StudioError("platform_reauth", f"{spec['label']}: bitte neu verbinden.", 409) from exc
    fresh["account"] = fresh.get("account") or token.get("account")
    fresh["scope"] = fresh.get("scope") or token.get("scope")
    fresh["refresh_token"] = fresh.get("refresh_token") or token.get("refresh_token")
    _save_token(platform, fresh)
    return fresh["access_token"]


def disconnect(platform: str) -> None:
    _spec(platform)
    try:
        os.remove(_token_path(platform))
    except FileNotFoundError:
        raise StudioError("platform_not_connected", "Kein verbundenes Konto.", 404) from None


# ------------------------------------------------------------ TikTok-Upload

def chunk_plan(size: int) -> list[tuple[int, int]]:
    """(start, ende) je Stück. Unter 5 MB: ein Stück; sonst 10-MB-Stücke,
    das letzte Stück nimmt den Rest auf (TikTok-Regel)."""
    if size <= 0 or size > MAX_VIDEO:
        raise StudioError("video_size_invalid", "Videogröße wird von TikTok nicht unterstützt.")
    if size < 5 * 1024 * 1024:
        return [(0, size - 1)]
    count = max(1, math.floor(size / CHUNK))
    out = [(i * CHUNK, (i + 1) * CHUNK - 1) for i in range(count - 1)]
    out.append(((count - 1) * CHUNK, size - 1))
    return out


def _api(method: str, path: str, token: str, body: dict) -> dict:
    try:
        code, raw = HTTP(method, f"{API}{path}", {"Authorization": f"Bearer {token}",
                                                  "Content-Type": "application/json; charset=UTF-8"},
                         json.dumps(body).encode())
    except Exception as exc:  # noqa: BLE001
        raise StudioError("tiktok_unreachable", f"TikTok nicht erreichbar ({type(exc).__name__}).", 502) from None
    data = _json(raw)
    err = (data.get("error") or {})
    if code >= 400 or (err.get("code") not in (None, "", "ok")):
        raise StudioError("tiktok_error",
                          f"TikTok meldet: {str(err.get('message') or err.get('code') or code)[:160]}",
                          502, {"http_status": code, "tiktok_code": err.get("code")})
    return data.get("data") or {}


def upload_to_inbox(video_path: str, progress=None) -> str:
    """Lädt ein Video in die TikTok-Entwürfe. Liefert die publish_id."""
    token = access_token("tiktok")
    size = os.path.getsize(video_path)
    plan = chunk_plan(size)
    data = _api("POST", "/post/publish/inbox/video/init/", token, {"source_info": {
        "source": "FILE_UPLOAD", "video_size": size,
        "chunk_size": plan[0][1] - plan[0][0] + 1, "total_chunk_count": len(plan)}})
    publish_id, upload_url = data.get("publish_id"), data.get("upload_url")
    if not publish_id or not str(upload_url or "").startswith("https://"):
        raise StudioError("tiktok_error", "TikTok lieferte keine Upload-Adresse.", 502)
    put_chunks(video_path, upload_url, plan, progress)
    return publish_id


def put_chunks(video_path: str, upload_url: str, plan: list[tuple[int, int]], progress=None) -> None:
    size = os.path.getsize(video_path)
    with open(video_path, "rb") as fh:
        for i, (start, end) in enumerate(plan):
            fh.seek(start)
            chunk = fh.read(end - start + 1)
            for attempt in range(4):  # vorübergehende Fehler wiederholen (nur dieses Stück)
                try:
                    code, _ = HTTP("PUT", upload_url, {
                        "Content-Type": "video/mp4", "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{size}"}, chunk)
                except Exception:  # noqa: BLE001
                    code = 0
                if code in (200, 201, 206):
                    break
                if code and 400 <= code < 500 and code not in (408, 429):
                    raise StudioError("tiktok_upload_failed", f"Upload abgelehnt (HTTP {code}).", 502)
                if attempt == 3:
                    raise StudioError("tiktok_upload_failed", "Upload nach mehreren Versuchen fehlgeschlagen.", 502)
                SLEEP(2 ** attempt)
            if progress:
                progress(f"TikTok-Upload {i + 1}/{len(plan)}")


STATUS_MAP = {
    "PROCESSING_UPLOAD": "uploading", "PROCESSING_DOWNLOAD": "uploading",
    "SEND_TO_USER_INBOX": "in_tiktok_drafts", "PUBLISH_COMPLETE": "published",
    "FAILED": "failed",
}


def fetch_status(publish_id: str) -> dict:
    data = _api("POST", "/post/publish/status/fetch/", access_token("tiktok"),
                {"publish_id": publish_id})
    raw = str(data.get("status") or "")
    ids = data.get("publicaly_available_post_id") or data.get("publicly_available_post_id") or []
    return {"tiktok_status": raw, "state": STATUS_MAP.get(raw, "unknown"),
            "fail_reason": data.get("fail_reason"),
            "post_id": str(ids[0]) if isinstance(ids, list) and ids else None}
