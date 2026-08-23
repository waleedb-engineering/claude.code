# 00 · Vision

## Das Produkt in einem Absatz

KLAUSURA macht aus Altklausur-PDFs einen strukturierten Übungs- und Prüfungsplan.
Eine Klausur wird sichtbar in Aufgabenkarten zerlegt; jede Aufgabe wird unter
Zeitbudget gelöst; der Rechenweg wird mit der Musterlösung verglichen; aus
wiederkehrenden Fehlern entsteht ein Fehlerprofil, das Lernplan und UI-Verhalten
steuert. Alle Nutzerdaten liegen lokal.

## Wer es benutzt

Ingenieurstudierende in der Klausurphase, die Altklausuren besitzen und sie
systematisch statt planlos durcharbeiten wollen. Primärfall: eine Person, ein
Gerät, drei bis zehn Altklausuren pro Fach, zwei bis sechs Wochen vor der Prüfung.

Nicht adressiert: Vorlesungsbegleitung über das Semester, Gruppenlernen,
Karteikarten-Vokabellernen, Hausaufgabenhilfe.

## Das Versprechen

Drei Dinge, die andere Lern-Apps nicht tun:

1. **Die Klausur bleibt die Einheit.** Nicht Karteikarten, nicht Themen —
   Aufgaben mit Punkten und Zeitbudget, so wie sie in der Prüfung stehen.
2. **Der Rechenweg wird bewertet, nicht nur das Ergebnis.** Ein Folgefehler
   kostet einen Punkt, nicht die Aufgabe.
3. **Das System erklärt sich.** Jede Verhaltensregel der App hängt an einer
   nachlesbaren Schwelle und ist einzeln abschaltbar.

## Was v1 nicht ist

- **Kein Klausur-Pool.** Nutzer bringen ihre eigenen Dateien mit. Es gibt keine
  zentrale Sammlung, kein Teilen, keinen Upload zu uns.
- **Kein Konto, kein Server** als Voraussetzung für Kernfunktionen.
- **Keine Notenvorhersage** als Zahl. Standardaussage ist der Bestehensabstand
  in Punkten.
- **Kein Gamification-Layer.** Keine XP, keine Level, keine Serien.
- **Keine Handschrifterkennung** von gelösten Rechenwegen. Eingabe ist getippt.

## Kernfunktionen v1

| Funktion | Ohne Netz | Mit KI-Opt-in |
|---|---|---|
| Import PDF mit Textlayer | vollständig | bessere Segmentierung |
| Import Scan / Foto | OCR on-device | Layout-Analyse besser |
| Manuelle Aufgaben-Segmentierung | vollständig | — |
| Auto-Segmentierung | Heuristik + Regex | LLM-gestützt |
| Lösen mit Timer | vollständig | — |
| Bewertung numerisch + Einheiten | vollständig | — |
| Rechenweg-Diff | vollständig (bei vorhandener Musterlösung) | Freitext-Bewertung |
| Parametrische Varianten | Abspielen verifizierter Vorlagen | Vorlagen erzeugen |
| Fehler-DNA, Wissensgraph, Plan | vollständig | — |

Lesart: **die App ist ohne Netz benutzbar.** KI verbessert die Aufbereitung beim
Import, sie ist keine Voraussetzung fürs Lernen.

---

## Recht und Datenschutz (Block E)

### Die Ausgangslage

Altklausuren und Musterlösungen sind urheberrechtlich geschützte Werke der
Hochschule bzw. der Prüfenden. Nutzer besitzen typischerweise Kopien, deren
Weitergabe ihnen nicht zusteht. Eine App, die diese Dateien zentral sammelt,
sammelt fremdes Urheberrecht — und wird damit zum Adressaten.

### Die vier Grundsatzentscheidungen

Diese sind Architektur, nicht Policy. Sie lassen sich später nicht nachrüsten.

**1 · Strikt local-first.** Klausuren, Aufgaben, Antworten, Zeiten, Profil und
Regel-Overrides liegen auf dem Gerät. Kein Backend als Voraussetzung. Sync ist
nicht Teil von v1.

**2 · Kein zentraler Klausur-Pool, kein Sharing in v1.** Es gibt keine Funktion,
die eine importierte Klausur an jemand anderen weitergibt — auch nicht als
„Export für Freunde". Wer das später will, braucht eine rechtliche Prüfung, die
v1 nicht leistet.

**3 · LLM-Verarbeitung ist Opt-in mit Anzeige.** Bevor Inhalte das Gerät
verlassen, sieht der Nutzer, *was* geht: welche Seiten, welcher Textausschnitt,
an welchen Anbieter. Die Zustimmung gilt pro Dokument, nicht pauschal für immer.
Kein stilles Nachladen im Hintergrund.

**4 · Vollständig lokaler Betrieb bleibt möglich.** Der LLM-Port hat einen
lokalen Adapter als Ziel. Auch wenn v1 mit Cloud-Key startet: keine Funktion
darf so gebaut werden, dass sie ohne Cloud prinzipiell unmöglich wird.

### Konsequenzen für die Architektur

- Der `LlmPort` bekommt eine **Vorschau-Methode**, die zurückgibt, was gesendet
  würde, ohne zu senden. Die Zustimmungs-UI ruft sie auf.
- Jeder LLM-Aufruf wird lokal protokolliert: Zeitpunkt, Dokument, Anbieter,
  gesendete Zeichenzahl. Der Nutzer kann das Protokoll einsehen.
- API-Keys liegen im Schlüsselbund des Betriebssystems, nie in der Datenbank
  und nie im Klartext in einer Konfigurationsdatei.
- Assets (Schaltbild-Ausschnitte) werden **nie** an ein LLM gesendet, solange
  nicht der Nutzer für dieses Dokument ausdrücklich Bildanalyse aktiviert.
- Ein Export erzeugt ein Archiv für den Nutzer selbst (Backup, Gerätewechsel).
  Er ist nicht als Weitergabeformat gestaltet und wirbt nicht damit.

### Was bewusst offenbleibt

Ob ein Nutzer seine Altklausuren überhaupt digitalisieren darf, ist seine
Angelegenheit und hängt von Hochschule und Quelle ab. Die App trifft dazu keine
Aussage und prüft nichts. Sie stellt nur sicher, dass sie selbst keine Kopie
in Umlauf bringt.
