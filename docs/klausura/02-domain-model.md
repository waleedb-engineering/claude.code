# 02 · Domänenmodell

Entitäten und Beziehungen, bevor ein Schema entsteht. Alles hier liegt in
`packages/core` und kennt weder Datenbank noch UI.

## Text-ER-Diagramm

```
Subject ──1:n── ExamPaper ──1:n── Task ──1:n── Subtask
   │                │              │              │
   │                │              ├─1:n── TaskAsset
   │                │              │
   │                │              └─1:n── SolutionStep ──0:n── AttemptStep
   │                │                                              │
   │                └─1:n── SourceDocument                         │
   │                          └─1:n── PageArtifact                 │
   │                                    └─1:n── SegmentCandidate   │
   │                                              └─0:1── SegmentOverride
   │
   ├─1:n── Topic ──n:m── TopicPrerequisite (DAG, self-join)
   │          │
   │          └─1:n── FormulaEntry
   │
   └─1:n── ParametricTemplate ──1:n── TemplateVariable
                  │                        └─0:n── VariableConstraint
                  └─1:n── GeneratedVariant

Task ──1:n── Attempt ──1:n── AttemptStep ──0:n── ErrorTag
              │
              ├──0:1── SimulationRun
              └──n:1── StudySession

Learner ──1:1── LearnerProfile ──1:n── ProfileAxis ──1:n── ProfileRule
   │                                        └─0:1── AxisBehaviorEstimate
   │
   └──1:n── MasteryState ──n:1── Topic | TaskType
```

## Entitäten

### Struktur der Klausur

**Subject** — Fach. `id`, `name`, `code` (ET2), `conventions` (j statt i,
Vorzeichenkonvention Statik).

**ExamPaper** — eine Altklausur. `subjectId`, `term` (WS 2023), `examiner`,
`durationMinutes`, `totalPoints`, `passPoints`, `allowedAids[]`, `importedAt`.

**Task** — Aufgabe. `examPaperId`, `ordinal` (A3), `title`, `points`,
`timeBudgetSeconds`, `type` (Berechnung / Herleitung / Bemessung / Freitext),
`topicIds[]`, `promptText`.

**Subtask** — Teilaufgabe. `taskId`, `ordinal` (a, b, c), `points`, `promptText`.
Tasks ohne Teilaufgaben sind erlaubt.

**TaskAsset** — Bildbereich aus dem Dokument: Schaltbild, Diagramm, Tabelle.
`taskId`, `kind`, `pageNumber`, `bbox`, `blobRef`. Assets werden ausgeschnitten,
nicht neu gezeichnet.

**SolutionStep** — geordneter Rechenschritt der Musterlösung. `taskId |
subtaskId`, `ordinal`, `formulaText`, `symbolicExpr`, `intermediateValue`,
`unit`, `explanation`, `pointsAwardedHere`.

### Ingest-Artefakte

Jede Pipeline-Stufe hinterlässt ein eigenes, wiederverwendbares Artefakt.

**SourceDocument** — die Originaldatei. `examPaperId`, `role`
(`exam` | `solution`), `mimeType`, `pageCount`, `sha256`, `blobRef`,
`hasTextLayer`.

**PageArtifact** — je Seite: `rasterRef`, `textLayerJson`, `deskewAngle`,
`qualityScore`.

**SegmentCandidate** — Vorschlag der Auto-Segmentierung. `pageArtifactId`,
`bbox`, `proposedTaskOrdinal`, `proposedPoints`, `confidence`, `producedByRunId`.

**SegmentOverride** — Korrektur des Nutzers. `segmentCandidateId | null`,
`bbox`, `taskOrdinal`, `points`, `action` (`accept` | `adjust` | `split` |
`merge` | `reject` | `create`), `createdAt`.

**SegmentationRun** — ein Durchlauf. `sourceDocumentId`, `strategy`
(`heuristic` | `llm` | `manual`), `startedAt`, `finishedAt`, `paramsJson`.

### Varianten

**ParametricTemplate** — `taskId`, `templateText`, `solutionExpr`,
`status` (`draft` | `quarantined` | `verified`), `verificationReport`.

**TemplateVariable** — `templateId`, `symbol` (R₁), `unit`, `min`, `max`,
`step`, `quantityKind` (Widerstand, Spannung, Länge).

**VariableConstraint** — `templateId`, `expression`
(`R1 < R2`, `U/R1 < 0.5`), `kind` (`relation` | `plausibility`).

**GeneratedVariant** — `templateId`, `seed`, `bindingsJson`,
`expectedResult`, `expectedUnit`, `verifiedAt`.

### Versuche und Fehler

**Attempt** — ein Lösungsversuch. `taskId | subtaskId`, `startedAt`,
`submittedAt`, `elapsedSeconds`, `answerValue`, `answerUnit`,
`awardedPoints`, `maxPoints`, `variantId | null`, `mode`
(`practice` | `simulation`).

**AttemptStep** — eine Zeile des eingegebenen Rechenwegs. `attemptId`,
`ordinal`, `rawText`, `parsedExpr`, `value`, `unit`,
`matchedSolutionStepId | null`, `verdict`
(`equal` | `deviating` | `unmatched` | `undecidable`).

**ErrorTag** — Zuweisung aus der geschlossenen Taxonomie (siehe `05`).
`attemptStepId`, `code`, `severity`, `pointsLost`, `assignedBy`
(`rule` | `llm` | `user`).

### Themen und Beherrschung

**Topic** — `subjectId`, `name`, `level` (Voraussetzungsebene).

**TopicPrerequisite** — `topicId`, `requiresTopicId`. Muss azyklisch bleiben.

**MasteryState** — FSRS-Zustand je (Learner, Topic **oder** TaskType).
`stability`, `difficulty`, `lastReviewedAt`, `dueAt`, `reviewCount`,
`masteryPercent`.

**FormulaEntry** — `topicId`, `symbolicForm`, `name`, `unitBreakdownJson`,
`usedInTaskIds[]`.

### Lernender und Sitzungen

**Learner** — genau eine Zeile in v1. Existiert, damit der Kern mehrbenutzerfähig
bleibt, ohne dass v1 es nutzt.

**LearnerProfile** — `learnerId`, `onboardingAnswersJson`, `computedAt`.

**ProfileAxis** — `profileId`, `key`, `value` (0–100), `band`,
`provenance` (`surveyed` | `measured` | `overridden`).

**AxisBehaviorEstimate** — der gemessene Zwilling. `axisKey`, `estimate`,
`sampleCount`, `confidence`, `updatedAt`.

**ProfileRule** — `axisKey`, `thresholdExpr` (`>= 71`), `area` (TIMER),
`behaviorText`, `isActive`, `userDisabled`, `heldByHysteresis`.

**StudySession** — `learnerId`, `startedAt`, `endedAt`, `plannedBlockId`,
`attemptIds[]`.

**SimulationRun** — `examPaperId`, `learnerId`, `startedAt`,
`durationMinutes`, `totalAwarded`, `totalPossible`, `passed`.

## Invarianten

Jede ist prüfbar formuliert und gehört in die Unit-Tests des Kerns.

| # | Invariante |
|---|---|
| I1 | Hat eine `Task` Teilaufgaben, gilt `Σ Subtask.points == Task.points` |
| I2 | `Σ Task.points == ExamPaper.totalPoints` |
| I3 | `SolutionStep.ordinal` ist je Task/Subtask lückenlos `1..n` |
| I4 | `0 ≤ Attempt.awardedPoints ≤ Attempt.maxPoints` |
| I5 | `Σ Task.timeBudgetSeconds ≤ ExamPaper.durationMinutes · 60` |
| I6 | `TopicPrerequisite` bildet einen DAG — kein Zyklus |
| I7 | `ParametricTemplate.status == verified` nur, wenn alle drei Verifikationsstufen bestanden sind |
| I8 | Jede `GeneratedVariant` mit `verifiedAt == null` wird dem Nutzer nie vorgelegt |
| I9 | `ErrorTag.code` stammt aus der geschlossenen Taxonomie in `05`; unbekannte Codes sind ein Schemafehler |
| I10 | `MasteryState` existiert je (Learner, Topic) und je (Learner, TaskType) höchstens einmal |
| I11 | `TaskAsset.bbox` liegt vollständig innerhalb der Seitengrenzen des `PageArtifact` |
| I12 | Ein `SegmentOverride` überlebt jeden neuen `SegmentationRun`: erneute Auto-Segmentierung darf ihn nie überschreiben oder löschen |
| I13 | `SimulationRun.durationMinutes == ExamPaper.durationMinutes` — der Simulator kürzt die Klausurdauer nicht |
| I14 | `ProfileAxis.value == clamp(0, 50 + Σ Beiträge, 100)` — der Wert wird nie gespeichert, immer gerechnet |
| I15 | Ein `ProfileRule` mit `userDisabled == true` ändert `ProfileAxis.value` nicht — Abschalten wirkt auf Verhalten, nicht aufs Profil |
| I16 | `Attempt.submittedAt >= Attempt.startedAt`, und `elapsedSeconds` ist aus beiden ableitbar, nicht unabhängig gesetzt |
| I17 | Ein `SourceDocument` mit `role == solution` gehört zum selben `ExamPaper` wie das zugehörige `exam`-Dokument |

## Abgeleitet, nie gespeichert

Achsenwerte, Bänder, aktive Regeln, Beherrschungsgrade, Tagesplan, Bestehens-
prognose, Fortschrittsbalken. Persistiert werden ausschließlich Rohdaten
(Dokumente, Antworten, Zeiten, Onboarding-Antworten) und ausdrückliche
Nutzerentscheidungen (Overrides, abgeschaltete Regeln).

Grund: das Profil muss sich nach einer geänderten Antwort vollständig neu
rechnen lassen, und ein Bugfix in der Arithmetik muss rückwirkend gelten.
