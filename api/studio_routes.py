"""HTTP-Routen des Creator Studios — dünne Adapter über `clipforge.studio`.

Hier liegt KEINE Fachlogik: jede Route validiert die Eingabe (Pydantic),
ruft genau einen Service auf und gibt das Ergebnis zurück.

Fehlerformat (stabil, siehe docs/API_STUDIO.md):
    {"detail": {"code": "<stabiler_code>", "message": "<Text>", "details": {...}}}
Idempotenz: `POST /projects`, `/ingest`, `/render` akzeptieren den Header
`Idempotency-Key`; derselbe Key liefert dasselbe Ergebnis.
"""

from __future__ import annotations

import datetime
import os
import tempfile
from typing import Any, Literal

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from clipforge.captions import STYLES as BASE_CAPTION_STYLES
from clipforge.config import get_settings
from clipforge.publishing import list_drafts
from clipforge.studio import analytics, audio, credentials, ideas, publish_ops, templates
from clipforge.studio.automation import AutomationService, Worker
from clipforge.studio.errors import StudioError
from clipforge.studio.flags import is_enabled, load_flags
from clipforge.studio.projects import ASPECT_RATIOS, CAPTION_STYLES, RESOLUTIONS, VISUAL_MODES
from clipforge.studio.providers import readiness as provider_readiness
from clipforge.studio.render import CAPTION_MAP, caption_preview
from clipforge.studio.service import StudioService, save_upload
from clipforge.studio.storage import read_json, safe_filename, studio_dir, write_json_atomic


# ---------------------------------------------------------------- Modelle
class ProductInfo(BaseModel):
    name: str = ""
    problem: str = ""
    benefits: list[str] = Field(default_factory=list)
    price: str = ""
    cta: str = ""


class ProjectCreate(BaseModel):
    workflow: str
    title: str = ""
    language: Literal["de", "en"] = "de"
    prompt: str | None = None
    script: str | None = None
    url: str | None = None
    job_id: str | None = None
    product: ProductInfo | None = None
    tone: str = ""
    target_seconds: int = Field(default=45, ge=10, le=600)
    aspect_ratio: str | None = None
    resolution: str | None = None
    style: str | None = None
    captions: dict[str, Any] | None = None
    voice: dict[str, Any] | None = None
    music: dict[str, Any] | None = None
    budget_limit_usd: float | None = Field(default=None, ge=0, le=10000)
    options: dict[str, Any] | None = None
    rights_confirmed: bool | None = None
    translation: dict[str, Any] | None = None
    template_id: str | None = None
    auto_ingest: bool = True


class ProjectPatch(BaseModel):
    expected_version: int
    title: str | None = None
    language: str | None = None
    tone: str | None = None
    style: str | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    scenes: list[dict[str, Any]] | None = None
    voice: dict[str, Any] | None = None
    music: dict[str, Any] | None = None
    captions: dict[str, Any] | None = None
    visuals: dict[str, Any] | None = None
    options: dict[str, Any] | None = None
    transitions: dict[str, Any] | None = None
    budget_limit_usd: float | None = Field(default=None, ge=0, le=10000)


class TemplateSave(BaseModel):
    name: str
    description: str = ""
    from_project: str | None = None
    settings: dict[str, Any] | None = None
    structure: list[dict[str, Any]] | None = None


class BackgroundRequest(BaseModel):
    mode: Literal["transparent", "color", "image", "video", "blur"] | None = None
    model: Literal["bg_fast", "bg_quality", "bg_person"] | None = None
    color: str | None = None
    background: str | None = None


class BrollImport(BaseModel):
    item: dict[str, Any]
    query: str = ""


class BrollAuto(BaseModel):
    stock: Literal["pexels", "pixabay"] | None = None
    overwrite: bool = False


class MediaTags(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=30)


class ModelDownload(BaseModel):
    accept_license: bool = False


class DirectPublish(BaseModel):
    confirm: bool = False
    confirm_cost: bool = False
    options: dict[str, Any] = Field(default_factory=dict)


class SchedulePublish(BaseModel):
    at: str
    approve: bool = False
    confirm_cost: bool = False
    options: dict[str, Any] = Field(default_factory=dict)


class SocialCopyRequest(BaseModel):
    engine: Literal["local", "anthropic"] = "local"
    confirm_cost: bool = False


class ApplyTemplate(BaseModel):
    expected_version: int
    template_id: str


class SceneOp(BaseModel):
    expected_version: int
    op: Literal["add", "update", "delete", "duplicate", "move", "reorder"]
    scene_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SceneRegenerate(BaseModel):
    expected_version: int
    visual_prompt: str | None = None


class RenderRequest(BaseModel):
    mode: Literal["final", "preview"] = "final"


class ExportRequest(BaseModel):
    render_id: str | None = None


class TitleRequest(BaseModel):
    title: str | None = None


class VoicePreviewRequest(BaseModel):
    language: Literal["de", "en"] = "de"
    provider: str = "auto"
    voice_id: str | None = None
    text: str = ""
    confirm_cost: bool = False
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class AutomationPayload(BaseModel):
    name: str | None = None
    workflow: str | None = None
    enabled: bool | None = None
    schedule: dict[str, Any] | None = None
    items: list[str] | None = None
    language: str | None = None
    settings: dict[str, Any] | None = None
    use_brand_kit: bool | None = None
    publishing: dict[str, Any] | None = None
    budget_per_run_usd: float | None = Field(default=None, ge=0, le=10000)
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=10000)


class ConfirmPayload(BaseModel):
    confirm: bool = False


class CredentialPayload(BaseModel):
    api_key: str = Field(min_length=8, max_length=500)


class MarkPublished(BaseModel):
    confirm: bool = False
    url: str | None = None
    published_at: str | None = None


class MetricsPayload(BaseModel):
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    reach: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)


class IdeaPayload(BaseModel):
    title: str | None = None
    url: str | None = None
    notes: str | None = None
    niche: str | None = None
    tags: list[str] | None = None
    hook_type: str | None = None
    format: str | None = None
    platform: str | None = None
    metrics: dict[str, Any] | None = None


class IdeaUse(BaseModel):
    topic: str
    language: Literal["de", "en"] = "de"


# ------------------------------------------------------------- Verdrahtung
class Studio:
    """Bündelt die Services einer App-Instanz (kein globaler Zustand)."""

    def __init__(self, registry, youtube_status=None, youtube_upload_service=None) -> None:
        self.registry = registry
        self.service = StudioService(registry=registry)
        self.automations = AutomationService(self.service, registry=registry)
        self.youtube_status = youtube_status or (lambda: {})
        self.youtube_upload_service = youtube_upload_service
        self.worker = Worker(self.tick)
        self.service.tasks.on_finish(self._publish_interrupted)

    def _publish_interrupted(self, task: dict) -> None:
        """Abgebrochener Post: ehrlich als „unklar/fehlgeschlagen“ markieren —
        nicht automatisch neu posten (könnte doppelt veröffentlichen)."""
        if task.get("kind") not in ("publish_direct", "publish_tiktok") or \
                task["status"] not in ("interrupted", "canceled"):
            return
        from clipforge.publishing import apply_publish_state
        job = self.registry.get((task.get("params") or {}).get("job_id"))
        if job is not None:
            apply_publish_state(job.job_dir, task["params"]["publishing_id"], {
                "status": "failed", "upload_state": "unknown", "last_error_code": "interrupted",
                "error": "Veröffentlichung wurde unterbrochen. Bitte auf der Plattform prüfen, "
                         "ob der Beitrag erschienen ist, bevor du erneut veröffentlichst."})

    def tick(self) -> None:
        from clipforge.studio import workspace
        for ws in workspace.all_workspaces():
            with workspace.use(*(ws or (None,))):
                self.automations.tick()
        due = publish_ops.scheduler_tick(self.registry, datetime.datetime.now(datetime.timezone.utc))
        for item in due:
            if item.get("auto"):
                self.start_scheduled_post(item)

    def start_scheduled_post(self, item: dict) -> dict | None:
        """Fälligen Post mit gespeicherter Freigabe starten (genau einmal) —
        im Benutzerbereich des Job-Besitzers (dessen Konto-Token)."""
        from clipforge.auth import user_role
        from clipforge.publishing import apply_publish_state, load_draft
        from clipforge.studio import workspace
        job = self.registry.get(item["job_id"])
        if job is None:
            return None
        owner = (job.owner, user_role(job.owner)) if job.owner else None
        with workspace.use(*(owner or (None,))):
            draft = load_draft(job.job_dir, item["publishing_id"]) or {}
            auto = draft.get("auto_publish") or {}
            try:
                prep = publish_ops.direct_prepare(
                    job.job_dir, item["publishing_id"], confirm=True, options=auto.get("options"),
                    confirm_cost=bool(auto.get("confirm_cost")),
                    approval={"source": "zeitplan", "approved_at": auto.get("approved_at"),
                              "scheduled_at": draft.get("scheduled_at")})
            except StudioError as exc:
                apply_publish_state(job.job_dir, item["publishing_id"], {
                    "status": "failed", "error": exc.message, "last_error_code": exc.code})
                return None
            if prep["already"]:
                return None
            return self.service.tasks.submit(
                "publish_direct", None, {"job_id": job.id, "publishing_id": item["publishing_id"]},
                idempotency_key=f"direct:{job.id}:{item['publishing_id']}:"
                                f"{prep['draft'].get('publish_attempt_id')}")

    def startup(self) -> dict:
        from clipforge.studio import workspace
        tasks: dict = {"requeued": [], "interrupted": []}
        autos = None
        for ws in workspace.all_workspaces():  # jeder Benutzerbereich hat eigene Aufgaben
            with workspace.use(*(ws or (None,))):
                res = self.service.tasks.recover()
                tasks["requeued"] += res["requeued"]
                tasks["interrupted"] += res["interrupted"]
                autos = self.automations.recover()
        if os.environ.get("CLIPFORGE_STUDIO_WORKER", "on").strip().lower() != "off" \
                and is_enabled("studio_automation"):
            self.worker.start()
        return {"tasks": tasks, "automations": autos}

    def readiness(self) -> list[dict]:
        return publish_ops.platform_readiness(get_settings(), self.youtube_status())


def _require_studio() -> None:
    if not is_enabled("studio"):
        raise StudioError("feature_disabled", "Das Creator Studio ist deaktiviert.", 403)


def _require_flag(name: str):
    def dep() -> None:
        if not is_enabled(name):
            raise StudioError("feature_disabled", f"Funktion '{name}' ist deaktiviert.", 403)
    return dep


def _idempotent(key: str | None, scope: str, make) -> Any:
    """Führt `make()` höchstens einmal je (scope, key) aus."""
    if not key:
        return make()
    if len(key) > 200:
        raise StudioError("validation_error", "Idempotency-Key ist zu lang.")
    path = os.path.join(studio_dir(), "idempotency.json")
    data = read_json(path, {}) or {}
    full = f"{scope}:{key}"
    if full in data:
        return {"__replayed__": data[full]}
    result = make()
    data = read_json(path, {}) or {}
    data[full] = result
    if len(data) > 2000:
        data = dict(list(data.items())[-1500:])
    write_json_atomic(path, data)
    return result


def init_studio(app: FastAPI, registry, youtube_status=None,
                youtube_upload_service=None) -> Studio:
    studio = Studio(registry, youtube_status, youtube_upload_service)
    svc, autos = studio.service, studio.automations
    r = APIRouter(prefix="/api/studio", tags=["studio"], dependencies=[Depends(_require_studio)])

    @app.exception_handler(StudioError)
    async def _studio_error(_request: Request, exc: StudioError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"detail": exc.to_dict()})

    @app.on_event("startup")
    def _studio_startup() -> None:
        info = studio.startup()
        n = len(info["tasks"]["interrupted"]) + len(info["tasks"]["requeued"])
        if n:
            print(f"[clipforge] Studio-Recovery: {len(info['tasks']['requeued'])} neu eingeplant, "
                  f"{len(info['tasks']['interrupted'])} unterbrochen.")

    @app.on_event("shutdown")
    def _studio_shutdown() -> None:
        studio.worker.stop()

    def _job(job_id: str):
        job = registry.get(job_id)
        if job is None:
            raise StudioError("job_not_found", "Job nicht gefunden.", 404)
        return job

    # ---------------------------------------------------------- Übersicht
    @r.get("/overview")
    def overview() -> dict:
        projects = svc.list_projects()
        return {
            "flags": load_flags(),
            "workflows": svc.workflows(),
            "project_count": len(projects),
            "recent_projects": projects[:6],
            "automation_count": len(autos.list()),
            "idea_count": len(ideas.search()),
            "worker": studio.worker.status(),
            "options": {"aspect_ratios": ASPECT_RATIOS, "resolutions": RESOLUTIONS,
                        "caption_styles": CAPTION_STYLES, "visual_modes": VISUAL_MODES,
                        "languages": ["de", "en"]},
            "llm_available": bool(get_settings().llm_available),
        }

    @r.get("/workflows")
    def workflows() -> dict:
        return {"workflows": svc.workflows()}

    @r.get("/providers")
    def providers() -> dict:
        return {"providers": provider_readiness(), "platforms": studio.readiness(),
                "note": "Es werden nur Namen benötigter Variablen genannt, nie Werte."}

    # --------------------------------------------------------- Credentials
    @r.get("/credentials")
    def credential_status() -> dict:
        return {"credentials": credentials.status(),
                "note": "Es werden nie Schlüsselwerte zurückgegeben."}

    @r.put("/credentials/{provider}")
    def credential_set(provider: str, req: CredentialPayload) -> dict:
        return credentials.set_key(provider, req.api_key)

    @r.delete("/credentials/{provider}")
    def credential_delete(provider: str) -> dict:
        return credentials.delete_key(provider)

    @r.post("/credentials/{provider}/test")
    def credential_test(provider: str) -> dict:
        return credentials.test_key(provider)

    # ------------------------------------------------------- Stimmklon
    @r.get("/voices/clones")
    def clone_list() -> dict:
        from clipforge.studio.voice_clone import CONSENT_TEXT, NO_DECEPTION, list_clones
        return {"clones": list_clones(), "consent_text": CONSENT_TEXT, "no_deception": NO_DECEPTION,
                "enabled": is_enabled("studio_voice_cloning")}

    @r.post("/voices/clones", status_code=201)
    def clone_create(request: Request, name: str = Form(...), basis: str = Form(...),
                     speaker: str = Form(default=""), no_deception: bool = Form(default=False),
                     files: list[UploadFile] = File(...)) -> dict:
        from clipforge.studio.providers import _CLONES, require_ready
        from clipforge.studio.voice_clone import MAX_SAMPLE_BYTES, MAX_SAMPLES, create_clone
        if not is_enabled("studio_voice_cloning"):
            raise StudioError("feature_disabled", "Stimmklon ist deaktiviert.", 403)
        provider = _CLONES[0]
        require_ready(provider)
        if not files or len(files) > MAX_SAMPLES:
            raise StudioError("validation_error", f"Bitte 1 bis {MAX_SAMPLES} Sprachproben hochladen.")
        tmp = tempfile.mkdtemp(prefix="cf_clone_")
        try:
            paths = []
            for i, up in enumerate(files):
                ext = os.path.splitext(up.filename or "")[1].lower()
                # .webm/.mp4: Browser-Aufnahmen (MediaRecorder)
                if ext not in audio.AUDIO_EXT | {".webm", ".mp4"}:
                    raise StudioError("file_type_not_allowed", "Sprachproben müssen Audiodateien sein.", 415)
                dest = os.path.join(tmp, f"probe_{i}{ext}")
                save_upload(up.file, dest, MAX_SAMPLE_BYTES)
                if ext in (".webm", ".mp4", ".ogg"):
                    wav = os.path.join(tmp, f"probe_{i}.wav")
                    try:
                        audio.run_ffmpeg(["ffmpeg", "-y", "-i", dest, "-vn", "-ac", "1", "-ar", "44100",
                                          "-c:a", "pcm_s16le", wav], "Aufnahme umwandeln")
                    except StudioError:
                        raise StudioError("file_unreadable", "Die Aufnahme ist kein lesbares Audio.", 415)
                    dest = wav
                if audio.media_duration(dest) <= 0:
                    raise StudioError("file_unreadable", "Eine Probe ist kein lesbares Audio.", 415)
                paths.append(dest)
            return {"clone": create_clone(
                name=name, speaker=speaker, basis=basis, no_deception=no_deception, samples=paths,
                user=getattr(request.state, "user", None), provider=provider)}
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    @r.delete("/voices/clones/{clone_id}")
    def clone_delete(clone_id: str) -> dict:
        from clipforge.studio.providers import _CLONES
        from clipforge.studio.voice_clone import delete_clone
        delete_clone(clone_id, _CLONES[0])
        return {"deleted": True}

    @r.get("/voices")
    def voices(language: str = "de", tone: str = "") -> dict:
        return svc.voice_options(language if language in ("de", "en") else "de", tone)

    @r.post("/voices/preview")
    def voice_preview(req: VoicePreviewRequest):
        path = svc.voice_preview(req.language, req.provider, req.voice_id, req.text,
                                 req.confirm_cost, req.speed)
        return FileResponse(path, media_type="audio/mpeg")

    @r.get("/caption-styles")
    def caption_styles() -> dict:
        out = []
        for sid in CAPTION_STYLES:
            if sid == "none":
                out.append({"id": "none", "label": "Keine Captions", "word_level": False})
                continue
            base, mode = CAPTION_MAP[sid]
            out.append({"id": sid, "label": sid.capitalize(),
                        "description": BASE_CAPTION_STYLES[base].description,
                        "word_level": mode == "karaoke"})
        return {"styles": out}

    @r.get("/caption-preview")
    def caption_preview_png(style: str = "karaoke", aspect_ratio: str = "9:16",
                            text: str = "", use_brand: bool = True):
        if style not in CAPTION_STYLES or aspect_ratio not in ASPECT_RATIOS:
            raise StudioError("validation_error", "Unbekannter Stil oder Seitenverhältnis.")
        tmp = tempfile.mkdtemp(prefix="cf_cap_")
        out = caption_preview(style, aspect_ratio, text[:120], os.path.join(tmp, "preview.png"),
                              use_brand)
        return FileResponse(out, media_type="image/png")

    # -------------------------------------------------------------- Musik
    @r.get("/music")
    def music_list() -> dict:
        return {"tracks": audio.list_music(),
                "note": "Eigene, lizenzierte Musikdateien. ClipForge liefert keine Musik mit."}

    @r.post("/music")
    def music_upload(file: UploadFile = File(...)) -> dict:
        name = safe_filename(file.filename or "")
        if os.path.splitext(name)[1].lower() not in audio.AUDIO_EXT:
            raise StudioError("file_type_not_allowed", "Bitte eine Audiodatei hochladen.", 415)
        dest = os.path.join(audio.music_dir(), name)
        save_upload(file.file, dest, 100 * 1024 * 1024)
        if audio.media_duration(dest) <= 0:
            os.remove(dest)
            raise StudioError("file_unreadable", "Die Datei ist kein lesbares Audio.", 415)
        return {"id": name, "duration": round(audio.media_duration(dest), 2)}

    @r.get("/music/{track_id}/file")
    def music_file(track_id: str):
        return FileResponse(audio.music_path(track_id))

    @r.get("/music/{track_id}/beats")
    def music_beats(track_id: str) -> dict:
        return audio.detect_beats(audio.music_path(track_id))

    @r.delete("/music/{track_id}")
    def music_delete(track_id: str) -> dict:
        os.remove(audio.music_path(track_id))
        return {"deleted": True}

    # ------------------------------------------------------------ Projekte
    @r.get("/projects")
    def project_list() -> dict:
        return {"projects": svc.list_projects()}

    @r.post("/projects", status_code=201)
    def project_create(req: ProjectCreate,
                       idempotency_key: str | None = Header(default=None)) -> dict:
        def make() -> dict:
            data = req.model_dump(exclude_none=True)
            tid = data.pop("template_id", None)
            template = templates.get_template(tid) if tid else None
            project = svc.create_project(data)
            if template:
                project = svc.store.save(templates.apply_template(project, template),
                                         project["version"])
            task_id = None
            needs_file = project["workflow"] in (
                "pdf", "audio", "music", "podcast", "longform", "media", "youtube", "translate")
            if req.auto_ingest and not needs_file:
                task_id = svc.start_ingest(project["id"])["id"]
            return {"project_id": project["id"], "task_id": task_id}
        result = _idempotent(idempotency_key, "project", make)
        replayed = "__replayed__" in result
        if replayed:
            result = result["__replayed__"]
        project = svc.store.load(result["project_id"])
        return {"project": project, "task_id": result["task_id"], "replayed": replayed,
                "needs_upload": project["workflow"] in (
                    "pdf", "audio", "music", "podcast", "longform", "media", "youtube", "translate")
                and not project["source"].get("file")}

    # ------------------------------------------------------------ Vorlagen
    @r.get("/templates")
    def template_list() -> dict:
        return {"templates": templates.list_templates()}

    def _template_body(req: TemplateSave) -> dict:
        body = req.model_dump(exclude_none=True)
        if req.from_project:
            body = {**templates.from_project(svc.store.load(req.from_project)), **body}
        return body

    @r.post("/templates", status_code=201)
    def template_create(req: TemplateSave) -> dict:
        return {"template": templates.save_template(_template_body(req))}

    @r.put("/templates/{tid}")
    def template_update(tid: str, req: TemplateSave) -> dict:
        return {"template": templates.save_template(_template_body(req), tid)}

    @r.delete("/templates/{tid}")
    def template_delete(tid: str) -> dict:
        templates.delete_template(tid)
        return {"deleted": True}

    @r.post("/projects/{pid}/apply-template")
    def project_apply_template(pid: str, req: ApplyTemplate) -> dict:
        template = templates.get_template(req.template_id)
        project = svc.store.load(pid)
        return {"project": svc.store.save(templates.apply_template(project, template),
                                          req.expected_version)}

    @r.get("/projects/{pid}")
    def project_get(pid: str) -> dict:
        return svc.project_view(pid)

    @r.patch("/projects/{pid}")
    def project_patch(pid: str, req: ProjectPatch) -> dict:
        patch = req.model_dump(exclude_none=True)
        expected = patch.pop("expected_version")
        return {"project": svc.update_project(pid, patch, expected)}

    @r.delete("/projects/{pid}")
    def project_delete(pid: str) -> dict:
        svc.delete_project(pid)
        return {"deleted": True}

    @r.post("/projects/{pid}/duplicate", status_code=201)
    def project_duplicate(pid: str, req: TitleRequest) -> dict:
        return {"project": svc.store.duplicate(pid, req.title)}

    @r.post("/projects/{pid}/remix", status_code=201,
            dependencies=[Depends(_require_flag("studio_analytics"))])
    def project_remix(pid: str, req: TitleRequest) -> dict:
        metrics = None
        for exp in svc.store.load(pid)["exports"]:
            job = registry.get(exp["job_id"])
            if job is None:
                continue
            for draft in list_drafts(job.job_dir):
                entries = analytics.history(job.id, draft["publishing_id"])
                if entries:
                    metrics = entries[-1]
        return {"project": svc.remix(pid, metrics, req.title)}

    @r.post("/projects/{pid}/source")
    def project_source(pid: str, file: UploadFile = File(...),
                       kind: str = Form(default="source")) -> dict:
        if kind not in ("source", "transcript"):
            raise StudioError("validation_error", "kind muss 'source' oder 'transcript' sein.")
        return svc.upload_source(pid, file.filename or "", file.file, kind)

    @r.post("/projects/{pid}/ingest", status_code=202)
    def project_ingest(pid: str, idempotency_key: str | None = Header(default=None)) -> dict:
        return {"task": svc.start_ingest(pid, idempotency_key)}

    @r.get("/projects/{pid}/media")
    def media_list(pid: str) -> dict:
        return {"media": svc.list_media(pid)}

    @r.post("/projects/{pid}/media", status_code=201)
    def media_upload(pid: str, file: UploadFile = File(...)) -> dict:
        return svc.upload_media(pid, file.filename or "", file.file)

    @r.get("/projects/{pid}/media/{name}")
    def media_file(pid: str, name: str):
        return FileResponse(svc.media_path(pid, name))

    @r.delete("/projects/{pid}/media/{name}")
    def media_delete(pid: str, name: str) -> dict:
        svc.delete_media(pid, name)
        return {"deleted": True}

    @r.post("/projects/{pid}/media/{name}/background/preview")
    def media_background_preview(pid: str, name: str, req: BackgroundRequest):
        from fastapi.responses import Response
        png = svc.background_preview(pid, name, req.model_dump(exclude_none=True))
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})

    @r.post("/projects/{pid}/media/{name}/background", status_code=202)
    def media_background(pid: str, name: str, req: BackgroundRequest) -> dict:
        return {"task": svc.start_background(pid, name, req.model_dump(exclude_none=True))}

    # ------------------------------------------------------------- B-Roll
    @r.get("/projects/{pid}/scenes/{scene_id}/broll")
    def broll_suggest(pid: str, scene_id: str, stock: Literal["pexels", "pixabay"] | None = None,
                      kind: Literal["video", "image"] = "video") -> dict:
        return svc.broll_suggest(pid, scene_id, stock, kind)

    @r.post("/projects/{pid}/broll/import", status_code=201)
    def broll_import(pid: str, req: BrollImport) -> dict:
        return svc.broll_import(pid, req.item, req.query)

    @r.post("/projects/{pid}/broll/auto", status_code=202)
    def broll_auto(pid: str, req: BrollAuto) -> dict:
        return {"task": svc.start_broll_auto(pid, req.stock, req.overwrite)}

    @r.put("/projects/{pid}/media/{name}/tags")
    def media_tags(pid: str, name: str, req: MediaTags) -> dict:
        return svc.set_media_tags(pid, name, req.tags)

    @r.post("/projects/{pid}/social-copy")
    def social_copy(pid: str, req: SocialCopyRequest) -> dict:
        from clipforge.studio import social_copy as sc
        from clipforge.studio.costs import CostLedger
        project = svc.store.load(pid)
        if req.engine == "local":
            return sc.local(project)
        if not req.confirm_cost:
            raise StudioError("cost_confirmation_required",
                              f"Claude-Vorschläge kosten ca. {sc.USD_PER_CALL:.2f} USD. Bitte bestätigen.",
                              402, {"estimated_usd": sc.USD_PER_CALL})
        ledger = CostLedger(svc.store.dir(pid), project.get("budget_limit_usd") or 0.0)
        rid = ledger.reserve(sc.USD_PER_CALL, "Social-Texte (Claude)")
        try:
            out = sc.with_llm(project)
        except BaseException:
            ledger.release(rid)
            raise
        ledger.commit(rid, sc.USD_PER_CALL, "anthropic", "social_copy")
        return out

    @r.get("/trends")
    def trends_status() -> dict:
        from clipforge.studio import trends
        return trends.status()

    @r.get("/trends/youtube")
    def trends_youtube(region: str = "DE", category: str = "") -> dict:
        from clipforge.studio import trends
        return trends.youtube_trends(region.upper(), category)

    @r.get("/translation/engines")
    def translation_engines() -> dict:
        from clipforge.studio import translate as tr
        return {"engines": tr.engines_status(), "languages": tr.LANG_NAMES}

    # ------------------------------------------------------- lokale Modelle
    @r.get("/models")
    def model_list(group: str | None = None) -> dict:
        from clipforge.studio import models
        return {"models": models.status(group)}

    @r.post("/models/{model_id}/download", status_code=202)
    def model_download(model_id: str, req: ModelDownload) -> dict:
        from clipforge.studio import models
        if model_id not in models.CATALOG:
            raise StudioError("model_unknown", "Unbekanntes Modell.", 404)
        if not req.accept_license:
            models.download(model_id, False)  # wirft consent_required
        return {"task": svc.tasks.submit("model_download", None, {"model": model_id})}

    @r.delete("/models/{model_id}")
    def model_delete(model_id: str) -> dict:
        from clipforge.studio import models
        models.delete(model_id)
        return {"deleted": True}

    @r.post("/projects/{pid}/scenes")
    def scene_op(pid: str, req: SceneOp) -> dict:
        return {"project": svc.scene_operation(pid, req.op, req.expected_version,
                                               req.scene_id, req.payload)}

    @r.post("/projects/{pid}/scenes/{scene_id}/regenerate", status_code=202)
    def scene_regenerate(pid: str, scene_id: str, req: SceneRegenerate) -> dict:
        return svc.regenerate_scene(pid, scene_id, req.expected_version, req.visual_prompt)

    @r.get("/projects/{pid}/estimate")
    def project_estimate(pid: str) -> dict:
        return svc.estimate(pid)

    @r.get("/projects/{pid}/quality")
    def project_quality(pid: str) -> dict:
        return svc.quality(pid)

    @r.post("/projects/{pid}/render", status_code=202)
    def project_render(pid: str, req: RenderRequest,
                       idempotency_key: str | None = Header(default=None)) -> dict:
        return {"task": svc.start_render(pid, req.mode, idempotency_key)}

    @r.get("/projects/{pid}/renders")
    def render_list(pid: str) -> dict:
        return {"renders": svc.list_renders(pid)}

    @r.get("/projects/{pid}/renders/{render_id}")
    def render_get(pid: str, render_id: str) -> dict:
        return svc.get_render(pid, render_id)

    @r.get("/projects/{pid}/renders/{render_id}/file")
    def render_file(pid: str, render_id: str, download: bool = False):
        path = svc.render_file(pid, render_id)
        if download:
            return FileResponse(path, media_type="video/mp4",
                                filename=f"clipforge_studio_{render_id}.mp4")
        return FileResponse(path, media_type="video/mp4")

    @r.post("/projects/{pid}/export")
    def project_export(pid: str, req: ExportRequest) -> dict:
        return svc.export_to_job(pid, req.render_id)

    @r.get("/projects/{pid}/versions")
    def project_versions(pid: str) -> dict:
        return {"versions": svc.store.versions(pid)}

    @r.post("/projects/{pid}/versions/{version}/restore")
    def project_restore(pid: str, version: int) -> dict:
        return {"project": svc.store.restore_version(pid, version)}

    @r.get("/projects/{pid}/artifacts")
    def artifact_list(pid: str) -> dict:
        return {"artifacts": svc.list_artifacts(pid)}

    @r.get("/projects/{pid}/artifacts/{name}")
    def artifact_get(pid: str, name: str) -> dict:
        return svc.get_artifact(pid, name)

    # ------------------------------------------------------------ Aufgaben
    @r.get("/tasks/{task_id}")
    def task_get(task_id: str) -> dict:
        return svc.tasks.get(task_id)

    @r.post("/tasks/{task_id}/retry", status_code=202)
    def task_retry(task_id: str) -> dict:
        task = svc.tasks.get(task_id)
        if task["kind"] in ("publish_direct", "publish_tiktok"):
            raise StudioError("retry_not_allowed",
                              "Veröffentlichungen werden nicht automatisch wiederholt. Bitte prüfen, "
                              "ob der Beitrag erschienen ist, und bewusst neu veröffentlichen.", 409)
        if task["kind"] == "ingest" and task.get("project_id"):
            svc.store.mutate(task["project_id"],
                             lambda p: p.update(status="ingesting", status_error=None))
        return {"task": svc.tasks.retry(task_id)}

    @r.post("/tasks/{task_id}/cancel")
    def task_cancel(task_id: str) -> dict:
        return {"task": svc.tasks.cancel(task_id)}

    # --------------------------------------------------------- Automation
    auto_dep = [Depends(_require_flag("studio_automation"))]

    @r.get("/automations", dependencies=auto_dep)
    def automation_list() -> dict:
        return {"automations": [autos.view(a) for a in autos.list()],
                "worker": studio.worker.status(),
                "max_concurrent": autos.max_concurrent,
                "safety": "Automationen erzeugen höchstens Entwürfe und veröffentlichen nie."}

    @r.post("/automations", status_code=201, dependencies=auto_dep)
    def automation_create(req: AutomationPayload) -> dict:
        return {"automation": autos.view(autos.create(req.model_dump(exclude_none=True)))}

    @r.get("/automations/{aid}", dependencies=auto_dep)
    def automation_get(aid: str) -> dict:
        return {"automation": autos.view(autos.get(aid))}

    @r.patch("/automations/{aid}", dependencies=auto_dep)
    def automation_patch(aid: str, req: AutomationPayload) -> dict:
        return {"automation": autos.view(autos.update(aid, req.model_dump(exclude_none=True)))}

    @r.delete("/automations/{aid}", dependencies=auto_dep)
    def automation_delete(aid: str) -> dict:
        autos.delete(aid)
        return {"deleted": True}

    @r.post("/automations/{aid}/pause", dependencies=auto_dep)
    def automation_pause(aid: str) -> dict:
        return {"automation": autos.view(autos.set_enabled(aid, False))}

    @r.post("/automations/{aid}/resume", dependencies=auto_dep)
    def automation_resume(aid: str) -> dict:
        return {"automation": autos.view(autos.set_enabled(aid, True))}

    @r.post("/automations/{aid}/run", status_code=202, dependencies=auto_dep)
    def automation_run(aid: str) -> dict:
        return autos.run_now(aid)

    @r.post("/automations/{aid}/runs/{run_id}/retry", status_code=202, dependencies=auto_dep)
    def automation_retry(aid: str, run_id: str) -> dict:
        return autos.retry_run(aid, run_id)

    # ---------------------------------------------------------- Publishing
    @r.get("/publishing/platforms")
    def publishing_platforms() -> dict:
        return {"platforms": studio.readiness(),
                "safety": ("Kein automatisches Veröffentlichen. YouTube nur PRIVAT und nur "
                           "nach Bestätigung; andere Plattformen über das Export-Pack.")}

    @r.get("/publishing/drafts")
    def publishing_drafts() -> dict:
        ready = studio.readiness()
        rows = []
        for job in registry.list():
            if not os.path.isdir(job.job_dir):
                continue
            for d in list_drafts(job.job_dir):
                rows.append({
                    "job_id": job.id, "publishing_id": d["publishing_id"],
                    "platform": d.get("platform"), "title": d.get("title"),
                    "status": d.get("status"), "state": publish_ops.draft_state(d, ready),
                    "scheduled_at": d.get("scheduled_at"),
                    "published_at": d.get("published_at"),
                    "publish_source": d.get("publish_source"),
                    "external_url": d.get("external_url"),
                    "auto_publish": bool((d.get("auto_publish") or {}).get("approved_at")),
                    "error": d.get("error") if d.get("status") == "failed" else None})
        rows.sort(key=lambda x: x["scheduled_at"] or x["published_at"] or "", reverse=True)
        return {"drafts": rows}

    # ------------------------------------------------- Konten / TikTok
    from clipforge.studio import accounts as accts

    @r.get("/accounts")
    def account_list() -> dict:
        return {"accounts": [accts.status(p) for p in accts.PLATFORMS], "not_supported": {}}

    @r.post("/accounts/{platform}/connect")
    def account_connect(platform: str) -> dict:
        return accts.start(platform)

    @r.delete("/accounts/{platform}")
    def account_disconnect(platform: str) -> dict:
        accts.disconnect(platform)
        return {"disconnected": True}

    @r.post("/publishing/{job_id}/{publishing_id}/tiktok", status_code=202)
    def tiktok_publish(job_id: str, publishing_id: str, req: ConfirmPayload) -> dict:
        job = _job(job_id)
        prep = publish_ops.tiktok_prepare(job.job_dir, publishing_id, req.confirm)
        if prep["already"]:
            return {"task": None, "draft": prep["draft"], "already": True}
        task = svc.tasks.submit("publish_tiktok", None,
                                {"job_id": job.id, "publishing_id": publishing_id},
                                idempotency_key=f"tiktok:{job.id}:{publishing_id}:"
                                                f"{prep['draft'].get('publish_attempt_id')}")
        return {"task": task, "draft": prep["draft"], "already": False}

    @r.post("/publishing/{job_id}/{publishing_id}/tiktok/status")
    def tiktok_status(job_id: str, publishing_id: str) -> dict:
        job = _job(job_id)
        return publish_ops.tiktok_refresh(job.job_dir, publishing_id)

    def _task_publish_tiktok(task: dict, progress, should_cancel) -> dict:
        job = _job(task["params"]["job_id"])
        res = publish_ops.tiktok_upload(job.job_dir, task["params"]["publishing_id"], progress)
        return {"state": res["tiktok"]["state"], "publish_id": res["draft"].get("external_post_id")}
    svc.tasks.register("publish_tiktok", _task_publish_tiktok)

    @r.get("/publishing/tiktok/creator-info")
    def tiktok_creator_info() -> dict:
        from clipforge.studio import social
        return social.tiktok_creator_info()

    @r.post("/publishing/{job_id}/{publishing_id}/publish", status_code=202)
    def direct_publish(job_id: str, publishing_id: str, req: DirectPublish) -> dict:
        job = _job(job_id)
        prep = publish_ops.direct_prepare(job.job_dir, publishing_id, confirm=req.confirm,
                                          options=req.options, confirm_cost=req.confirm_cost)
        if prep["already"]:
            return {"task": None, "draft": prep["draft"], "already": True}
        task = svc.tasks.submit("publish_direct", None,
                                {"job_id": job.id, "publishing_id": publishing_id},
                                idempotency_key=f"direct:{job.id}:{publishing_id}:"
                                                f"{prep['draft'].get('publish_attempt_id')}")
        return {"task": task, "draft": prep["draft"], "already": False}

    def _task_publish_direct(task: dict, progress, should_cancel) -> dict:
        job = _job(task["params"]["job_id"])
        draft = publish_ops.direct_publish(job.job_dir, task["params"]["publishing_id"], progress)
        return {"status": draft.get("status"), "external_url": draft.get("external_url"),
                "external_post_id": draft.get("external_post_id")}
    svc.tasks.register("publish_direct", _task_publish_direct)

    @r.post("/publishing/{job_id}/{publishing_id}/schedule")
    def direct_schedule(job_id: str, publishing_id: str, req: SchedulePublish) -> dict:
        job = _job(job_id)
        return {"draft": publish_ops.schedule_direct(
            job.job_dir, publishing_id, at=req.at, approve=req.approve, options=req.options,
            confirm_cost=req.confirm_cost)}

    @r.delete("/publishing/{job_id}/{publishing_id}/schedule")
    def direct_unschedule(job_id: str, publishing_id: str) -> dict:
        job = _job(job_id)
        return {"draft": publish_ops.cancel_schedule(job.job_dir, publishing_id)}

    @r.post("/publishing/{job_id}/{publishing_id}/mark-published")
    def publishing_mark(job_id: str, publishing_id: str, req: MarkPublished) -> dict:
        job = _job(job_id)
        return {"draft": publish_ops.mark_published(
            job.job_dir, publishing_id, confirm=req.confirm, url=req.url,
            published_at=req.published_at)}

    # ----------------------------------------------------------- Analytics
    ana_dep = [Depends(_require_flag("studio_analytics"))]

    def _fetchers() -> dict:
        from clipforge.studio import social
        out: dict = {}
        if accts.status("instagram")["state"] == "connected":
            out["instagram_reels"] = social.instagram_metrics
        if accts.status("x")["state"] == "connected":
            out["x"] = social.x_metrics
        if accts.status("tiktok")["state"] == "connected" and accts.has_scope("tiktok", "video.list"):
            out["tiktok"] = social.tiktok_metrics
        if studio.youtube_upload_service is None:
            return out
        ready = next((p for p in studio.readiness() if p["platform"] == "youtube_shorts"), {})
        if ready.get("state") != "ready":
            return out
        out["youtube_shorts"] = analytics.default_youtube_fetcher(studio.youtube_upload_service())
        return out

    studio.metric_fetchers = _fetchers  # in Tests ersetzbar

    @r.get("/analytics", dependencies=ana_dep)
    def analytics_overview() -> dict:
        return analytics.overview(registry)

    @r.get("/analytics/{job_id}/{publishing_id}", dependencies=ana_dep)
    def analytics_history(job_id: str, publishing_id: str) -> dict:
        _job(job_id)
        return {"entries": analytics.history(job_id, publishing_id)}

    @r.post("/analytics/{job_id}/{publishing_id}/metrics", status_code=201, dependencies=ana_dep)
    def analytics_manual(job_id: str, publishing_id: str, req: MetricsPayload) -> dict:
        job = _job(job_id)
        return {"entry": analytics.record(job.id, job.job_dir, publishing_id,
                                          req.model_dump(), "manual")}

    @r.post("/analytics/{job_id}/{publishing_id}/sync", status_code=201, dependencies=ana_dep)
    def analytics_sync(job_id: str, publishing_id: str) -> dict:
        job = _job(job_id)
        return {"entry": analytics.sync(job.id, job.job_dir, publishing_id,
                                        studio.metric_fetchers())}

    # --------------------------------------------------------------- Ideen
    idea_dep = [Depends(_require_flag("studio_ideas"))]

    @r.get("/ideas", dependencies=idea_dep)
    def idea_list(q: str = "", niche: str = "", hook_type: str = "", format: str = "",
                  tag: str = "", platform: str = "") -> dict:
        return {"ideas": ideas.search(q, niche, hook_type, format, tag, platform),
                "options": {"hook_types": ideas.HOOK_TYPES, "formats": ideas.FORMATS,
                            "platforms": ideas.PLATFORMS},
                "notice": ideas.ORIGINALITY_NOTICE}

    @r.post("/ideas", status_code=201, dependencies=idea_dep)
    def idea_create(req: IdeaPayload) -> dict:
        return {"idea": ideas.create(req.model_dump(exclude_none=True))}

    @r.patch("/ideas/{idea_id}", dependencies=idea_dep)
    def idea_update(idea_id: str, req: IdeaPayload) -> dict:
        return {"idea": ideas.update(idea_id, req.model_dump(exclude_none=True))}

    @r.delete("/ideas/{idea_id}", dependencies=idea_dep)
    def idea_delete(idea_id: str) -> dict:
        ideas.delete(idea_id)
        return {"deleted": True}

    @r.post("/ideas/{idea_id}/use", status_code=201, dependencies=idea_dep)
    def idea_use(idea_id: str, req: IdeaUse) -> dict:
        idea = ideas.get(idea_id)
        project = svc.create_project(ideas.inspiration_request(idea, req.topic, req.language))
        task = svc.start_ingest(project["id"])
        return {"project": project, "task_id": task["id"],
                "originality_notice": ideas.ORIGINALITY_NOTICE[req.language]}

    @app.get("/api/studio/accounts/{platform}/callback")
    def account_callback(platform: str, code: str | None = None, state: str | None = None,
                         error: str | None = None):
        """OAuth-Rückkehr von der Plattform → zurück zur Einrichtungsseite."""
        from fastapi.responses import RedirectResponse
        from urllib.parse import quote
        front = os.environ.get("CLIPFORGE_FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/")
        try:
            accts.callback(platform, code, state, error)
            return RedirectResponse(f"{front}/studio/setup?account={quote(platform)}&result=ok", 303)
        except StudioError as exc:
            return RedirectResponse(
                f"{front}/studio/setup?account={quote(platform)}&result={quote(exc.code)}", 303)

    app.include_router(r)
    return studio
