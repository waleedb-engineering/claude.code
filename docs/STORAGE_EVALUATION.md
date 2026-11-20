# Persistenz: JSON beibehalten oder SQLite? (Bewertung 11/2026)

**Entscheidung: JSON bleibt.** Kein Datenbankwechsel in ClipForge 3.0.

## Ist-Zustand

| Eigenschaft | Umsetzung | Nachweis |
|---|---|---|
| Atomares Schreiben | Temp-Datei + `fsync` + `os.replace` (`studio/storage.write_json_atomic`), Retry unter Windows | `test_storage.py`, Windows-CI |
| Keine Reste bei Abbruch | Temp-Datei wird im `finally` gelöscht | `test_storage.py` |
| Konflikte im Editor | Projektversion (`expected_version`) → 409 bei paralleler Änderung | `test_studio_api.py` |
| Versionsgeschichte / Undo | Projekt-Snapshots, `restore_version` (auch vom Agenten genutzt) | `test_restore.py`, `test_editor_agent.py` |
| Hintergrundaufgaben | persistente Task-Dateien, Recovery nach Neustart, kooperativer Abbruch | `test_cancel.py`, `test_studio_hardening.py` |
| Benutzertrennung | eigener Ordner je Benutzer (ContextVar) | `test_auth_accounts.py` |
| Backup | Ordner kopieren genügt (keine laufende DB-Datei) | – |

## Warum (noch) kein SQLite

- Datenmengen sind klein (Projekt-JSON wenige KB, Analyse ≤ ~1 MB je 3-h-Stream);
  Medien liegen ohnehin als Dateien daneben.
- Typischer Betrieb ist **ein Nutzer lokal**; die Schreiblast ist gering.
- Ein Wechsel würde Migration, Rückfallweg und neue Fehlerklassen (Sperren,
  Schema-Upgrades) bringen, ohne einen gemessenen Engpass zu lösen.

## Bekannte Grenze (dokumentiert, nicht behoben)

Lese-Ändere-Schreibe-Folgen auf derselben Datei (z. B. `analysis.json`, wenn
gleichzeitig ein Highlight korrigiert und markiert wird) sind nur innerhalb eines
Prozesses durch die Schreibsperre geschützt, nicht als Transaktion. Im
Einzelplatzbetrieb praktisch irrelevant; bei **mehreren gleichzeitigen Nutzern
auf einem Server** oder mehreren Backend-Prozessen ist das ein Grund zu wechseln.

## Wann wechseln — und wie

Auslöser: Online-Betrieb mit mehreren Prozessen/Instanzen, > ~10 gleichzeitige
Nutzer oder Abfragen über viele Projekte (Suche, Statistik).
Dann: SQLite im WAL-Modus (Einzelserver) bzw. PostgreSQL (mehrere Instanzen),
Migration mit Sicherung des alten Ordners, Migrationstest gegen echte Altbestände,
Projektversionen 1:1 übernehmen, Rückweg dokumentieren.

## Betrieb

- **macOS lokal**: `scripts/start_local.sh` (seit 2.0 für bash 3.2 ohne `wait -n` angepasst).
- **Docker**: `Dockerfile` + `docker-compose.yml`; CI baut das Image und prüft `/health`.
- **Vercel-Preview**: nur das Next.js-Frontend; das Python-/FFmpeg-Backend kann dort
  nicht laufen. Der rote Vercel-Check besteht schon auf der Basis-Branch und ist
  kein Fehler dieses Branches (Empfehlung im PR: Root auf `web/` setzen oder
  Preview deaktivieren — Entscheidung des Repo-Eigentümers). Keine bezahlten
  Deployments ausgelöst.
