"""Realistische Test-Transkripte für Analyzer-Kalibrierung (Prompt 20).

Kompakt gehalten (kleine Dateien), aber mit genug Substanz, um echte
Kandidaten-Erkennung, Dedup und Score-Verteilung zu prüfen. Vier Profile:

  - de_podcast   : DE Interview/Podcast, mehrere gute Clips + Füller.
  - en_education : EN Educational/Creator, how/why/hooks/takeaways.
  - mixed        : gemischt DE/EN, kurz — darf nicht crashen.
  - weak         : Smalltalk/Füller — soll niedrige Scores erzeugen.

Wörter werden gleichmäßig aus dem Segmenttext abgeleitet (Wort-Timestamps
sind für den Analyzer nicht kritisch; die Segmentgrenzen zählen).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.models import Transcript, TranscriptSegment, Word


def _seg(text: str, start: float, end: float) -> TranscriptSegment:
    toks = text.split()
    words: list[Word] = []
    if toks:
        step = (end - start) / len(toks)
        for i, t in enumerate(toks):
            words.append(Word(text=t, start=start + i * step, end=start + (i + 1) * step))
    return TranscriptSegment(text=text, start=start, end=end, words=words)


def _build(pairs: list[tuple[str, float]], language: str, gap: float = 0.2) -> Transcript:
    """Baut ein Transkript aus (Text, Dauer)-Paaren mit kleinen Sprech-Pausen."""
    segs: list[TranscriptSegment] = []
    t = 0.0
    for text, dur in pairs:
        segs.append(_seg(text, t, t + dur))
        t += dur + gap
    return Transcript(language=language, duration=round(t, 1), segments=segs)


# ==========================================================================
# 1) DE Podcast / Interview — mehrere starke Clips + Füller dazwischen
# ==========================================================================

def de_podcast() -> Transcript:
    pairs = [
        # Füller / Smalltalk-Einstieg (soll NICHT gut scoren)
        ("Ja, schön dass du da bist, wie geht es dir eigentlich so heute?", 6.0),
        ("Ganz gut, ähm, war ein langer Tag, aber passt schon irgendwie.", 6.0),
        # Starker Clip 1: Frage-Hook + These + Payoff
        ("Warum scheitern die meisten Gründer schon im ersten Jahr?", 5.0),
        ("Der eigentliche Fehler ist, dass sie Produkte bauen, die niemand wirklich braucht.", 7.0),
        ("Deshalb ist die wichtigste Frage nicht wie, sondern für wen du das überhaupt machst.", 8.0),
        # Füller-Übergang
        ("Genau, das ist ein guter Punkt, den hört man ja öfter.", 5.0),
        # Starker Clip 2: Bold Claim + Zahl + Loop
        ("Niemand sagt dir das, aber Konsistenz schlägt Talent in fast jedem Fall.", 7.0),
        ("Ich habe dreihundert Videos gepostet, bevor eins wirklich funktioniert hat.", 7.0),
        ("Und das Geheimnis dahinter ist überraschend simpel, gleich mehr dazu.", 6.0),
        # Kontext-abhängiger Clip (soll needs_context flaggen)
        ("Das hat er damals auch schon gesagt, und deshalb hat es funktioniert.", 6.0),
        # Starker Clip 3: How-To + klare Struktur
        ("So baust du in dreißig Tagen deine erste echte Reichweite auf.", 6.0),
        ("Schritt eins: poste jeden Tag zur gleichen Zeit, ohne Ausnahme.", 6.0),
        ("Schritt zwei: analysiere, welcher Hook die meisten Leute stoppt.", 6.0),
        # Füller
        ("Ja, ähm, das ergibt total Sinn, sozusagen.", 4.0),
        # Starker Clip 4: Emotion + Story
        ("Ich war kurz davor, alles hinzuwerfen, weil mir das Geld ausging.", 7.0),
        ("Und genau in dem Moment kam die eine Nachricht, die alles verändert hat.", 7.0),
        ("Das war der Wendepunkt, an dem ich verstanden habe, was wirklich zählt.", 7.0),
        # Starker Clip 5: Meinung / Kontroverse (share potential)
        ("Ehrlich gesagt ist die beste Marketing-Strategie einfach ein besseres Produkt.", 7.0),
        ("Alles andere ist nur teurer Lärm, den am Ende niemand hören will.", 6.0),
        # Payoff / Abschluss
        ("Also merke dir: fang heute an, poste dein erstes Video, warte nicht auf perfekt.", 8.0),
        # Füller-Ausklang
        ("Ja, cool, danke dir, war ein super Gespräch, bis zum nächsten Mal.", 6.0),
    ]
    return _build(pairs, "de")


# ==========================================================================
# 2) EN Educational / Creator — how / why / hooks / takeaways
# ==========================================================================

def en_education() -> Transcript:
    pairs = [
        # Filler intro
        ("Hey everyone, welcome back, so today we're gonna talk about a few things.", 6.0),
        # Strong clip 1: why-hook + insight
        ("Why do most people never actually finish what they start?", 5.0),
        ("The real reason is that they optimize for motivation instead of systems.", 7.0),
        ("A system runs even on the days you feel like doing absolutely nothing.", 7.0),
        # Filler
        ("Yeah, so, um, that's kind of the whole idea basically.", 4.0),
        # Strong clip 2: how-to with steps + number
        ("Here is how you learn any skill twice as fast in ninety days.", 6.0),
        ("Step one: practice the hardest part first, not the part you already enjoy.", 7.0),
        ("Step two: get feedback within twenty four hours, or the lesson fades away.", 7.0),
        # Context-dependent clip
        ("And that is exactly why he told them to do it the other way.", 6.0),
        # Strong clip 3: bold claim + share potential
        ("Honestly, the best productivity advice is to do fewer things on purpose.", 7.0),
        ("Everyone chases more, but focus is the real unfair advantage nobody talks about.", 7.0),
        # Strong clip 4: emotional story
        ("I failed my first three launches and almost quit for good.", 6.0),
        ("Then one small change in how I wrote the first line fixed everything.", 7.0),
        ("That single insight is what I wish someone had told me years ago.", 7.0),
        # Strong clip 5: takeaway / payoff
        ("So the takeaway is simple: start ugly, ship fast, and improve in public.", 7.0),
        ("That is the entire secret, and most creators still ignore it every single day.", 7.0),
        # Filler outro
        ("Alright, um, that's it for today, thanks for watching, see you next time.", 6.0),
    ]
    return _build(pairs, "en")


# ==========================================================================
# 3) Mixed DE/EN — kurz, darf nicht crashen
# ==========================================================================

def mixed() -> Transcript:
    pairs = [
        ("Okay let's start, also fangen wir einfach mal an.", 5.0),
        ("Why is consistency so hard? Warum ist das eigentlich so schwer?", 6.0),
        ("The secret is simple, das Geheimnis ist wirklich simpel.", 6.0),
        ("Du musst jeden Tag posten, even when you don't feel like it.", 6.0),
        ("Deshalb: start today, fang heute an, keine Ausreden mehr.", 6.0),
    ]
    return _build(pairs, "de")


# ==========================================================================
# 4) Weak / Smalltalk — soll niedrige Scores erzeugen
# ==========================================================================

def weak() -> Transcript:
    pairs = [
        ("Ja also ähm, ich weiß auch nicht so genau, irgendwie halt.", 6.0),
        ("Das ist so eine Sache, die man eben so macht, sozusagen.", 6.0),
        ("Und dann, ja, keine Ahnung, das war dann halt so.", 5.0),
        ("Genau, also, das ist eigentlich auch schon alles dazu.", 5.0),
        ("Naja, man müsste da mal schauen, aber ist auch egal.", 5.0),
        ("Ähm, ja, ich glaube das war es dann auch so weit.", 5.0),
    ]
    return _build(pairs, "de")


ALL_FIXTURES = {
    "de_podcast": de_podcast,
    "en_education": en_education,
    "mixed": mixed,
    "weak": weak,
}
