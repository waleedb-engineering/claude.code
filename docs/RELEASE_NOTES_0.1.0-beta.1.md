# ClipForge AI — Release Notes 0.1.0-beta.1

## 1. Was ist ClipForge?

Ein lokales Tool, das aus einem langen Video (Podcast, Talk, Coaching-Call)
automatisch mehrere kurze, vertikale Clips (9:16) mit eingebrannten
Untertiteln erzeugt — für YouTube Shorts, TikTok und Instagram Reels
gedacht. Läuft komplett auf dem eigenen Rechner, kein Account nötig.

## 2. Was kann diese Beta?

- Video hochladen (einzeln oder als Batch), automatische Clip-Auswahl aus
  dem Transkript
- Lokale Transkription (faster-whisper) oder ein mitgeliefertes Transkript
  nutzen
- Wortgenaue Karaoke-Untertitel, Silence-Removal, Smart-Reframe
  (Gesichtserkennung, statischer Crop pro Clip), Brand Kit
- Performance-Potential-Score mit nachvollziehbarer Aufschlüsselung
  (regelbasiert, optional durch Claude verstärkt)
- Automatisch generierte Titel/Hashtags/Beschreibungstexte pro Clip
- Web-Editor zum Nachjustieren einzelner Clips + Re-Render
- Publishing Planner (lokale Entwürfe, plattformübergreifende Übersicht,
  Duplizieren)
- YouTube Dry-Run (zeigt, was hochgeladen würde — ohne es zu tun)
- Ein echter, ausschließlich **privater** YouTube-Upload-Pfad (standardmäßig
  deaktiviert, mehrstufig bestätigungspflichtig)
- One-Command Setup/Start, Environment Doctor, Browser-E2E-Testsuite

## 3. Was sollte getestet werden?

- Der komplette Kernablauf: Upload → Job beobachten → Clips ansehen →
  Editor/Re-Render → Publishing-Entwurf → YouTube Dry-Run
- Verhalten bei ungewöhnlichen Eingaben (sehr lange/kurze Videos, viele
  Dateien auf einmal, ungewöhnliche Formate)
- Ob Fehlermeldungen verständlich sind, wenn etwas schiefgeht
- Das Setup/Start-Erlebnis selbst (ist die Anleitung klar? Bricht irgendwo
  etwas unerwartet ab?)
- Auf ausdrückliche Bitte: ein einzelner, bewusster manueller
  YouTube-Real-Test (siehe unten)

## 4. Was ist bewusst deaktiviert?

- Öffentlicher oder „Unlisted"-YouTube-Upload — existiert nicht, kein
  Umgehen möglich
- Automatischer TikTok-/Instagram-Upload — nur lokale Pakete zum manuellen
  Hochladen
- Automatisches Scheduling/Posting — kein Hintergrunddienst
- Echter YouTube-Upload standardmäßig **aus**
  (`CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=false`) — auch mit konfigurierten
  Credentials passiert ohne diese bewusste Einstellung nichts automatisch

## 5. Wichtigste Sicherheitsregeln

- Kein Upload ohne explizite, mehrstufige Bestätigung
  (Checkbox + Eingabe von `UPLOAD_PRIVATE`)
- Tokens/Secrets werden **nie** im Browser-DOM, in Logs oder
  API-Antworten ausgegeben — nur Status-Booleans
- YouTube-Tokens liegen ausschließlich im OS-Keychain, nie als Klartext-Datei
- Jeder automatisierte Test läuft ohne echte Google-Calls und ohne echten
  Upload

## 6. Daten bleiben lokal, soweit aktuelle Architektur

Videos, Clips, Transkripte und Publishing-Entwürfe liegen ausschließlich in
`api/jobs/` auf deinem Rechner. Es gibt keinen Cloud-Sync. Zwei Ausnahmen,
beide **optional und bewusst von dir aktiviert**:

- Der KI-Analyzer sendet Transkript-Text an die Anthropic-API, **nur** wenn
  du einen `ANTHROPIC_API_KEY` gesetzt hast (sonst regelbasiert, komplett
  lokal).
- Ein echter YouTube-Upload sendet das Video an Google, **nur** wenn du das
  Feature-Flag aktivierst UND den Upload explizit bestätigst.

## 7. YouTube-Upload: nur privat, standardmäßig deaktiviert

Falls du den echten Upload-Pfad testest: Das Video ist **immer** `private`
(nur du siehst es in YouTube Studio). Es gibt keine Option für „public" oder
„unlisted" — das ist keine Einstellung, die man versehentlich ändern könnte,
sondern eine Grenze im Code selbst.

## 8. Bekannte Grenzen

Vollständige, laufend gepflegte Liste mit Auswirkung/Workaround/Status:
[`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md). Kurzfassung: echter YouTube-Upload
noch nicht mit realem Konto E2E-verifiziert, local-first (kein
Multi-User/Auth/CORS-Härtung für Internet-Exposition), kein dynamisches
Reframe, 3 dokumentierte ESLint-Tech-Debt-Punkte, kein automatisches
Resume eines unterbrochenen Uploads nach Prozessneustart (dafür sichere
Recovery/Reconciliation).

## 9. Feedback-Schwerpunkte

Besonders hilfreich für uns:

1. Bricht der Setup-/Start-Prozess irgendwo ab, oder ist eine Meldung
   unklar?
2. Wirkt der Score/die Clip-Auswahl bei deinen eigenen Videos plausibel?
3. Sind die generierten Titel/Hashtags/Texte brauchbar oder daneben?
4. Gibt es Stellen, an denen die Oberfläche etwas verspricht, das sie nicht
   hält (z. B. ein Button, der nichts Sichtbares tut)?
5. Alles rund um Fehlerfälle: Absturz, Netzwerkausfall, ungewöhnliche
   Dateien — zeigt ClipForge dabei immer eine verständliche Meldung statt
   einer leeren/kaputten Seite?

Kein Punkt hier ist ein Versprechen für Viralität oder Erfolg — der Score
ist eine Einschätzung, keine Garantie.
