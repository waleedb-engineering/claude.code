# Anbieter- und Modell-Matrix

Live-Ansicht: **Studio → Einrichtung → Anbieter & Modelle** bzw.
`GET /api/studio/provider-matrix`. Kosten/Limits sind Richtwerte (Stand 11/2026).

| Bereich | Anbieter | Kosten | Schlüssel | Live verifiziert | Fallback |
|---|---|---|---|---|---|
| Stimme | eSpeak NG | 0 | – | ja | – |
| Stimme | Piper, macOS `say`, Windows SAPI | 0 | – | nein (Modelle/OS fehlten) | eSpeak |
| Stimme | ElevenLabs, OpenAI TTS | nach Zeichen | ja | nein | Piper/eSpeak |
| Stimmklon | ElevenLabs | Tarif | ja | nein | – |
| Bild | OpenAI Images | je Bild | ja | nein | Motion |
| Video | fal.ai (Kling) | ca. 0,05–0,30 USD/s | `FAL_KEY` | nein | Bild → Motion |
| Avatar | fal.ai (SadTalker) | ca. 0,02–0,10 USD/s | `FAL_KEY` | nein | Standbild |
| Face Swap | fal.ai | ca. 0,05 USD/Bild | `FAL_KEY` | nein | – |
| KI-Assistent | Regelbasiert | 0 | – | ja | – |
| KI-Assistent | Ollama (lokal) | 0 | – | nein (kein Modell in der Testumgebung; Status/Probelauf in der Einrichtung) | Regeln (automatisch) |
| KI-Assistent | Claude, OpenAI | Cent je Nachricht | ja | nein | Regeln/Ollama |
| Übersetzung | Argos (lokal) | 0 | – | nein (Modell-Download gesperrt) | manuell |
| Übersetzung | Claude | Cent je Aufruf | ja | nein | manuell |
| Stock | Pexels, Pixabay | 0 | ja (kostenlos) | nein | eigene Mediathek |
| Trends | YouTube Data API | 0 (Kontingent) | ja (kostenlos) | nein | manuelle Ideen |
| Live-Chat | YouTube Data API (liveChatMessages) | 0 (≈ 5 Einheiten/Abfrage, 10 000/Tag) | `YOUTUBE_API_KEY` | nein (nachgebildete API getestet) | Chat-Export nach dem Stream |
| Live-Chat | Twitch-IRC (anonym) | 0 | – | nein (lokaler IRC-Testserver) | Chat-Export (TwitchDownloader) |
| LLM | Gemini | Gratis-Kontingent möglich | ja | – | – (verwaltbar, **noch nicht genutzt**) |
| Modelle | Hugging Face | 0 | optional | – | – (verwaltbar, **noch nicht genutzt**) |

Weitere rechtmäßig kostenlose Optionen (geprüft, nicht eingebaut): Gemini-
Gratiskontingent für Text, Hugging Face Inference (Rate-Limits), lokale Modelle
über Ollama (Llama, Qwen, Mistral) — Letzteres ist der empfohlene kostenlose Weg
für den KI-Assistenten.

Regeln: Schlüssel nur verschlüsselt serverseitig, nie im Frontend; jede
kostenpflichtige Aktion braucht Bestätigung und Projektbudget; das Budget ist
eine Schätzung, keine Ausgabengrenze beim Anbieter.
