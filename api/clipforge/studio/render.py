"""Studio-Renderer: Szenen → Visual-Segmente + Voice + Musik + Captions → MP4.

Ablauf (alles lokal über FFmpeg, Aufrufe ausschließlich als Argumentlisten):
  1. Voice je Szene (Provider, gecacht) bzw. Ausschnitt aus Original-Audio
  2. Szenendauer bestimmen, optional auf Musik-Beats einrasten
  3. Visual-Segment je Szene (Motion-Verlauf, Farbe, eigenes Bild/Video,
     KI-Bild mit Ken-Burns, Split-Screen)
  4. Finaler Pass: Concat + Voice + Musik (Ducking) + eingebrannte Captions
Kostenpflichtige Provider laufen nur nach Budgetprüfung; fällt ein Provider
aus, wird lokal ersetzt und der Vorfall im Report vermerkt.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import wave

from ..brand_kit import load_brand_kit, to_caption_overrides
from ..captions import _escape, _fmt_ts, make_captions
from ..ffmpeg_utils import concat_entry, filter_path, probe
from ..models import Word
from . import audio as audio_mod
from .audio import media_duration, run_ffmpeg
from .costs import CostLedger
from .errors import BudgetExceeded, ProviderError, StudioError
from .options import options_of
from .projects import IMAGE_EXT, VIDEO_EXT, resolve_music
from .providers import get_image, get_voice, select_voice
from .providers.local import speech_seconds
from .storage import new_id, now_iso, read_json, safe_child, write_json_atomic

ASPECT = {"9:16": (9, 16), "16:9": (16, 9), "1:1": (1, 1), "4:5": (4, 5)}
SHORT_SIDE = {"720p": 720, "1080p": 1080, "4k": 2160}
# Studio-Caption-Stil → (bestehender Caption-Style, Modus)
CAPTION_MAP = {
    "minimal": ("minimal", "standard"),
    "bold": ("bold_creator", "standard"),
    "karaoke": ("clean", "karaoke"),
    "dynamic": ("high_energy", "karaoke"),
}
PALETTES = [
    ("#1e3a8a", "#7c3aed"), ("#0f766e", "#1d4ed8"), ("#9d174d", "#c2410c"),
    ("#14532d", "#0e7490"), ("#3730a3", "#be185d"), ("#7c2d12", "#a16207"),
]
_FONT_RE = re.compile(r"^[A-Za-z0-9 _-]{1,40}$")
VOICE_PAD = 0.25


class RenderCanceled(Exception):
    pass


def dimensions(aspect_ratio: str, resolution: str, preview: bool = False) -> tuple[int, int]:
    aw, ah = ASPECT.get(aspect_ratio, (9, 16))
    short = 360 if preview else SHORT_SIDE.get(resolution, 1080)
    if aw <= ah:
        w, h = short, short * ah / aw
    else:
        w, h = short * aw / ah, short
    return int(round(w / 2) * 2), int(round(h / 2) * 2)


def _hash(*parts) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:20]


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:20]


def _cover(w: int, h: int) -> str:
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"


def _grade(style: str) -> str:
    return ",eq=contrast=1.06:saturation=0.88,vignette=PI/5" if style == "cinematic" else ""


class StudioRenderer:
    def __init__(self, project: dict, project_dir: str, *, mode: str = "final",
                 progress=None, should_cancel=None, voice_override=None) -> None:
        self.p = project
        self.dir = project_dir
        self.preview = mode == "preview"
        self.progress = progress or (lambda _m: None)
        self.should_cancel = should_cancel or (lambda: False)
        self.w, self.h = dimensions(project["aspect_ratio"], project["resolution"], self.preview)
        self.fps = 15 if self.preview else 30
        self.preset = "ultrafast" if self.preview else "veryfast"
        self.crf = "30" if self.preview else "20"
        self.cache = os.path.join(project_dir, "cache")
        self.ledger = CostLedger(project_dir, project.get("budget_limit_usd") or 0.0)
        self.warnings: list[str] = []
        self._upscale_checked: set[str] = set()
        self._tts_words: dict[str, list] = {}
        self._scene_wav: dict[str, str] = {}
        self._scene_speech: dict[str, float] = {}
        self.fallbacks: list[dict] = []
        self.voice_override = voice_override
        self.brand = load_brand_kit()
        self.opt = options_of(project)
        os.makedirs(os.path.join(self.cache, "voice"), exist_ok=True)
        os.makedirs(os.path.join(self.cache, "image"), exist_ok=True)

    # ------------------------------------------------------------ Helfer
    def _check(self) -> None:
        if self.should_cancel():
            raise RenderCanceled()

    def _media(self, name: str) -> str:
        path = safe_child(os.path.join(self.dir, "media"), name)
        if not os.path.isfile(path):
            raise StudioError("media_not_found", f"Mediendatei '{name}' fehlt.", 404)
        return path

    def _colors(self, index: int, scene: dict) -> tuple[str, str]:
        custom = scene["visual"].get("color")
        if custom:
            return custom, PALETTES[index % len(PALETTES)][1]
        if self.p["captions"].get("use_brand") and self.brand.get("_exists"):
            return self.brand["secondary_color"], self.brand["primary_color"]
        return PALETTES[(index + scene["visual"].get("seed", 0)) % len(PALETTES)]

    # ------------------------------------------------------------- Voice
    def resolve_voice(self) -> dict:
        if self.voice_override:
            return self.voice_override
        v = self.p["voice"]
        return select_voice(
            self.p["language"], v.get("tone") or self.p.get("tone") or "",
            v.get("provider"), v.get("voice_id"),
            allow_paid=(self.p.get("budget_limit_usd") or 0) > 0)

    def _voice_for_scene(self, scene: dict, voice: dict, work: str) -> tuple[str, float, str]:
        """→ (wav-Pfad normalisiert, Sprechdauer, timing_quelle)."""
        out = os.path.join(work, f"voice_{scene['id']}.wav")
        src = scene.get("audio_source")
        original = self.p["source"].get("audio_file")
        if src and original:
            run_ffmpeg(["ffmpeg", "-y", "-ss", f"{src['start']:.3f}", "-to", f"{src['end']:.3f}",
                        "-i", safe_child(os.path.join(self.dir, "source"), original),
                        "-vn", "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", out],
                       "Audio-Ausschnitt")
            return out, src["end"] - src["start"], "transcribed"
        text = scene.get("voice_text") or scene["text"]
        if not text.strip():
            return self._silence(out, 1.0), 0.0, "none"
        provider = get_voice(voice["provider"])
        speed = float(self.p["voice"].get("speed") or 1.0)
        key = _hash(provider.id, voice["voice_id"], self.p["language"], text,
                    self.opt.voice_model, speed)
        cached = os.path.join(self.cache, "voice", key + ".audio")
        words_file = cached + ".words.json"
        if not os.path.isfile(cached):
            # Reservieren VOR der Anfrage (wirft BudgetExceeded, ohne etwas zu senden)
            rid = self.ledger.reserve(
                provider.estimate_cost(len(text)) if provider.paid else 0.0,
                f"Voice-over ({provider.label})")
            try:
                tmp = cached + ".tmp"
                result = provider.synthesize(text, self.p["language"], voice["voice_id"], tmp,
                                             model=self.opt.voice_model or None, speed=speed)
                if result.words:  # echte Wort-Zeitpunkte des TTS (z. B. eSpeak)
                    write_json_atomic(words_file, result.words)
                os.replace(tmp, cached)
                self.ledger.commit(rid, result.cost_usd, provider.id, "voice")
            except ProviderError as exc:
                self.ledger.release(rid)  # Ausfall kostet nichts; Fallback ist kostenlos
                self.fallbacks.append({"scene_id": scene["id"], "kind": "voice",
                                       "provider": provider.id, "fallback": "none",
                                       "reason": str(exc)})
                self.warnings.append(
                    f"Voice-Provider '{provider.id}' ausgefallen — Szene ohne Stimme gerendert.")
                seconds = speech_seconds(text, speed)
                return self._silence(out, seconds), seconds, "estimated"
            except BaseException:
                self.ledger.release(rid)
                raise
        run_ffmpeg(["ffmpeg", "-y", "-i", cached, "-vn", "-ac", "1", "-ar", "44100",
                    "-c:a", "pcm_s16le", out], "Voice-Normalisierung")
        words = read_json(words_file, None)
        # Wort-Timings passen nur, wenn die Caption genau den gesprochenen Text zeigt
        if isinstance(words, list) and words and not scene.get("voice_text"):
            self._tts_words[scene["id"]] = words
            return out, media_duration(out), "tts"
        return out, media_duration(out), "estimated"

    @staticmethod
    def _silence(path: str, seconds: float) -> str:
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00\x00" * int(44100 * max(0.05, seconds)))
        return path

    @staticmethod
    def _fit_wav(src: str, dst: str, seconds: float) -> None:
        """Bringt ein Mono-44.1k-WAV exakt auf `seconds` (Stille anhängen/kürzen)."""
        want = int(round(44100 * seconds))
        with wave.open(src, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        have = len(frames) // 2
        if have >= want:
            frames = frames[: want * 2]
        else:
            frames += b"\x00\x00" * (want - have)
        with wave.open(dst, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(frames)

    def _note_upscale(self, path: str, w: int, h: int) -> None:
        """Kontrolliertes Upscaling: kleinere Quellen werden hochskaliert und
        das wird im finalen Render-Bericht offen vermerkt (keine stille
        „4K“-Behauptung). Vorschauen sind bewusst klein und warnen nicht."""
        if self.preview or path in self._upscale_checked:
            return
        self._upscale_checked.add(path)
        try:
            info = probe(path)
        except Exception:  # noqa: BLE001 — Messfehler blockiert den Render nicht
            return
        if not info.width or not info.height:
            return
        factor = max(w / info.width, h / info.height)
        if factor > 1.0 + 1e-6:
            self.warnings.append(
                f"'{os.path.basename(path)}' ({info.width}×{info.height}) ist kleiner als "
                f"die Zielauflösung und wurde um Faktor {factor:.1f} hochskaliert.")

    # ------------------------------------------------------------ Visuals
    def _ai_image(self, scene: dict) -> str | None:
        """KI-Bild (gecacht). None → lokaler Fallback wurde vermerkt."""
        pid = self.p["visuals"].get("image_provider") or "openai_image"
        prompt = scene.get("visual_prompt") or scene["text"]
        key = _hash(pid, prompt, self.p["aspect_ratio"], scene["visual"].get("seed", 0))
        path = os.path.join(self.cache, "image", key + ".png")
        if os.path.isfile(path):
            return path
        rid = None
        try:
            provider = get_image(pid)
            state, hint = provider.status()
            if state != "ready":
                raise ProviderError(pid, f"nicht einsatzbereit ({state})")
            rid = self.ledger.reserve(provider.estimate_cost(1) if provider.paid else 0.0,
                                      f"KI-Bild ({provider.label})")
            w, h = dimensions(self.p["aspect_ratio"], "1080p")
            tmp = path + ".tmp.png"
            cost = provider.generate(prompt, w, h, tmp)
            os.replace(tmp, path)
            self.ledger.commit(rid, cost, provider.id, "image")
            return path
        except BudgetExceeded:
            raise
        except (ProviderError, StudioError) as exc:
            self.ledger.release(rid)
            self.fallbacks.append({"scene_id": scene["id"], "kind": "image", "provider": pid,
                                   "fallback": "motion", "reason": str(exc)})
            self.warnings.append(
                f"Bild-Provider '{pid}' nicht nutzbar — Szene mit lokalem Motion-Hintergrund gerendert.")
            return None
        except BaseException:
            self.ledger.release(rid)
            raise

    def _can_fallback_to_image(self) -> bool:
        from .providers import get_image
        try:
            prov = get_image(self.p["visuals"].get("image_provider") or "openai_image")
        except StudioError:
            return False
        return prov.status()[0] == "ready"

    def _ai_video(self, scene: dict, dur: float) -> str | None:
        """KI-Clip (gecacht). Text→Video oder — mit Bild als Medium — Bild→Video."""
        from .providers import get_video
        pid = self.p["visuals"].get("video_provider") or "fal_video"
        rid = None
        try:
            provider = get_video(pid)
            state, _ = provider.status()
            if state != "ready":
                raise ProviderError(pid, f"nicht einsatzbereit ({state})")
            seconds = provider.clip_seconds(dur)
            image = None
            media = scene["visual"].get("media")
            if media and os.path.splitext(media)[1].lower() in IMAGE_EXT:
                image = self._media(media)
            prompt = scene.get("visual_prompt") or scene["text"]
            key = _hash(pid, provider.models(), prompt, seconds, self.p["aspect_ratio"],
                        scene["visual"].get("seed", 0), _file_hash(image) if image else "")
            path = os.path.join(self.cache, "video", key + ".mp4")
            if os.path.isfile(path):
                return path
            os.makedirs(os.path.dirname(path), exist_ok=True)
            rid = self.ledger.reserve(provider.estimate_cost(seconds), f"KI-Video ({provider.label})")
            tmp = path + ".part"
            cost = provider.generate(prompt, image, seconds, self.p["aspect_ratio"], tmp,
                                     should_cancel=self.should_cancel)
            os.replace(tmp, path)
            self.ledger.commit(rid, cost, provider.id, "video")
            return path
        except BudgetExceeded:
            raise
        except (ProviderError, StudioError) as exc:
            self.ledger.release(rid)
            if self.should_cancel():
                raise RenderCanceled() from None
            self.fallbacks.append({"scene_id": scene["id"], "kind": "video", "provider": pid,
                                   "fallback": "ai_image/motion", "reason": str(exc)})
            self.warnings.append(f"KI-Video '{pid}' nicht nutzbar — Szene mit Ersatz-Visual gerendert.")
            return None
        except BaseException:
            self.ledger.release(rid)
            raise

    def _avatar(self, scene: dict) -> str | None:
        """Sprechender Avatar aus Avatar-Bild + Stimme dieser Szene (gecacht)."""
        from .providers import get_avatar
        pid = self.p["visuals"].get("avatar_provider") or "fal_avatar"
        image_name = self.p["visuals"].get("avatar_image")
        wav = self._scene_wav.get(scene["id"])
        rid = None
        try:
            if not image_name:
                raise ProviderError(pid, "kein Avatar-Bild gewählt")
            if not wav or self._scene_speech.get(scene["id"], 0) <= 0:
                raise ProviderError(pid, "Szene hat keine Stimme")
            provider = get_avatar(pid)
            state, _ = provider.status()
            if state != "ready":
                raise ProviderError(pid, f"nicht einsatzbereit ({state})")
            image = self._media(image_name)
            key = _hash(pid, provider.model(), _file_hash(image), _file_hash(wav))
            path = os.path.join(self.cache, "avatar", key + ".mp4")
            if os.path.isfile(path):
                return path
            os.makedirs(os.path.dirname(path), exist_ok=True)
            rid = self.ledger.reserve(provider.estimate_cost(self._scene_speech[scene["id"]]),
                                      f"Talking Avatar ({provider.label})")
            tmp = path + ".part"
            cost = provider.generate(image, wav, tmp, should_cancel=self.should_cancel)
            os.replace(tmp, path)
            self.ledger.commit(rid, cost, provider.id, "avatar")
            return path
        except BudgetExceeded:
            raise
        except (ProviderError, StudioError) as exc:
            self.ledger.release(rid)
            if self.should_cancel():
                raise RenderCanceled() from None
            self.fallbacks.append({"scene_id": scene["id"], "kind": "avatar", "provider": pid,
                                   "fallback": "image", "reason": str(exc)})
            self.warnings.append(
                f"Talking Avatar nicht nutzbar ({exc}) — Szene mit Standbild ohne Lippenbewegung.")
            return None
        except BaseException:
            self.ledger.release(rid)
            raise

    def _base_inputs(self, index: int, scene: dict, dur: float, w: int, h: int,
                     offset: float) -> tuple[list[str], str]:
        """→ (ffmpeg-Input-Argumente, Filterkette für diesen Input)."""
        mode = scene["visual"]["mode"]
        if mode == "split":
            mode = "media" if scene["visual"].get("media") else "motion"
        image: str | None = None
        if mode == "ai_video":
            clip = self._ai_video(scene, dur)
            if clip:
                return (["-stream_loop", "-1", "-i", clip],
                        f"{_cover(w, h)},fps={self.fps}{_grade(self.p['style'])}")
            mode = "ai_image" if self._can_fallback_to_image() else "motion"
        if mode == "avatar":
            clip = self._avatar(scene)
            if clip:
                # letztes Bild halten, falls die Szene länger als die Sprechzeit ist
                return (["-i", clip],
                        f"{_cover(w, h)},fps={self.fps},tpad=stop_mode=clone:stop_duration=600")
            avatar = self.p["visuals"].get("avatar_image")
            if avatar:  # ehrlicher Ersatz: Standbild des Avatars (ohne Lippenbewegung)
                image, mode = self._media(avatar), "image"
            else:
                mode = "motion"
        if mode == "ai_image":
            image = self._ai_image(scene)
            mode = "image" if image else "motion"
        if mode == "media":
            path = self._media(scene["visual"]["media"])
            ext = os.path.splitext(path)[1].lower()
            if ext in IMAGE_EXT:
                image, mode = path, "image"
            elif ext in VIDEO_EXT:
                self._note_upscale(path, w, h)
                return (["-stream_loop", "-1", "-i", path],
                        f"{_cover(w, h)},fps={self.fps}{_grade(self.p['style'])}")
            else:
                raise StudioError("media_unsupported", "Dieser Medientyp kann nicht als Visual dienen.", 415)
        if mode == "image" and image:
            self._note_upscale(image, w, h)
        if mode == "image" and image and not self.opt.image_animation:
            # Option „Bildanimation aus“: Standbild ohne Ken-Burns
            return (["-loop", "1", "-framerate", str(self.fps), "-i", image],
                    f"{_cover(w, h)}{_grade(self.p['style'])}")
        if mode == "image" and image:
            frames = max(2, int(round(dur * self.fps)))
            speed = 0.0006 if self.p["style"] == "cinematic" else 0.0012
            zoom = (f"zoompan=z='min(zoom+{speed},1.35)':d={frames}"
                    f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={self.fps}")
            return (["-i", image], f"{_cover(w * 2, h * 2)},{zoom}{_grade(self.p['style'])}")
        c0, c1 = self._colors(index, scene)
        if mode == "static":
            return (["-f", "lavfi", "-i", f"color=c={c0}:s={w}x{h}:r={self.fps}:d={dur:.3f}"],
                    f"setsar=1{_grade(self.p['style'])}")
        seed = (index * 7 + scene["visual"].get("seed", 0) * 13) % 100000
        speed = 0.008 if self.p["style"] == "cinematic" else 0.02
        return (["-f", "lavfi", "-i",
                 f"gradients=s={w}x{h}:c0={c0}:c1={c1}:n=2:seed={seed}:speed={speed}"
                 f":r={self.fps}:d={dur:.3f}"],
                f"setsar=1{_grade(self.p['style'])}")

    def render_segment(self, index: int, scene: dict, dur: float, out: str, offset: float) -> None:
        split = scene["visual"]["mode"] == "split"
        gameplay = self.p["visuals"].get("gameplay_media")
        enc = ["-an", "-c:v", "libx264", "-preset", self.preset, "-crf", self.crf,
               "-pix_fmt", "yuv420p", "-r", str(self.fps), "-t", f"{dur:.3f}", out]
        if split and gameplay:
            half = (self.h // 2) // 2 * 2
            inputs, chain = self._base_inputs(index, scene, dur, self.w, self.h - half, offset)
            gp = self._media(gameplay)
            self._note_upscale(gp, self.w, half)
            gdur = media_duration(gp) or 1.0
            cmd = ["ffmpeg", "-y", *inputs, "-stream_loop", "-1", "-ss", f"{offset % gdur:.3f}",
                   "-i", gp, "-filter_complex",
                   f"[0:v]{chain}[top];[1:v]{_cover(self.w, half)},fps={self.fps}[bot];"
                   f"[top][bot]vstack=inputs=2[v]", "-map", "[v]", *enc]
        else:
            if split:
                self.warnings.append("Split-Screen ohne Gameplay-Datei — Szene im Vollbild gerendert.")
            inputs, chain = self._base_inputs(index, scene, dur, self.w, self.h, offset)
            cmd = ["ffmpeg", "-y", *inputs, "-vf", chain, *enc]
        run_ffmpeg(cmd, f"Szene {index + 1}")

    # ------------------------------------------------------------ Captions
    def _scene_words(self, scene: dict, start: float, speech: float) -> list[Word]:
        timed = scene.get("words") or self._tts_words.get(scene["id"])
        if timed:
            return [Word(text=w["text"], start=start + w["start"], end=start + w["end"])
                    for w in timed]
        tokens = scene["text"].split()
        if not tokens or speech <= 0:
            return []
        weights = [len(t) + 1 for t in tokens]
        total = float(sum(weights))
        words, t = [], start
        for tok, wgt in zip(tokens, weights):
            d = speech * wgt / total
            words.append(Word(text=tok, start=t, end=t + d))
            t += d
        return words

    def build_ass(self, words: list[Word], total: float, headlines: list[tuple[float, float, str]]
                  ) -> tuple[str | None, dict]:
        style = self.p["captions"]["style"]
        scale = 1080.0 / min(self.w, self.h)
        vw, vh = int(round(self.w * scale)), int(round(self.h * scale))
        overrides = to_caption_overrides(self.brand) if self.p["captions"].get("use_brand") else {}
        if style == "none" or not words:
            cap_style, cap_mode, use_words = "minimal", "standard", []
        else:
            cap_style, cap_mode = CAPTION_MAP[style]
            use_words = words
        ass, info = make_captions(use_words, 0.0, total, mode=cap_mode, style=cap_style,
                                  width=vw, height=vh, overrides=overrides)
        info["studio_style"] = style
        if vh < 1900:  # nicht-Hochformat: Captions näher an den unteren Rand
            ass = re.sub(r"(Style: Caption,.*,2,120,120,)\d+(,1)",
                         lambda m: f"{m.group(1)}{int(vh * 0.1)}{m.group(2)}", ass, count=1)
        font = self.brand.get("font_family") if overrides else None
        if font and _FONT_RE.match(str(font)):
            ass = ass.replace("Style: Caption,Arial,", f"Style: Caption,{font},", 1)
            info["font"] = font
        events = []
        if self.p["visuals"].get("headlines", True):
            for start, end, text in headlines:
                if not text:
                    continue
                y = int(vh * 0.16)
                body = (f"{{\\an8\\fs{int(vw * 0.085)}\\b1\\bord4\\fad(250,200)"
                        f"\\move({vw // 2},{y - 40},{vw // 2},{y},0,350)}}{_escape(text.upper())}")
                events.append(f"Dialogue: 1,{_fmt_ts(start)},{_fmt_ts(end)},Caption,,0,0,0,,{body}")
        if self.p["style"] == "cinematic":
            bar = int(vh * 0.085)
            for an, y in ((7, 0), (1, vh)):
                shape = f"m 0 0 l {vw} 0 l {vw} {bar} l 0 {bar}"
                events.append(
                    f"Dialogue: 0,{_fmt_ts(0)},{_fmt_ts(total)},Caption,,0,0,0,,"
                    f"{{\\an{an}\\pos(0,{y})\\bord0\\shad0\\1c&H000000&\\p1}}{shape}{{\\p0}}")
        if events:
            ass = ass.rstrip("\n") + "\n" + "\n".join(events) + "\n"
        has_content = bool(use_words) or bool(events) or bool(overrides.get("watermark_text"))
        return (ass if has_content else None), info

    # --------------------------------------------------------------- Render
    def plan(self, work: str) -> dict:
        """Voice erzeugen + Zeitplan (Dauer/Start je Szene) berechnen."""
        scenes = self.p["scenes"]
        if not scenes:
            raise StudioError("project_empty", "Das Projekt hat noch keine Szenen.", 409)
        voice = self.resolve_voice()
        entries, timing_sources = [], set()
        for i, scene in enumerate(scenes):
            self._check()
            self.progress(f"Voice {i + 1}/{len(scenes)}")
            wav, speech, source = self._voice_for_scene(scene, voice, work)
            timing_sources.add(source)
            minimum = speech + (0.0 if scene.get("audio_source") else VOICE_PAD)
            dur = max(minimum, scene.get("duration") or 0.0, 0.8) + scene.get("pause_after", 0.0)
            entries.append({"scene": scene, "wav": wav, "speech": speech,
                            "min": minimum, "dur": dur})
            self._scene_wav[scene["id"]] = wav
            self._scene_speech[scene["id"]] = speech
        music_path = None
        beat_info = None
        track = self.p["music"].get("track")
        if track and self.opt.music_mode == "none":
            track = None  # Option „ohne Musik“ gewinnt über einen gespeicherten Titel
        if track:
            try:
                music_path = resolve_music(self.dir, track)
            except StudioError:
                self.warnings.append("Musiktitel nicht gefunden — ohne Musik gerendert.")
        if music_path and self.p["music"].get("beat_sync"):
            beat_info = audio_mod.detect_beats(music_path)
            if beat_info["beats"]:
                snapped = audio_mod.snap_durations(
                    [e["dur"] for e in entries], [e["min"] for e in entries], beat_info["beats"])
                for e, d in zip(entries, snapped):
                    e["dur"] = d
            else:
                self.warnings.append("Kein klarer Beat erkannt — Schnitte nicht synchronisiert.")
        t = 0.0
        for e in entries:
            e["start"] = t
            # auf Frame-Raster runden, damit Bild und Ton nicht auseinanderlaufen
            e["dur"] = max(1, round(e["dur"] * self.fps)) / self.fps if not beat_info else e["dur"]
            t += e["dur"]
        return {"entries": entries, "total": t, "voice": voice, "music_path": music_path,
                "beats": beat_info, "timing": sorted(timing_sources)}

    def render(self, out_path: str) -> dict:
        work = os.path.join(self.dir, "cache", f"work_{new_id()}")
        os.makedirs(work, exist_ok=True)
        try:
            plan = self.plan(work)
            entries, total = plan["entries"], plan["total"]
            listing, words, headlines = [], [], []
            voice_parts = []
            for i, e in enumerate(entries):
                self._check()
                self.progress(f"Szene {i + 1}/{len(entries)} rendern")
                seg = os.path.join(work, f"seg_{i:03d}.mp4")
                self.render_segment(i, e["scene"], e["dur"], seg, e["start"])
                listing.append(concat_entry(seg))
                fitted = os.path.join(work, f"fit_{i:03d}.wav")
                self._fit_wav(e["wav"], fitted, e["dur"])
                voice_parts.append(fitted)
                words.extend(self._scene_words(e["scene"], e["start"], e["speech"]))
                if e["scene"]["visual"]["mode"] in ("motion", "static") or e["scene"].get("headline"):
                    headline = e["scene"].get("headline") or ""
                    if headline:
                        headlines.append((e["start"], e["start"] + min(e["dur"], 3.0), headline))
            concat_txt = os.path.join(work, "concat.txt")
            with open(concat_txt, "w", encoding="utf-8") as fh:
                fh.write("\n".join(listing) + "\n")
            voice_wav = os.path.join(work, "voice.wav")
            with wave.open(voice_wav, "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(44100)
                for part in voice_parts:
                    with wave.open(part, "rb") as wf:
                        out.writeframes(wf.readframes(wf.getnframes()))
            self._check()
            self.progress("Captions, Ton und Export")
            ass, cap_info = self.build_ass(words, total, headlines)
            self._final_pass(concat_txt, voice_wav, plan, ass, total, out_path, work)
            return self._report(out_path, plan, cap_info)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _final_pass(self, concat_txt, voice_wav, plan, ass, total, out_path, work) -> None:
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-i", voice_wav]
        vf = "null"
        if ass:
            ass_path = os.path.join(work, "captions.ass")
            with open(ass_path, "w", encoding="utf-8") as fh:
                fh.write(ass)
            esc = filter_path(ass_path)
            vf = f"ass={esc}"
        filters = [f"[0:v]{vf}[v]"]
        music = plan["music_path"]
        # Ducking nur, wenn die Voice-Spur wirklich Ton enthält (nicht bei "none")
        speech = plan["voice"].get("provider") != "none" or "transcribed" in plan["timing"]
        if music:
            cmd += ["-stream_loop", "-1", "-i", music]
            vol = float(self.p["music"].get("volume", 0.25))
            fade = max(0.0, total - 1.5)
            filters.append(f"[2:a]aresample=44100,volume={vol:.3f},"
                           f"afade=t=out:st={fade:.3f}:d=1.5[m]")
            if speech and self.p["music"].get("ducking", True):
                filters.append("[1:a]asplit=2[vo][sc]")
                filters.append("[m][sc]sidechaincompress=threshold=0.02:ratio=10:"
                               "attack=15:release=350[duck]")
                filters.append("[vo][duck]amix=inputs=2:duration=first:normalize=0[a]")
            else:
                filters.append("[1:a][m]amix=inputs=2:duration=first:normalize=0[a]")
            amap = "[a]"
        else:
            amap = "1:a"
        tmp = out_path + ".part.mp4"
        cmd += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", amap,
                "-c:v", "libx264", "-preset", self.preset, "-crf", self.crf,
                "-pix_fmt", "yuv420p", "-r", str(self.fps),
                "-c:a", "aac", "-b:a", "96k" if self.preview else "160k", "-ar", "44100",
                "-t", f"{total:.3f}", "-movflags", "+faststart", tmp]
        run_ffmpeg(cmd, "Finaler Export")
        os.replace(tmp, out_path)

    def _report(self, out_path: str, plan: dict, cap_info: dict) -> dict:
        info = probe(out_path)
        return {
            "file": os.path.basename(out_path),
            "mode": "preview" if self.preview else "final",
            "rendered_at": now_iso(),
            "project_version": self.p["version"],
            "width": info.width, "height": info.height,
            "duration": round(info.duration, 3), "has_audio": info.has_audio,
            "expected": {"width": self.w, "height": self.h,
                         "duration": round(plan["total"], 3)},
            "bytes": os.path.getsize(out_path),
            "aspect_ratio": self.p["aspect_ratio"], "resolution": self.p["resolution"],
            "options": self.opt.to_dict(),
            "voice": plan["voice"],
            "word_timing": plan["timing"],
            "music": {"track": self.p["music"].get("track") if plan["music_path"] else None,
                      "bpm": (plan["beats"] or {}).get("bpm"),
                      "beat_synced": bool(plan["beats"] and plan["beats"]["beats"])},
            "captions": cap_info,
            "scenes": [{"id": e["scene"]["id"], "start": round(e["start"], 3),
                        "duration": round(e["dur"], 3), "speech": round(e["speech"], 3),
                        "visual_mode": e["scene"]["visual"]["mode"]} for e in plan["entries"]],
            "warnings": self.warnings, "fallbacks": self.fallbacks,
            "costs": self.ledger.summary(),
        }


def render_project(project: dict, project_dir: str, *, mode: str = "final",
                   progress=None, should_cancel=None, voice_override=None) -> dict:
    """Rendert ein Projekt nach `renders/<id>.mp4` und schreibt den Report."""
    render_id = new_id()
    rdir = os.path.join(project_dir, "renders")
    os.makedirs(rdir, exist_ok=True)
    out = os.path.join(rdir, f"{render_id}.mp4")
    renderer = StudioRenderer(project, project_dir, mode=mode, progress=progress,
                              should_cancel=should_cancel, voice_override=voice_override)
    report = renderer.render(out)
    report["render_id"] = render_id
    from .quality import post_render_checks
    report["quality"] = post_render_checks(report)
    write_json_atomic(os.path.join(rdir, f"{render_id}.json"), report)
    return report


def render_scene_preview(project: dict, project_dir: str, scene_id: str, *, progress=None) -> dict:
    """Rendert genau EINE Szene (nach Regeneration) als kurze Vorschau."""
    scene = next((s for s in project["scenes"] if s["id"] == scene_id), None)
    if scene is None:
        raise StudioError("scene_not_found", "Szene nicht gefunden.", 404)
    single = dict(project)
    single["scenes"] = [scene]
    single["music"] = {**project["music"], "beat_sync": False}
    render_id = new_id()
    rdir = os.path.join(project_dir, "renders")
    os.makedirs(rdir, exist_ok=True)
    out = os.path.join(rdir, f"{render_id}.mp4")
    report = StudioRenderer(single, project_dir, mode="preview", progress=progress).render(out)
    report.update({"render_id": render_id, "mode": "scene", "scene_id": scene_id})
    write_json_atomic(os.path.join(rdir, f"{render_id}.json"), report)
    return report


def caption_preview(style: str, aspect_ratio: str, text: str, out_png: str,
                    use_brand: bool = True) -> str:
    """Standbild der Caption-Darstellung (für die Stil-Vorschau im Editor)."""
    project = {"aspect_ratio": aspect_ratio, "resolution": "720p", "style": "clean",
               "captions": {"style": style, "use_brand": use_brand},
               "visuals": {"headlines": False}, "budget_limit_usd": 0, "version": 0}
    work = os.path.dirname(out_png)
    r = StudioRenderer(project, work, mode="preview")
    tokens = (text or "Beispieltext für die Vorschau").split()[:8]
    words = [Word(text=t, start=i * 0.4, end=i * 0.4 + 0.4) for i, t in enumerate(tokens)]
    ass, _ = r.build_ass(words, 4.0, [])
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"gradients=s={r.w}x{r.h}:c0=#1e3a8a:c1=#7c3aed:seed=3:d=2"]
    if ass:
        ass_path = out_png + ".ass"
        with open(ass_path, "w", encoding="utf-8") as fh:
            fh.write(ass)
        esc = filter_path(ass_path)
        cmd += ["-vf", f"ass={esc}"]
    cmd += ["-ss", "0.5", "-frames:v", "1", out_png]
    try:
        run_ffmpeg(cmd, "Caption-Vorschau", timeout=60)
    finally:
        if ass and os.path.exists(out_png + ".ass"):
            os.remove(out_png + ".ass")
    shutil.rmtree(os.path.join(work, "cache"), ignore_errors=True)
    return out_png
