"""Direkte Veröffentlichung: TikTok (Direct Post), Instagram Reels, X.

Grundsätze:
- Nichts geht ohne ausdrückliche Bestätigung des Nutzers raus (`confirm`).
  Geplante Posts brauchen eine eigene, gespeicherte Freigabe je Entwurf.
- Nur offizielle APIs. Abläufe nach der jeweiligen Entwicklerdokumentation
  (Stand der Recherche: 11/2026); gegen die echten Dienste UNGETESTET.
- Fehler werden ehrlich gemeldet; kein automatisches Wiederholen eines
  Posts nach einem unklaren Ausgang (sonst Doppel-Posts).

TikTok Direct Post: creator_info → video/init (post_info + FILE_UPLOAD) →
  PUT-Stücke → status/fetch. Ohne TikTok-App-Audit sind Posts nur privat
  (SELF_ONLY) möglich — das zeigt ClipForge an.
Instagram Reels: Container (media_type=REELS, upload_type=resumable) →
  Datei an rupload.facebook.com → status_code FINISHED → media_publish.
X: Medien-Upload v2 (initialize/append/finalize/status) → POST /2/tweets.
  Kostenpflichtig nach Nutzung; Kosten werden vor dem Post angezeigt.
"""

from __future__ import annotations

import json
import os
import uuid

from . import accounts
from .errors import StudioError

TT_API = "https://open.tiktokapis.com/v2"
IG_GRAPH = "https://graph.instagram.com"
IG_VERSION = os.environ.get("CLIPFORGE_IG_API_VERSION", "v24.0")
IG_RUPLOAD = "https://rupload.facebook.com/ig-api-upload"
X_API = "https://api.x.com/2"
X_CHUNK = 4 * 1024 * 1024
# Richtwert je Video-Post auf X (Post + Medienobjekt, Nutzungsabrechnung);
# echte Kosten zeigt die X-Entwicklerkonsole.
X_COST_PER_VIDEO_POST = float(os.environ.get("CLIPFORGE_X_COST_PER_POST_USD", "0.03"))
X_COST_PER_METRICS_READ = 0.005
TT_PRIVACY = ("PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY")


def _sleep(sec: float) -> None:
    accounts.SLEEP(sec)


def caption(title: str, description: str, hashtags: list[str], limit: int) -> str:
    tags = " ".join("#" + h.lstrip("#").replace(" ", "") for h in hashtags if h.strip())
    text = "\n\n".join(x for x in (title.strip(), description.strip(), tags) if x)
    return text[:limit]


# ------------------------------------------------------------------ TikTok
def tiktok_creator_info() -> dict:
    """Erlaubte Sichtbarkeiten, maximale Dauer usw. (vor jedem Direct Post Pflicht)."""
    if not accounts.has_scope("tiktok", "video.publish"):
        raise StudioError("scope_missing",
                          "Direktveröffentlichung braucht den TikTok-Scope video.publish "
                          "(in der App freischalten, CLIPFORGE_TIKTOK_DIRECT_POST=1 setzen, "
                          "Konto neu verbinden).", 409)
    data = accounts._api("POST", "/post/publish/creator_info/query/",
                         accounts.access_token("tiktok"), {})
    return {"nickname": data.get("creator_nickname"),
            "privacy_level_options": data.get("privacy_level_options") or [],
            "max_video_post_duration_sec": data.get("max_video_post_duration_sec"),
            "comment_disabled": data.get("comment_disabled"),
            "duet_disabled": data.get("duet_disabled"),
            "stitch_disabled": data.get("stitch_disabled"),
            "audited_app": os.environ.get("CLIPFORGE_TIKTOK_AUDITED") == "1"}


def tiktok_direct_post(video_path: str, *, title: str, privacy_level: str,
                       disable_comment: bool = False, disable_duet: bool = False,
                       disable_stitch: bool = False, progress=None) -> str:
    info = tiktok_creator_info()
    if privacy_level not in TT_PRIVACY or privacy_level not in info["privacy_level_options"]:
        raise StudioError("validation_error",
                          "Diese Sichtbarkeit erlaubt TikTok für dein Konto nicht "
                          f"(möglich: {', '.join(info['privacy_level_options']) or '–'}).")
    size = os.path.getsize(video_path)
    plan = accounts.chunk_plan(size)
    data = accounts._api("POST", "/post/publish/video/init/", accounts.access_token("tiktok"), {
        "post_info": {"title": title[:2200], "privacy_level": privacy_level,
                      "disable_comment": disable_comment, "disable_duet": disable_duet,
                      "disable_stitch": disable_stitch},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                        "chunk_size": plan[0][1] - plan[0][0] + 1,
                        "total_chunk_count": len(plan)}})
    publish_id, upload_url = data.get("publish_id"), data.get("upload_url")
    if not publish_id or not str(upload_url or "").startswith("https://"):
        raise StudioError("tiktok_error", "TikTok lieferte keine Upload-Adresse.", 502)
    accounts.put_chunks(video_path, upload_url, plan, progress)
    return publish_id


# --------------------------------------------------------------- Instagram
def _ig(method: str, path: str, params: dict | None = None, *, headers: dict | None = None,
        body: bytes | None = None, base: str | None = None) -> dict:
    import urllib.parse
    url = f"{base or IG_GRAPH}/{IG_VERSION}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        code, raw = accounts.HTTP(method, url, headers or {}, body)
    except Exception as exc:  # noqa: BLE001 — nie Token in die Meldung
        raise StudioError("instagram_unreachable", f"Instagram nicht erreichbar ({type(exc).__name__}).", 502) from None
    data = accounts._json(raw)
    if code >= 400 or data.get("error"):
        err = data.get("error") or {}
        raise StudioError("instagram_error",
                          f"Instagram meldet: {str(err.get('message') or code)[:160]}", 502,
                          {"http_status": code, "ig_code": err.get("code"),
                           "ig_subcode": err.get("error_subcode")})
    return data


def instagram_publish(video_path: str, *, text: str, share_to_feed: bool = True,
                      progress=None, max_wait: float = 600) -> str:
    """Lädt ein Reel hoch und veröffentlicht es. → Media-ID."""
    token = accounts.access_token("instagram")
    user = (accounts._load_token("instagram") or {}).get("account") or "me"
    auth = {"Authorization": f"Bearer {token}"}
    container = _ig("POST", f"/{user}/media", {"media_type": "REELS", "upload_type": "resumable",
                                               "caption": text[:2200],
                                               "share_to_feed": str(share_to_feed).lower()},
                    headers=auth)
    cid, uri = container.get("id"), container.get("uri")
    if not cid:
        raise StudioError("instagram_error", "Instagram lieferte keinen Container.", 502)
    size = os.path.getsize(video_path)
    with open(video_path, "rb") as fh:
        payload = fh.read()
    if progress:
        progress("Instagram: Video wird übertragen")
    up_url = uri if str(uri or "").startswith("https://rupload.facebook.com/") else \
        f"{IG_RUPLOAD}/{IG_VERSION}/{cid}"
    try:
        code, raw = accounts.HTTP("POST", up_url, {"Authorization": f"OAuth {token}",
                                                   "offset": "0", "file_size": str(size)},
                                  payload, timeout=600)
    except Exception as exc:  # noqa: BLE001
        raise StudioError("instagram_upload_failed", f"Upload fehlgeschlagen ({type(exc).__name__}).", 502) from None
    if code >= 400:
        raise StudioError("instagram_upload_failed", f"Upload abgelehnt (HTTP {code}).", 502)
    waited = 0.0
    while True:
        st = _ig("GET", f"/{cid}", {"fields": "status_code,status"}, headers=auth)
        state = st.get("status_code")
        if state == "FINISHED":
            break
        if state in ("ERROR", "EXPIRED"):
            raise StudioError("instagram_processing_failed",
                              f"Instagram konnte das Video nicht verarbeiten ({str(st.get('status') or state)[:120]}).",
                              502)
        if waited >= max_wait:
            raise StudioError("instagram_timeout", "Instagram verarbeitet noch — später Status prüfen.", 504,
                              {"container_id": cid})
        if progress:
            progress(f"Instagram verarbeitet ({state or '…'})")
        _sleep(5)
        waited += 5
    published = _ig("POST", f"/{user}/media_publish", {"creation_id": cid}, headers=auth)
    if not published.get("id"):
        raise StudioError("instagram_error", "Veröffentlichung ohne Media-ID beantwortet.", 502)
    return str(published["id"])


def instagram_metrics(media_id: str) -> dict:
    token = accounts.access_token("instagram")
    auth = {"Authorization": f"Bearer {token}"}
    base = _ig("GET", f"/{media_id}", {"fields": "like_count,comments_count,permalink"}, headers=auth)
    out = {"likes": base.get("like_count"), "comments": base.get("comments_count"),
           "url": base.get("permalink")}
    try:
        ins = _ig("GET", f"/{media_id}/insights", {"metric": "views,reach,shares,saved"}, headers=auth)
        for item in ins.get("data") or []:
            values = item.get("values") or [{}]
            out[{"views": "views", "reach": "reach", "shares": "shares", "saved": "saves"}.get(
                item.get("name"), item.get("name"))] = values[0].get("value")
    except StudioError:
        pass  # Insights brauchen instagram_business_manage_insights; Basiswerte reichen
    return out


# ---------------------------------------------------------------------- X
def _x(method: str, path: str, token: str, body: bytes | None = None, ctype: str | None = None,
       query: str = "") -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if ctype:
        headers["Content-Type"] = ctype
    try:
        code, raw = accounts.HTTP(method, f"{X_API}{path}{query}", headers, body)
    except Exception as exc:  # noqa: BLE001
        raise StudioError("x_unreachable", f"X nicht erreichbar ({type(exc).__name__}).", 502) from None
    data = accounts._json(raw)
    if code == 402 or code == 429:
        raise StudioError("x_payment_or_limit",
                          "X: Guthaben/Limit erreicht (Nutzungsabrechnung in der X-Konsole prüfen).", 402)
    if code >= 400:
        detail = (data.get("detail") or data.get("title")
                  or ((data.get("errors") or [{}])[0].get("message")) or code)
        raise StudioError("x_error", f"X meldet: {str(detail)[:160]}", 502, {"http_status": code})
    return data


def _multipart(fields: dict, file_field: str, filename: str, payload: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
                 f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
    parts.append(payload + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def x_upload_video(video_path: str, progress=None, max_wait: float = 600) -> str:
    token = accounts.access_token("x")
    size = os.path.getsize(video_path)
    init = _x("POST", "/media/upload/initialize", token, json.dumps({
        "media_type": "video/mp4", "total_bytes": size, "media_category": "tweet_video"}).encode(),
        "application/json")
    media_id = (init.get("data") or {}).get("id")
    if not media_id:
        raise StudioError("x_error", "X lieferte keine Medien-ID.", 502)
    with open(video_path, "rb") as fh:
        index = 0
        while True:
            chunk = fh.read(X_CHUNK)
            if not chunk:
                break
            body, ctype = _multipart({"segment_index": str(index)}, "media", "video.mp4", chunk)
            _x("POST", f"/media/upload/{media_id}/append", token, body, ctype)
            index += 1
            if progress:
                progress(f"X-Upload Teil {index}")
    fin = _x("POST", f"/media/upload/{media_id}/finalize", token)
    info = (fin.get("data") or {}).get("processing_info")
    waited = 0.0
    while info and info.get("state") in ("pending", "in_progress"):
        if waited >= max_wait:
            raise StudioError("x_timeout", "X verarbeitet das Video noch.", 504)
        wait = float(info.get("check_after_secs") or 5)
        _sleep(wait)
        waited += wait
        st = _x("GET", "/media/upload", token, query=f"?command=STATUS&media_id={media_id}")
        info = (st.get("data") or {}).get("processing_info")
    if info and info.get("state") == "failed":
        raise StudioError("x_processing_failed",
                          f"X konnte das Video nicht verarbeiten ({str(info.get('error') or '')[:120]}).", 502)
    return str(media_id)


def x_post(video_path: str, *, text: str, progress=None) -> str:
    media_id = x_upload_video(video_path, progress)
    token = accounts.access_token("x")
    res = _x("POST", "/tweets", token, json.dumps({"text": text[:280],
                                                   "media": {"media_ids": [media_id]}}).encode(),
             "application/json")
    post_id = (res.get("data") or {}).get("id")
    if not post_id:
        raise StudioError("x_error", "X lieferte keine Post-ID.", 502)
    return str(post_id)


def x_metrics(post_id: str) -> dict:
    data = _x("GET", f"/tweets/{post_id}", accounts.access_token("x"),
              query="?tweet.fields=public_metrics")
    m = (data.get("data") or {}).get("public_metrics") or {}
    return {"views": m.get("impression_count"), "likes": m.get("like_count"),
            "comments": m.get("reply_count"), "shares": m.get("retweet_count"),
            "url": f"https://x.com/i/status/{post_id}"}


# ------------------------------------------------------------ TikTok-Metriken
def tiktok_metrics(video_id: str) -> dict:
    if not accounts.has_scope("tiktok", "video.list"):
        raise StudioError("scope_missing", "TikTok-Kennzahlen brauchen den Scope video.list "
                          "(CLIPFORGE_TIKTOK_METRICS=1, Konto neu verbinden).", 409)
    """Braucht den Scope video.list. Direct-Post-IDs sind publish_ids; die Video-ID
    liefert TikTok im Status als publicaly_available_post_id."""
    data = accounts._api("POST", "/video/query/?fields=id,view_count,like_count,comment_count,share_count,share_url",
                         accounts.access_token("tiktok"), {"filters": {"video_ids": [video_id]}})
    v = (data.get("videos") or [{}])[0]
    return {"views": v.get("view_count"), "likes": v.get("like_count"),
            "comments": v.get("comment_count"), "shares": v.get("share_count"),
            "url": v.get("share_url")}

