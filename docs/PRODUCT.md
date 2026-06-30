# ClipForge AI — Produktdefinition

> **Leitsatz:** Aus langem Video in Minuten exportfertige Shorts — mit
> ehrlicher Performance-Einschätzung statt Viralitäts-Versprechen.
>
> **MVP-Doktrin:** Zuerst ein Tool, das **lokal** läuft und **echte Clips
> exportiert**. Alles, was diesen Kern nicht direkt bedient, wird gestrichen
> oder verschoben.

---

## 1. Das Kernproblem

Wer langes Video produziert (Podcasts, Coaching-Calls, Streams, Talks), sitzt
auf Goldminen ungenutzter Inhalte. Aber:

- **Manuelles Clipping kostet Stunden.** Das beste 30-Sekunden-Stück aus einer
  90-Minuten-Folge zu finden, bedeutet stundenlanges Durchscrubben.
- **Editing-Hürde ist hoch.** Hochformat-Crop, Untertitel, Schnitt — pro Clip
  schnell 20–40 Minuten Handarbeit.
- **Auswahl ist Bauchgefühl.** Welcher Moment trägt? Die meisten raten und
  posten zu wenig oder das Falsche.
- **Existierende Tools** sind teuer, cloud-gebunden (Upload-Pflicht,
  Datenschutz-Sorgen), oder versprechen "viral garantiert" — was unseriös ist.

**Kurz:** Hoher Zeit- und Skill-Aufwand pro Clip × Unsicherheit bei der Auswahl
= zu wenig veröffentlichte Shorts.

---

## 2. Die Lösung

**ClipForge AI** ist eine lokal lauffähige Pipeline, die ein langes Video
nimmt und automatisch:

1. **transkribiert** (Wort-genau, lokal),
2. die **stärksten Momente auswählt**,
3. jedem Clip einen **transparenten Performance-Potential-Score** gibt
   (Hook, Klarheit, Emotion, Tempo, Pointe),
4. fertige **9:16-Clips mit eingebrannten Untertiteln exportiert**,
5. **Plattform-Metadaten** (Titel/Beschreibung/Hashtags) und
   **Hook-Varianten** für A/B-Tests liefert.

**Ehrlichkeits-Prinzip (nicht verhandelbar):** ClipForge AI verspricht **nie**
Viralität. Es maximiert die **Wahrscheinlichkeit** starker Performance über
messbare Signale und macht den Score **erklärbar** (Aufschlüsselung + Begründung
pro Clip).

---

## 3. Wichtigste Zielgruppe für das MVP

Gesamt-Zielgruppe: Creator, Coaches, Podcaster, Streamer, Agenturen,
Unternehmer.

**MVP-Fokus: Podcaster & Solo-Coaches mit Talking-Head-Longform.**

Warum genau diese zuerst (streng begründet):

| Kriterium | Warum Podcaster/Coaches ideal sind |
|---|---|
| **Quellmaterial** | Lange Folgen → viele Clips pro Upload → sofortiger ROI |
| **Bildkomposition** | Reden meist frontal/zentriert → **Center-Crop reicht**, kein Face-Tracking nötig (= kein MVP-Blocker) |
| **Wert liegt im Wort** | Inhalt ist sprachgetrieben → unser transkript-basiertes Scoring greift maximal |
| **Schmerz** | Wenig Editing-Skill, wenig Zeit, hohe Posting-Frequenz gewünscht |
| **Datenschutz** | Lokaler Lauf ohne Cloud-Upload ist für viele ein echtes Kaufargument |

Streamer (Gaming-Overlays), Agenturen (Multi-User, Branding) und reine
B-Roll-Creator kommen **später** — sie brauchen Features, die das MVP bewusst
nicht hat (Face-Tracking, Teams, Templates).

---

## 4. Der perfekte 5-Schritte-Workflow

```
   [1] IMPORT            →  [2] ANALYSE        →  [3] AUSWAHL+SCORE
   Video lokal laden        Lokale Transkription   Top-Clips automatisch
   (Datei)                  (Wort-Timestamps)      gewählt & bewertet
                                                            │
                                                            ▼
   [5] EXPORT            ←  [4] REVIEW
   Fertige 9:16-MP4s        Nutzer sichtet Liste,
   + clips.json             korrigiert ggf. Grenzen
```

1. **Import** — Nutzer wählt eine lokale Videodatei. Kein Account, kein Upload.
2. **Analyse** — Lokale Transkription erzeugt Wort-genaue Timestamps.
3. **Auswahl + Score** — Pipeline bildet Kandidaten, bewertet sie und sortiert
   nach Performance-Potential-Score (mit Aufschlüsselung + Begründung).
4. **Review** — Nutzer sieht die rangierte Liste, Score-Begründungen und kann
   die Top-N festlegen. *(MVP: über CLI-Flags / clips.json; UI folgt.)*
5. **Export** — Fertige 9:16-MP4s mit Untertiteln + `clips.json` mit Metadaten
   und Hook-Varianten landen lokal im Ausgabeordner.

**Der „Aha-Moment" liegt zwischen Schritt 3 und 5:** in Minuten von Rohvideo zu
mehreren postbaren Clips, ohne eine Schnittsoftware zu öffnen.

---

## 5. MVP-Funktionen (das ist drin)

| # | Funktion | Status im Code |
|---|---|---|
| F1 | Lokaler Video-Import + Medienanalyse (ffprobe) | ✅ `ffmpeg_utils.py` |
| F2 | Lokale Transkription mit Wort-Timestamps (faster-whisper) | ✅ `transcribe.py` |
| F3 | Automatische Clip-Auswahl aus dem Transkript | ✅ `segmenter.py` |
| F4 | **Performance-Potential-Score** (Heuristik, transparent) | ✅ `scoring.py` |
| F5 | Optionale Claude-Verstärkung: Begründung, Metadaten, Hook-Varianten | ✅ `scoring.py` (Fallback ohne Key) |
| F6 | 9:16-Export per Center-Crop | ✅ `render.py` |
| F7 | Automatische, eingebrannte Untertitel | ✅ `captions.py` + `render.py` |
| F8 | Plattform-Metadaten (TikTok/Reels/Shorts) | ✅ Datenmodell + LLM-Pfad |
| F9 | Hook-Varianten für A/B-Testing (Generierung) | ✅ `scoring.py` |
| F10 | CLI + maschinenlesbarer Output (`clips.json`) | ✅ `cli.py`, `pipeline.py` |

**MVP-Erfolg = F1–F7 + F10 laufen lokal und exportieren abspielbare Clips.**
F5/F8/F9 sind „nice, sobald API-Key gesetzt", blockieren das MVP aber nicht.

---

## 6. Bewusst NICHT im MVP (gestrichen/verschoben)

Streng aussortiert, weil es den „lokal echte Clips exportieren"-Kern nicht
beschleunigt:

| Verschoben | Warum nicht jetzt |
|---|---|
| **Accounts, Login, Billing, SaaS-Abos** | Kein Nutzwert für lokalen Export; reine Plattform-Last |
| **Cloud-Upload & -Rendering** | Widerspricht lokal-first; Infra-Aufwand ohne MVP-Mehrwert |
| **Direkt-Posten auf TikTok/IG/YT** | OAuth-/API-Pflege, Review-Prozesse — hoher Aufwand, später |
| **Speaker-/Face-Tracking-Reframe** | Center-Crop genügt für Talking-Head-Zielgruppe |
| **Animierte Karaoke-Captions, Emojis, B-Roll** | Politur, kein Kern; verlangsamt MVP |
| **Mehrsprachige Übersetzung/Dubbing** | Eigenes Großprojekt |
| **Team-/Agentur-Features, Brand-Templates** | Andere Zielgruppe, nach Product-Market-Fit |
| **Echte A/B-Performance-Messung** | Braucht Plattform-Analytics-APIs; wir generieren nur Varianten |
| **YouTube-URL-Direktimport** | Rechtliche/Infra-Fragen; lokale Datei reicht zum Start |

> Diese Liste ist eine **Sperrzone**: Tasks daraus gelten als „später", bis das
> MVP die Akzeptanzkriterien (Abschnitt 10) erfüllt.

---

## 7. Spätere SaaS-Vision

Reihenfolge **nach** bestätigtem lokalem MVP:

1. **Thin Web-UI** (Next.js + Tailwind) über demselben Pipeline-Kern: Upload,
   Clip-Galerie mit Scores, Vorschau, Download.
2. **Hosted-Version**: Cloud-Rendering, Job-Queue, Storage — für Nutzer ohne
   lokale Power.
3. **Pro-Features**: Face-Tracking-Reframe, animierte Captions, Brand-Kits.
4. **Distribution**: Geplantes/direktes Posten + echtes Performance-Tracking,
   das den Score über Zeit kalibriert (Feedback-Loop).
5. **Teams/Agenturen**: Mehrbenutzer, Freigaben, Mandanten.

Geschäftsmodell-Hypothese: Free (lokal, limitiert) → Pro (Hosted, mehr
Clips/Features) → Team. **Erst nach MVP validieren.**

---

## 8. Technische Architektur

```
api/clipforge/            # Pipeline-Kern (framework-unabhängig)
  config.py     models.py        ffmpeg_utils.py
  transcribe.py segmenter.py     scoring.py
  captions.py   render.py        pipeline.py   cli.py
api/tests/                # Regressionstests ohne Modelle/Keys/ffmpeg
web/                      # (später) Next.js + Tailwind über denselben Kern
```

- **Sprache/Backend:** Python (FastAPI als späterer Layer) — beste Bindung an
  FFmpeg, Whisper, Datenverarbeitung.
- **Transkription:** `faster-whisper` **lokal** (kein Cloud-Zwang, Datenschutz).
- **Scoring:** Transparente Heuristik als Basis; **Claude** (`claude-sonnet-4-6`)
  als optionale Verstärkung mit hartem Fallback (nie Pipeline-Killer).
- **Medien:** **FFmpeg** für Crop, Untertitel-Einbrennen, Stille-Erkennung.
- **Output:** abspielbare 9:16-MP4 + `clips.json` (maschinenlesbar) +
  `transcript.json`.
- **Frontend (später):** Next.js + TypeScript + TailwindCSS, ruft denselben Kern.

**Architektur-Prinzip:** Der Pipeline-Kern ist UI- und Framework-frei. Jede
Oberfläche (CLI heute, Web später) ist nur ein dünner Adapter darüber.

---

## 9. Risiken und Grenzen

| Risiko / Grenze | Umgang |
|---|---|
| **Score ≠ Garantie** | Wird überall klar kommuniziert; Score ist erklärbare Heuristik, kein auf View-Daten trainiertes Modell |
| **Heuristik-Qualität** | Bewusst transparent & justierbar (Gewichte in `models.py`); LLM verbessert, ersetzt aber kein echtes Feedback |
| **Whisper-Genauigkeit** | Modellgröße konfigurierbar (`tiny`…`large-v3`); kleinere Modelle = schneller, ungenauer |
| **Rechenlast lokal** | Rendering/Transkription brauchen CPU/Zeit; Hosted-Variante später |
| **Center-Crop schneidet ggf. Inhalt ab** | Für Talking-Head ok; Face-Tracking ist Pro-Feature |
| **Sprach-/Domänen-Abdeckung** | Heuristik-Signalwörter aktuell DE/EN; erweiterbar |
| **Datenschutz vs. LLM** | Ohne API-Key bleibt alles lokal; LLM-Pfad ist opt-in |
| **Keine Performance-Messung im MVP** | A/B erzeugt nur Varianten; echte Messung später |

---

## 10. Akzeptanzkriterien für ein lauffähiges MVP

Das MVP gilt als **fertig**, wenn **alle** Punkte erfüllt und reproduzierbar
nachweisbar sind:

- [x] **A1** Läuft vollständig **lokal** ohne Pflicht-Cloud und ohne Account.
- [x] **A2** Akzeptiert eine lokale Videodatei und liest Medieninfos via ffprobe.
- [x] **A3** Erzeugt ein Wort-genaues Transkript lokal (faster-whisper) **oder**
      akzeptiert ein vorhandenes Transkript (Fallback ohne Modell-Download).
- [x] **A4** Wählt automatisch Kandidaten-Clips innerhalb der Längen-Grenzen
      (Default 15–60 s) aus.
- [x] **A5** Vergibt pro Clip einen **Performance-Potential-Score** mit
      Aufschlüsselung (Hook/Klarheit/Emotion/Tempo/Pointe) **und** Begründung;
      sortiert absteigend.
- [x] **A6** Exportiert die Top-N als **abspielbare 9:16-MP4s** mit
      **eingebrannten Untertiteln**.
- [x] **A7** Schreibt `clips.json` (Scores, Metadaten, Hook-Varianten) +
      `transcript.json`.
- [x] **A8** Funktioniert **ohne `ANTHROPIC_API_KEY`** (reine Heuristik) und
      **nutzt** ihn, wenn gesetzt (Metadaten + Hook-Varianten), ohne je zu
      crashen.
- [x] **A9** Kommuniziert klar, dass der Score **keine Viralitäts-Garantie** ist.
- [x] **A10** Hat reproduzierbare Tests/Beispiele, mit denen der Nutzer den
      kompletten Lauf selbst nachstellen kann.

> **Status:** A1–A10 sind durch den aktuellen Pipeline-Kern (`api/clipforge/`)
> erfüllt und verifiziert (siehe `README.md` → „Selbst testen"). Eine optionale
> **Thin Web-UI** ist die nächste Ausbaustufe, aber **kein** MVP-Blocker.

---

### Definition of Done (eine Zeile)
> *„Ein Nutzer legt lokal ein langes Video ab und bekommt ohne Account, ohne
> Cloud und ohne Schnittsoftware mehrere abspielbare, untertitelte 9:16-Clips
> mit erklärbarem Performance-Score heraus."* — **erfüllt.**
