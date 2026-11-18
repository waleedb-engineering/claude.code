"""Provider-Gateway: Registry, Readiness und automatische Stimmenauswahl."""

from __future__ import annotations

from ..errors import StudioError
from .base import (
    AvatarProvider, ImageProvider, PlaceholderProvider, Provider, VideoProvider, VoiceProvider,
    VoiceResult,
)
from .fal import FalAvatar, FalVideo
from .local import (
    EspeakVoice, MacSayVoice, MockImage, MockVoice, PiperVoice, SilentVoice, WindowsSapiVoice,
)
from .remote import ElevenLabsCloneProvider, ElevenLabsVoice, OpenAIImage, OpenAIVoice

# Reihenfolge = Priorität der automatischen Auswahl (lokal vor Cloud).
_VOICES: list[VoiceProvider] = [
    PiperVoice(), MacSayVoice(), WindowsSapiVoice(), EspeakVoice(),
    ElevenLabsVoice(), OpenAIVoice(), MockVoice(), SilentVoice(),
]
_IMAGES: list[ImageProvider] = [OpenAIImage(), MockImage()]
_VIDEOS: list[VideoProvider] = [FalVideo()]
_AVATARS: list[AvatarProvider] = [FalAvatar()]
_CLONES: list[Provider] = [ElevenLabsCloneProvider()]
_PLACEHOLDERS: list[Provider] = [
    PlaceholderProvider(
        "face_swap", "face_swap", "Face Swap",
        "Nicht verfügbar — Entscheidung offen (Identitätsprüfung und Kennzeichnung nötig), "
        "siehe docs/WAS_ICH_BRAUCHE.md.", "studio_face_swap"),
]


def all_providers() -> list[Provider]:
    return [*_VOICES, *_IMAGES, *_VIDEOS, *_AVATARS, *_CLONES, *_PLACEHOLDERS]


def readiness() -> list[dict]:
    return [p.info() for p in all_providers()]


def get_voice(provider_id: str) -> VoiceProvider:
    for p in _VOICES:
        if p.id == provider_id:
            return p
    raise StudioError("provider_unknown", f"Unbekannter Voice-Provider '{provider_id}'.", 400)


def get_video(provider_id: str) -> VideoProvider:
    for p in _VIDEOS:
        if p.id == provider_id:
            return p
    raise StudioError("provider_unknown", f"Unbekannter Video-Provider '{provider_id}'.", 400)


def get_avatar(provider_id: str) -> AvatarProvider:
    for p in _AVATARS:
        if p.id == provider_id:
            return p
    raise StudioError("provider_unknown", f"Unbekannter Avatar-Provider '{provider_id}'.", 400)


def get_image(provider_id: str) -> ImageProvider:
    for p in _IMAGES:
        if p.id == provider_id:
            return p
    raise StudioError("provider_unknown", f"Unbekannter Bild-Provider '{provider_id}'.", 400)


def require_ready(provider: Provider) -> None:
    state, hint = provider.status()
    if state != "ready":
        raise StudioError(
            "provider_not_configured",
            f"Provider '{provider.label}' ist nicht einsatzbereit. {hint}".strip(), 409,
            {"provider": provider.id, "status": state})


def select_voice(language: str, tone: str = "", provider_id: str | None = None,
                 voice_id: str | None = None, allow_paid: bool = False) -> dict:
    """Wählt Provider + Stimme nach Sprache und Ton.

    Ohne Vorgabe ("auto"): erster einsatzbereiter Provider, der die Sprache
    kann — lokale zuerst, kostenpflichtige nur mit `allow_paid`. Fällt immer
    auf `none` (Stille) zurück, damit ein Render nie an der Stimme scheitert.
    """
    lang = language if language else "de"
    candidates: list[VoiceProvider]
    if provider_id and provider_id != "auto":
        candidates = [get_voice(provider_id)]
        require_ready(candidates[0])
    else:
        candidates = [p for p in _VOICES
                      if p.status()[0] == "ready" and (allow_paid or not p.paid)
                      and p.id != "mock"]
    for prov in candidates:
        if lang not in prov.languages and prov.id != "none":
            continue
        voices = prov.voices(lang)
        if not voices:
            continue
        chosen = next((v for v in voices if v["id"] == voice_id), None)
        if chosen is None and tone:
            chosen = next((v for v in voices if v["tone"] == tone), None)
        chosen = chosen or voices[0]
        return {"provider": prov.id, "voice_id": chosen["id"], "label": chosen["label"],
                "tone": chosen["tone"], "language": lang,
                "produces_speech": prov.produces_speech}
    return {"provider": "none", "voice_id": "silent", "label": "Stille", "tone": "neutral",
            "language": lang, "produces_speech": False}


__all__ = [
    "AvatarProvider", "ImageProvider", "Provider", "VideoProvider", "VoiceProvider",
    "VoiceResult", "all_providers", "get_avatar", "get_image", "get_video", "get_voice", "readiness", "require_ready", "select_voice",
]
