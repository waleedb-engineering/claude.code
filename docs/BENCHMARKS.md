# Benchmarks (gemessen, 20.11.2026)

## Hardware / Software der Messung

| | |
|---|---|
| Umgebung | Cloud-Container (Linux 6.18, x86_64), **4 vCPU, 15 GB RAM**, keine GPU |
| Software | Python 3.13, FFmpeg 6.1.1 (libx264), NumPy |
| Medien | **synthetisch** erzeugt mit `scripts/make_stream_benchmark.py` (FFmpeg lavfi, Seed 2026), keine Fremdinhalte |

Ein MacBook mit Apple Silicon ist für Decoding/Encoding typischerweise schneller
(VideoToolbox wird von ClipForge aktuell **nicht** genutzt, libx264 läuft auf CPU).
Messwerte auf dem Mac des Nutzers stehen noch aus.

## Stream-Analyse (Signal-Messung über die ganze Aufnahme)

| Aufnahme | Dauer | Messzeit | Echtzeit-Faktor | Spitzen-RAM |
|---|---|---|---|---|
| 640×360, 30 fps, 3 Dateien | je 10 min | je 7,4 s | **81×** | – |
| 1280×720, 30 fps | 60 min | 117 s | **30,7×** | FFmpeg ≤ 440 MB, Python ~50 MB |

Hochrechnung (linear, nicht gemessen): 3 h 720p ≈ 6 min, 3 h 1080p ≈ 12–15 min auf
dieser Hardware. Die Messung wird in `signals.json` gecacht; eine erneute Analyse
(andere Gewichte, Clip-Längen, Chat-Verzögerung) dauert dann **< 1 s**.
Transkription läuft nur in Kandidaten-Fenstern (±40 s); faster-whisper wurde hier
nicht gemessen (Modell-Download in dieser Umgebung gesperrt).

## Erkennungsqualität auf dem synthetischen Testsatz

Nur ein **Pipeline-Test** — synthetische Ereignisse sind deutlich klarer als echte
Streams. Diese Zahlen sind KEIN Qualitätsnachweis für echte Streams.

| Testsatz | Ereignisse | Präzision | Recall | F1 | Ø Zeitabw. | Ereignis vollständig im Clip |
|---|---|---|---|---|---|---|
| 3 × 10 min (1 ohne Chat) | 10 | 0,71 | 1,00 | 0,83 | 1,0 s | 100 % |
| 60 min, max. 8 Clips (Standard) | 21 | 1,00 | 0,38 | 0,55 | 1,4 s | 100 % |
| 60 min, max. 25 Clips | 21 | 0,84 | 1,00 | 0,91 | 1,5 s | 100 % |

Erkenntnis: Bei langen Streams begrenzt **„max. Clips“ (Standard 8)** den Recall,
nicht die Erkennung. Für mehrstündige Streams in der Oberfläche höher stellen
(bis 20). Fehlalarme entstehen v. a. durch Chat-Spam-Wellen (neutraler Text,
hohe Rate) — auf echten Daten mit `python -m clipforge.stream.evaluate --tune`
nachjustieren.

Reproduzieren:

```bash
python scripts/make_stream_benchmark.py /tmp/bench --minutes 10 --count 3 --no-chat-every 3
cd api && python -m clipforge.stream.evaluate /tmp/bench --max-clips 25 --json /tmp/bench/result.json
```

## Rendering

| Vorgang | Ergebnis-Video | Dauer |
|---|---|---|
| Studio-Vorschau (360×640) | 38 s | 3,9 s |
| Studio-Final 1080×1920 | 38 s | 24,3 s |
| Studio-Final + Zoom (einfahrend) + Lautheit (2 Durchgänge) | 38 s | 28,0 s (+15 %) |
| Stream-Clip 30 s, 9:16 Smart-Reframe aus 60-min-720p-Quelle | 30 s | 9,4 s |

## Engpässe und Folgerungen

1. **Video-Decoding** dominiert die Stream-Analyse (720p ≈ 4× langsamer als 360p).
   Möglich: Hardware-Decoding (`-hwaccel videotoolbox/cuda`) — erst nach Messung
   auf dem Zielrechner einbauen.
2. **Final-Render 1080p** ≈ 0,6× Echtzeit (libx264 `medium`/CRF). Für Entwürfe die
   Vorschau nutzen (6× schneller).
3. **Speicher** unkritisch (< 0,5 GB je FFmpeg-Prozess); die Task-Queue rendert
   mit begrenzter Parallelität, der Live-Modus schneidet max. einen Clip pro Takt.
4. **Dateiverwaltung**: Signal-Cache je Stream ≈ 4 Werte × Sekunden (3 h ≈ 1 MB JSON).


## Production-Runde (21.11.2026, gleiche Hardware)

| Messung | Ergebnis |
|---|---|
| Stream-Messung 10 min 360p mit Audio-Ereignis-Merkmalen | 7,5 s je Datei (**80×** Echtzeit, unverändert) |
| Stream-Messung 60 min 720p mit Audio-Ereignis-Merkmalen | 94 s (**38×** Echtzeit; vorher 117 s — Schwankung des Containers, nicht als Verbesserung werten) |
| F1 synthetisch, `explain` vs. `rank` | 0,833 / 0,833 (3×10 min), 0,913 / 0,913 (60 min) — kein Unterschied messbar |
| CPU-Kodierung libx264 1080p, 10 s Testbild | 4,4 s (2,27× Echtzeit) |
| Hardware-Encoder | NVENC/QSV/VAAPI im FFmpeg-Build gelistet, Probelauf scheitert (keine GPU) → nicht genutzt |
| 3-h-Stream 360p (66 Ereignisse, synthetisch) | Messung 133 s (81×), RAM ≤ 148 MB FFmpeg; F1 0,47 mit max. 20 Highlights, 0,90 mit 80 → Obergrenze auf 60 angehoben |
