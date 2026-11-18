"""Szenenübergänge mit FFmpeg-xfade.

Zeitmodell: Ein Übergang in Szene i+1 beginnt genau an deren Startzeit und
dauert d Sekunden. Dafür wird Szene i um d verlängert gerendert; die
Gesamtlänge, die Stimme und die Untertitel bleiben dadurch unverändert.
Bei Beat-Sync liegen die Szenenstarts auf Beats — der Übergang startet also
auf dem Beat.
"""

from __future__ import annotations

# Benutzer-Name → xfade-Transition
XFADE = {
    "fade": "fade",
    "fadeblack": "fadeblack",
    "zoom": "zoomin",
    "slide": "slideleft",
    "slideup": "slideup",
    "smooth": "smoothleft",
    "wipe": "wipeleft",
    "dissolve": "dissolve",
    "circle": "circleopen",
}

# "auto": Auswahl passend zum Videostil (rotierend, damit es nicht eintönig wirkt)
AUTO_BY_STYLE = {
    "cinematic": ("fadeblack", "dissolve", "fade"),
    "energetic": ("zoom", "slide", "smooth", "wipe"),
    "minimal": ("fade",),
    "clean": ("fade", "smooth", "slide"),
}


def resolve(scene_transition: str, project: dict, index: int) -> str:
    """Effektiver Übergang in Szene `index` (0 = erste Szene, nie ein Übergang)."""
    if index == 0:
        return "cut"
    choice = scene_transition or "auto"
    if choice == "auto":
        choice = (project.get("transitions") or {}).get("style") or "cut"
    if choice == "auto":
        pool = AUTO_BY_STYLE.get(project.get("style") or "clean", AUTO_BY_STYLE["clean"])
        choice = pool[(index - 1) % len(pool)]
    return choice if choice in XFADE else "cut"


def plan(project: dict, entries: list[dict], fps: int) -> list[tuple[str, float]]:
    """→ je Szene (Übergang hinein, Dauer). Dauer passt in beide Nachbarszenen."""
    base = float((project.get("transitions") or {}).get("duration") or 0.4)
    out: list[tuple[str, float]] = []
    for i, e in enumerate(entries):
        name = resolve(e["scene"].get("transition", "auto"), project, i)
        if name == "cut":
            out.append(("cut", 0.0))
            continue
        # höchstens 40 % der kürzeren Nachbarszene, auf das Frame-Raster gerundet
        limit = 0.4 * min(e["dur"], entries[i - 1]["dur"])
        d = min(base, limit)
        d = round(d * fps) / fps
        out.append((name, d) if d >= 2 / fps else ("cut", 0.0))
    return out


def extensions(trans: list[tuple[str, float]]) -> list[float]:
    """Wie viel länger Szene i gerendert werden muss (Übergang in Szene i+1)."""
    return [trans[i + 1][1] if i + 1 < len(trans) else 0.0 for i in range(len(trans))]


def filtergraph(trans: list[tuple[str, float]], starts: list[float], fps: int) -> str:
    """xfade-Kette über alle Segmente → Ausgang [vx]."""
    parts = [f"[{i}:v]fps={fps},settb=AVTB,setpts=PTS-STARTPTS[s{i}]" for i in range(len(trans))]
    last = "[s0]"
    for i in range(1, len(trans)):
        name, d = trans[i]
        label = f"[x{i}]"
        if name == "cut" or d <= 0:
            # harter Schnitt: Segment i-1 wurde nicht verlängert → einfach anhängen
            parts.append(f"{last}[s{i}]concat=n=2:v=1:a=0{label}")
        else:
            parts.append(f"{last}[s{i}]xfade=transition={XFADE[name]}:"
                         f"duration={d:.4f}:offset={starts[i]:.4f}{label}")
        last = label
    parts.append(f"{last}null[vx]")
    return ";".join(parts)
