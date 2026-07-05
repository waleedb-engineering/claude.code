# ClipForge AI — Beta-Tester-Guide

## 1. Willkommen

Schön, dass du ClipForge testest. ClipForge macht aus einem langen Video
automatisch mehrere kurze, vertikale Clips (9:16) mit Untertiteln — für
YouTube Shorts, TikTok und Instagram Reels gedacht.

Das hier ist eine **geschlossene Beta**. Es läuft komplett auf deinem
eigenen Rechner — kein Account, keine Cloud, deine Videos verlassen deinen
Computer nicht (außer du aktivierst bewusst eine der optionalen
Cloud-Funktionen). Manche Dinge sind noch nicht fertig — dafür bist du ja da.

Danke, dass du dir die Zeit nimmst.

---

## 2. Voraussetzungen

Du brauchst auf deinem Rechner:

- **Python** (Version 3.10 oder neuer)
- **Node.js** (Version 20 oder neuer)
- **ffmpeg** (das Werkzeug, das die Videos schneidet — muss separat
  installiert sein, z. B. `brew install ffmpeg` auf dem Mac oder
  `apt install ffmpeg` auf Linux)

Kein Konto, kein API-Key, keine Kreditkarte nötig, um loszulegen.

---

## 3. Installation

1. Terminal öffnen, in den entpackten ClipForge-Ordner wechseln.
2. Einmalig ausführen:
   ```bash
   ./scripts/setup_local.sh
   ```
3. Das Skript installiert alles Nötige und meldet sich am Ende mit einer
   Übersicht — grüne Häkchen sind gut. Steht dort etwas mit „FAIL" (rot),
   fehlt noch eine Voraussetzung (meistens ffmpeg) — die Meldung sagt dir,
   was fehlt.

---

## 4. Start

```bash
./scripts/start_local.sh
```

Ein Befehl startet alles. Nach ein paar Sekunden siehst du im Terminal:

```
Öffnen: http://127.0.0.1:3000/upload
```

Diesen Link im Browser öffnen — fertig. Zum Beenden: im selben Terminal
**Strg+C** drücken.

---

## 5. Erster Upload

1. Auf der Upload-Seite ein Video auswählen (per Klick oder Drag & Drop).
2. Unten auf **„Videos analysieren"** klicken.
3. Du wirst zur Job-Seite weitergeleitet — dort läuft die Analyse live mit
   Fortschrittsanzeige. Das dauert je nach Videolänge und Rechner ein paar
   Minuten.
   - **Erster Job dauert länger:** ClipForge lädt beim allerersten Mal ein
     Spracherkennungs-Modell herunter (~140 MB, einmalig).

---

## 6. Clips ansehen

Sobald der Job fertig ist, erscheinen die Clips als Karten:

- **Video-Vorschau** direkt abspielbar
- **Score** — eine Einschätzung, wie stark der Clip wahrscheinlich
  performt (keine Garantie, nur ein Hinweis)
- **Content-Paket** — vorgeschlagener Titel, Hashtags, Beschreibungstexte
  für die jeweilige Plattform (aufklappen, um sie zu sehen/kopieren)
- **MP4 herunterladen** — lädt den fertigen Clip auf deinen Rechner

---

## 7. Re-render

Gefällt dir der Zuschnitt eines Clips nicht ganz? Auf **„Bearbeiten"**
klicken:

1. Start-/Endzeit anpassen (Schieberegler/Zahlenfelder).
2. Untertitel-Stil und Bildausrichtung nach Wunsch ändern.
3. **„Neu rendern"** klicken — erzeugt eine neue Version, ohne den
   ursprünglichen Clip zu löschen.

---

## 8. Publishing Planner

Auf einer Clip-Karte **„Publishing vorbereiten"** klicken, um einen
**lokalen Entwurf** anzulegen — Titel, Caption, Hashtags editierbar. Das ist
**kein echter Upload**, sondern eine Planungshilfe: du bekommst am Ende ein
ZIP-Paket (Video + fertige Texte) zum **manuellen** Hochladen auf der
jeweiligen Plattform.

Unter **„Publishing"** (oben in der Navigation) siehst du alle Entwürfe über
alle Videos hinweg an einem Ort, mit Suche und Filter.

---

## 9. YouTube Dry-Run

Bei einem YouTube-Shorts-Entwurf gibt es einen Button **„YouTube Dry-Run
prüfen"**. Er zeigt dir **genau, was hochgeladen würde** (Titel,
Beschreibung, technische Checks) — **ohne** tatsächlich etwas hochzuladen.
Reiner Vorschau-Modus, komplett gefahrlos.

Es gibt in dieser Beta auch einen Pfad für einen **echten, aber
ausschließlich privaten** YouTube-Upload (nur du selbst siehst das Video
danach). Er ist **standardmäßig deaktiviert** und erfordert eine bewusste,
mehrstufige Bestätigung. Für die Beta empfehlen wir: **beim Dry-Run
bleiben**, außer wir bitten dich ausdrücklich um einen echten Testupload.

---

## 10. Was aktuell NICHT funktioniert

- **Kein öffentlicher oder „Unlisted"-Upload** — YouTube-Upload ist
  ausschließlich **privat**.
- **Kein TikTok- oder Instagram-Auto-Upload** — nur lokale Text-/Video-Pakete
  zum manuellen Hochladen.
- **Kein automatisches Planen/Posten** — nichts passiert von selbst zu einer
  bestimmten Uhrzeit.
- **Kein Mehrbenutzer-Betrieb** — ClipForge ist für einen einzelnen Nutzer
  auf einem Rechner gedacht.
- Der echte private YouTube-Upload ist implementiert, aber noch nicht mit
  einem echten YouTube-Konto vollständig durchgetestet — sei hier besonders
  vorsichtig und melde uns jede Auffälligkeit.

Ausführliche, laufend gepflegte Liste: [`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md).

---

## 11. Fehler melden

Am hilfreichsten für uns:

1. **Was hast du versucht?** (z. B. „Video hochgeladen, dann auf Bearbeiten
   geklickt")
2. **Was ist passiert?** (die genaue Fehlermeldung, am besten als Text oder
   Screenshot)
3. **Was hast du erwartet?**
4. Die Ausgabe von:
   ```bash
   python3 scripts/clipforge_doctor.py
   ```

Je genauer die Schritte zum Nachstellen, desto schneller können wir es
reparieren.

---

## 12. Welche Logs geteilt werden dürfen

Unbedenklich zu teilen:

- Die Terminal-Ausgabe von `start_local.sh` bzw. `clipforge_doctor.py`
- Fehlermeldungen, die **im Browser** angezeigt werden
- Screenshots der ClipForge-Oberfläche

Diese enthalten keine Passwörter oder Zugangsdaten — ClipForge gibt so
etwas grundsätzlich nirgends aus (auch nicht in Logs oder Fehlermeldungen).

---

## 13. Welche Daten niemals geteilt werden dürfen

Bitte **niemals** öffentlich teilen (z. B. in einem GitHub-Issue, Screenshot
oder Chat):

- Den Inhalt deiner `.env`-Datei
- Alles, was wie ein Google-„Client-Secrets"-JSON aussieht
  (`client_secret.json` o. ä.)
- Irgendetwas, das mit `ya29.`, `1//`, `GOCSPX-` oder `Bearer ` beginnt —
  das sind Formate echter Google-Zugangstoken
- Deine eigenen Videos, falls sie privat/vertraulich sind (das ist dein
  Content, nicht unserer)

Falls du dir unsicher bist, ob etwas ein Geheimnis ist: **lieber nicht
teilen** und uns kurz fragen.

---

## 14. Reset

Alles an Job-Daten zurücksetzen, ohne ClipForge neu zu installieren:

```bash
# ClipForge vorher stoppen (Strg+C im Start-Terminal), dann:
rm -rf api/jobs/*
```

Das entfernt alle hochgeladenen Videos und erzeugten Clips lokal — nichts
davon war je irgendwo hochgeladen.

---

## 15. Uninstall / Entfernen

ClipForge installiert nichts systemweit. Zum vollständigen Entfernen reicht:

1. ClipForge stoppen (Strg+C).
2. Den ClipForge-Ordner löschen.

Das war's — keine Registry-Einträge, keine Hintergrunddienste, keine
versteckten Dateien außerhalb des Ordners (mit einer Ausnahme: falls du den
YouTube-OAuth-Testpfad genutzt hast, liegt ein Token im
Betriebssystem-Schlüsselbund/Keychain — dafür gibt es in der App den Button
„YouTube-Token löschen").

---

Danke fürs Testen. Bei Fragen: siehe [`docs/LOCAL_BETA_GUIDE.md`](LOCAL_BETA_GUIDE.md)
für die technischere Variante dieser Anleitung.
