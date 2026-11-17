"""Typisiertes Produktionsmodell eines Studio-Projekts.

`ProductionOptions` ist die EINE Beschreibung dessen, was produziert werden
soll. Dieselbe Instanz entsteht aus der API-Anfrage, wird in `project.json`
gespeichert (Schlüssel `options`) und von Skripterzeugung, Qualitätsprüfung und
Renderer gelesen. Alte Projekte ohne `options` laden mit Defaults.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .errors import StudioError

PLATFORMS = ("generic", "youtube_shorts", "tiktok", "instagram_reels", "x")
# Plattform → (Standard-Seitenverhältnis, empfohlene Maximaldauer in Sekunden)
PLATFORM_PROFILES = {
    "generic": ("9:16", 180),
    "youtube_shorts": ("9:16", 180),
    "tiktok": ("9:16", 180),
    "instagram_reels": ("9:16", 90),
    "x": ("16:9", 140),
}
MEDIA_TYPES = ("motion", "static", "ai_image")
MUSIC_MODES = ("track", "none")


def _text(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


@dataclass
class ProductionOptions:
    platform: str = "generic"
    duration_target: int = 45
    goal: str = ""
    audience: str = ""
    cta: str = ""
    creative_instructions: str = ""
    forbidden_topics: list[str] = field(default_factory=list)
    visual_style: str = ""
    media_type: str = "motion"
    image_animation: bool = True
    voice_model: str = ""
    video_provider: str = ""
    video_model: str = ""
    music_mode: str = "track"

    @classmethod
    def from_dict(cls, data: dict | None, strict: bool = False) -> "ProductionOptions":
        """Baut Optionen aus beliebigen (alten/unvollständigen) dicts.

        strict=True (API-Eingabe): ungültige Auswahlwerte → validation_error.
        strict=False (Laden von Platte): ungültige Werte → Default.
        """
        d = data if isinstance(data, dict) else {}

        def choice(key: str, allowed: tuple, default: str) -> str:
            value = d.get(key)
            if value in (None, ""):
                return default
            if value not in allowed:
                if strict:
                    raise StudioError(
                        "validation_error",
                        f"'{key}' muss einer dieser Werte sein: {', '.join(allowed)}.")
                return default
            return value

        try:
            duration = int(d.get("duration_target") or 45)
        except (TypeError, ValueError):
            if strict:
                raise StudioError("validation_error", "duration_target muss eine Zahl sein.")
            duration = 45
        topics = d.get("forbidden_topics") or []
        if isinstance(topics, str):
            topics = topics.replace("\n", ",").split(",")
        topics = list(dict.fromkeys(_text(t, 60).lower() for t in topics if _text(t, 60)))[:30]
        video_provider = _text(d.get("video_provider"), 40)
        if strict and video_provider not in ("", "none"):
            raise StudioError(
                "provider_unknown",
                "KI-Video-Provider sind noch nicht verfügbar (kein Adapter). "
                "Nutze KI-Bilder (media_type=ai_image) oder eigene Medien.", 409)
        return cls(
            platform=choice("platform", PLATFORMS, "generic"),
            duration_target=max(10, min(duration, 600)),
            goal=_text(d.get("goal"), 300),
            audience=_text(d.get("audience"), 300),
            cta=_text(d.get("cta"), 200),
            creative_instructions=_text(d.get("creative_instructions"), 2000),
            forbidden_topics=topics,
            visual_style=_text(d.get("visual_style"), 120),
            media_type=choice("media_type", MEDIA_TYPES, "motion"),
            image_animation=bool(d.get("image_animation", True)),
            voice_model=_text(d.get("voice_model"), 80),
            video_provider="" if video_provider == "none" else video_provider,
            video_model=_text(d.get("video_model"), 80),
            music_mode=choice("music_mode", MUSIC_MODES, "track"),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def default_aspect_ratio(self) -> str:
        return PLATFORM_PROFILES[self.platform][0]

    def max_seconds(self) -> int:
        return PLATFORM_PROFILES[self.platform][1]

    def find_forbidden(self, text: str) -> list[str]:
        low = (text or "").lower()
        return [t for t in self.forbidden_topics if t and t in low]


def options_of(project: dict) -> ProductionOptions:
    return ProductionOptions.from_dict(project.get("options"))
