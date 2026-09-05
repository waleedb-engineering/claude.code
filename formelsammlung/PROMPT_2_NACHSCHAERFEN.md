# Nachschärf-Prompts für ChatGPT

> **Nicht** in die erste Nachricht kopieren. Diese Texte schickst du erst, wenn er
> im laufenden Chat abdriftet — jeder einzeln, als normale Nachricht.

# ZUSATZ-PROMPTS — zum Reinwerfen, wenn er abdriftet

Modelle lassen Regeln über lange Chats schleifen. Diese vier Texte holen ihn zurück.
Einfach als normale Nachricht schicken.

## A) Wenn er die Aufgabenstellung umformuliert hat

```
Stopp. Du hast die Aufgabenstellung in eigenen Worten wiedergegeben. Das ist
Regel 2, und sie ist für mich die wichtigste.

Ich erkenne die Aufgabe in der Klausur am Wortlaut wieder — eine Paraphrase ist
für mich wertlos, egal wie korrekt sie inhaltlich ist.

Gib die letzte Antwort noch einmal aus, diesmal mit:
- jeder Aufgabenstellung am Originalwortlaut, in Anführungszeichen; leichtes Straffen
  ist erlaubt, aber Signalverb, Fachbegriffe, Formelzeichen und Zahlen bleiben wörtlich
- Fundstelle und Teilaufgabenbuchstaben a)/b)/c) im Original
- den Originalsymbolen der jeweiligen Quelle, auch wenn sie sich zwischen den
  Quellen unterscheiden
- [unleserlich] dort, wo der Scan es nicht hergibt — nichts ergänzen

Wenn du eine Stelle nicht wörtlich lesen kannst, sag es, statt sie zu glätten.
```

## B) Wenn er Aufgaben zusammengefasst oder übersprungen hat

```
Stopp. Du hast Fundstellen zusammengefasst oder weggelassen. Das ist Regel 3.

Zwei Aufgaben mit gleichem Rechenweg, aber anderem Wortlaut sind für mich zwei
Einträge, nicht einer. Genau die Varianten brauche ich.

Liste für dieses Thema jetzt:
1. alle Fundstellen-IDs aus dem Inventar
2. welche du in deiner Antwort tatsächlich erfasst hast
3. die Differenz — und arbeite die fehlenden nach

Schließ mit der Abdeckungsbilanz: im Inventar N · erfasst N · offen 0.
```

## C) Wenn er abkürzt oder mich rechnen lässt

```
Stopp. Zwei Dinge:

1. Du hast abgekürzt („analog zu oben", „das Gleiche mit anderen Zahlen", „…").
   Ich rechne nicht nach, ich schreibe ab. Jede Lösung muss vollständig dastehen,
   auch wenn sie sich wiederholt.

2. Ich lerne den Stoff nicht und rechne nicht selbst. Frag mich nichts ab und gib
   mir keine Aufgaben zum Selbstrechnen. Du lieferst fertig gelöste Aufgaben.

Gib die letzte Antwort noch einmal aus: jede Fundstelle mit Aufgabenwortlaut und
vollständig durchgerechneter Lösung, jeder Schritt mit Einheit, nichts ausgelassen.
```

## D) Regelcheck zwischendurch (alle paar Themen einmal)

```
Regelcheck, bevor du weitermachst:

1. Nenn mir Regel 1, 2, 3 und 4 in einem Satz je Regel.
2. Zeig die Fortschrittstabelle: Thema · Fundstellen im Inventar · davon erfasst ·
   Status · Kasten fertig.
3. Nenn mir jedes Thema, bei dem "erfasst" kleiner ist als "im Inventar", und sag
   warum.

Erst danach weiter mit dem nächsten Thema.
```

## E) Override — wenn ein Chat noch die alte, widersprüchliche Fassung enthält

Nur nötig, wenn du in einem laufenden Chat weitermachst, dem du vorher eine frühere
Fassung dieses Prompts gegeben hast. **Besser ist ein neuer Chat.** Die frühere Fassung
sagte an zwei Stellen das Gegenteil (der Nutzer rechnet selbst; identische Aufgaben werden
nicht doppelt ausgeschrieben) — bleiben diese Sätze unwidersprochen im Kontext, fällt das
Modell nach einigen Runden dorthin zurück.

Diesen Text schicken, **bevor** du die neue Fassung schickst:

```
Wichtig: Ab hier gelten neue Anweisungen. Sie ERSETZEN alles, was ich dir
vorher gesagt habe. Wo sie meinen früheren Anweisungen widersprechen, gilt
ausschließlich die neue Fassung. Vergiss die alten Regeln.

Zwei Punkte habe ich ausdrücklich umgedreht:

1. FRÜHER sagte ich „ich rechne, du prüfst". Das gilt NICHT mehr.
   Ab jetzt rechnest DU alles vollständig vor. Ich lerne den Stoff nicht und
   rechne nicht selbst. Frag mich nichts ab, gib mir keine Aufgaben zum
   Selbstrechnen. Du lieferst fertig gelöste Aufgaben zum Abschreiben.

2. FRÜHER sagte ich, identische Aufgaben rechnen wir nicht doppelt. Das gilt
   NICHT mehr. Ab jetzt wird JEDE Fundstelle vollständig ausgeschrieben, auch
   wenn sich der Rechenweg wiederholt. „Analog zu oben" ist verboten.

Bestätige mir in zwei Sätzen, dass diese beiden Punkte ab jetzt umgekehrt
gelten. Danach schicke ich dir die vollständige neue Anweisung.
```
