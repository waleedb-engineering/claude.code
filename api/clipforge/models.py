"""Datenmodelle der ClipForge-Pipeline.

Bewusst als dataclasses gehalten (kein Framework-Zwang), damit Pipeline-Kern
und CLI unabhängig von FastAPI testbar bleiben.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Word:
    """Ein einzelnes Wort mit Wort-Level-Timestamps (aus der Transkription)."""

    text: str
    start: float  # Sekunden
    end: float    # Sekunden

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class TranscriptSegment:
    """Ein zusammenhängendes Transkript-Segment (Satz/Phrase)."""

    text: str
    start: float
    end: float
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    """Vollständige Transkription eines Videos."""

    language: str
    duration: float
    segments: list[TranscriptSegment] = field(default_factory=list)

    @property
    def words(self) -> list[Word]:
        out: list[Word] = []
        for seg in self.segments:
            out.extend(seg.words)
        return out

    @property
    def full_text(self) -> str:
        return " ".join(seg.text.strip() for seg in self.segments).strip()


@dataclass
class CandidateClip:
    """Ein Kandidat für einen Kurzclip, abgeleitet aus dem Transkript."""

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class ScoreBreakdown:
    """Transparente Aufschlüsselung des Performance-Potential-Scores.

    WICHTIG: Dies ist eine Heuristik + LLM-Einschätzung, KEINE Garantie für
    Viralität. Jeder Teilwert liegt in [0, 100].
    """

    hook: float          # Wie stark zieht der Einstieg (erste Sekunden)?
    clarity: float       # Ist die Aussage in sich verständlich/abgeschlossen?
    emotion: float       # Emotionale Ladung / Spannung
    pacing: float        # Sprechtempo & Dichte (nicht zu langsam, nicht gehetzt)
    payoff: float        # Gibt es einen befriedigenden Abschluss/Pointe?

    weights: dict[str, float] = field(
        default_factory=lambda: {
            "hook": 0.35,
            "clarity": 0.20,
            "emotion": 0.20,
            "pacing": 0.10,
            "payoff": 0.15,
        }
    )

    def total(self) -> float:
        parts = {
            "hook": self.hook,
            "clarity": self.clarity,
            "emotion": self.emotion,
            "pacing": self.pacing,
            "payoff": self.payoff,
        }
        return round(sum(parts[k] * self.weights.get(k, 0.0) for k in parts), 1)


@dataclass
class PlatformMetadata:
    """Plattform-spezifische Metadaten für einen Clip."""

    title: str
    description: str
    hashtags: list[str] = field(default_factory=list)


@dataclass
class HookVariant:
    """Eine Varianten-Idee für den Hook/Titel (für A/B-Testing)."""

    label: str       # z.B. "Frage", "Bold Claim", "Zahl"
    text: str


@dataclass
class ScoredClip:
    """Ein bewerteter, render-fähiger Clip — das zentrale Output-Objekt."""

    start: float
    end: float
    text: str
    score: float
    breakdown: ScoreBreakdown
    reason: str                                  # Begründung (LLM oder Heuristik)
    metadata: dict[str, PlatformMetadata] = field(default_factory=dict)
    hook_variants: list[HookVariant] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)
    scorer: str = "heuristic"                    # "heuristic" | "llm" | "llm+heuristic"
    output_path: str | None = None               # gesetzt nach dem Rendering
    silence_info: dict[str, Any] | None = None   # Schnitt-Metriken (nach Render)
    caption_info: dict[str, Any] | None = None   # Caption-Metriken (nach Render)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration"] = self.duration
        # Wörter aus dem JSON-Export herauslassen (zu groß / redundant)
        d.pop("words", None)
        return d
