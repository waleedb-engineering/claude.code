import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { asAttemptId, formatPoints, type Attempt, type Task } from '@klausura/model';
import {
  beginAttempt, readElapsed, resumeAttempt, submitAttempt, type AttemptSession,
} from '@klausura/core';
import { findRunningAttempt, listAttempts, saveAttempt } from '@klausura/storage-sqlite';
import { db } from '../platform/expo-storage';
import { nativeClock } from '../platform/native-clock';
import { MobileTimer } from '../components/MobileTimer';
import { C, HIT, MONO, R, S, T } from '../theme';

const UNITS = ['Ω', 'kΩ', 'MΩ', 'V', 'mV', 'A', 'mA', 'W'] as const;

export function SolveScreen({ task, onBack }: { task: Task; onBack: () => void }) {
  const [session, setSession] = useState<AttemptSession | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [value, setValue] = useState('');
  const [unit, setUnit] = useState('');
  const [past, setPast] = useState<Attempt[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const budgetMs = task.timeBudgetSeconds * 1000;

  const loadPast = useCallback(async () => {
    const storage = await db();
    setPast((await listAttempts(storage, task.id)).filter((a) => a.submittedAtWall !== null));
  }, [task.id]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const storage = await db();
      const running = await findRunningAttempt(storage, task.id);
      if (cancelled) return;
      if (running !== undefined) {
        setSession(resumeAttempt(running));
        setValue(running.answerValue ?? '');
        setUnit(running.answerUnit ?? '');
      } else {
        const fresh = beginAttempt(
          { id: asAttemptId(`att-${task.id}-${nativeClock.wall()}`), taskId: task.id, maxPoints: task.points, mode: 'practice' },
          nativeClock,
        );
        await saveAttempt(storage, fresh.attempt);
        if (!cancelled) setSession(fresh);
      }
      await loadPast();
    })();
    return () => { cancelled = true; };
  }, [task.id, task.points, loadPast]);

  // Mobil reicht ein Takt pro Sekunde: der Balken braucht keine 60 Bilder.
  // Der WERT kommt trotzdem jedes Mal frisch aus den Zeitstempeln — der
  // Intervall treibt nur die Anzeige, er summiert nichts.
  useEffect(() => {
    if (session === null) return;
    const read = (): void => setElapsed(readElapsed(session.anchors, nativeClock).elapsedMs);
    read();
    timer.current = setInterval(read, 500);
    return () => { if (timer.current !== null) clearInterval(timer.current); };
  }, [session]);

  async function submit(): Promise<void> {
    if (session === null) return;
    const storage = await db();
    await saveAttempt(storage, submitAttempt(session, { value, unit }, nativeClock));
    setSession(null);
    await loadPast();
    onBack();
  }

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={styles.body}>
        <View style={styles.head}>
          <Text style={styles.ordinal}>{task.ordinal}</Text>
          <Text style={styles.title}>{task.title}</Text>
          <Text style={styles.meta}>
            {formatPoints(task.points)} P · {(task.topic ?? 'OHNE THEMA').toUpperCase()}
          </Text>
        </View>

        <MobileTimer elapsedMs={elapsed} budgetMs={budgetMs} />

        <Text style={styles.label}>ERGEBNIS</Text>
        <View style={styles.answer}>
          <TextInput
            style={styles.value}
            value={value}
            onChangeText={setValue}
            keyboardType="numbers-and-punctuation"
            accessibilityLabel="Ergebniswert"
            placeholder="—"
            placeholderTextColor={C.ink30}
          />
          <View style={styles.divider} />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.units}>
            {UNITS.map((u) => (
              <Pressable
                key={u}
                onPress={() => setUnit(u === unit ? '' : u)}
                accessibilityRole="button"
                accessibilityState={{ selected: u === unit }}
                style={[styles.unit, u === unit && styles.unitActive]}
              >
                <Text style={[styles.unitText, u === unit && styles.unitTextActive]}>{u}</Text>
              </Pressable>
            ))}
          </ScrollView>
        </View>

        <Text style={styles.label}>FRÜHERE VERSUCHE</Text>
        {past.length === 0 ? (
          <Text style={styles.muted}>Noch kein abgegebener Versuch.</Text>
        ) : (
          past.map((a) => (
            <View key={a.id} style={styles.attempt}>
              <Text style={styles.mono}>{a.answerValue ?? '—'} {a.answerUnit ?? ''}</Text>
              <Text style={styles.monoMuted}>{Math.round(a.elapsedMs / 1000)} s</Text>
            </View>
          ))
        )}
      </ScrollView>

      {/* Primaeraktion in fixer Fussleiste, wie im Handoff fuer Mobile gefordert. */}
      <View style={styles.footer}>
        <Pressable style={styles.secondary} onPress={onBack} accessibilityRole="button">
          <Text style={styles.secondaryText}>Zurück</Text>
        </Pressable>
        <Pressable style={styles.primary} onPress={() => void submit()} accessibilityRole="button">
          <Text style={styles.primaryText}>Abgeben</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.paper },
  body: { padding: S.lg, gap: S.md },
  head: { gap: S.xs },
  ordinal: { fontFamily: MONO, fontSize: T['body-12'].size, fontWeight: '600', color: C.ink60 },
  title: { fontSize: T['title-18'].size, fontWeight: '600', color: C.ink },
  meta: { fontFamily: MONO, fontSize: T['label-10'].size, letterSpacing: 1.2, color: C.ink60 },
  label: { fontFamily: MONO, fontSize: T['label-11'].size, letterSpacing: 1.5, color: C.ink60, marginTop: S.md },
  answer: { backgroundColor: C.chrome, borderWidth: 1, borderColor: C.rule, borderRadius: R },
  value: { minHeight: HIT, paddingHorizontal: S.md, fontFamily: MONO, fontSize: T['num-22'].size, color: C.ink },
  divider: { height: 1, backgroundColor: C.rule },
  units: { padding: S.sm, gap: S.sm },
  unit: {
    minHeight: HIT, minWidth: HIT, alignItems: 'center', justifyContent: 'center',
    paddingHorizontal: S.md, borderWidth: 1, borderColor: C.rule, borderRadius: R,
  },
  unitActive: { backgroundColor: C.ink, borderColor: C.ink },
  unitText: { fontFamily: MONO, fontSize: T['body-15'].size, color: C.ink60 },
  unitTextActive: { color: C.chrome },
  muted: { fontSize: T['body-13'].size, color: C.ink60 },
  attempt: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingVertical: S.sm, borderBottomWidth: 1, borderBottomColor: C.rule,
  },
  mono: { fontFamily: MONO, fontSize: T['num-13'].size, color: C.ink, fontVariant: ['tabular-nums'] },
  monoMuted: { fontFamily: MONO, fontSize: T['num-13'].size, color: C.ink60, fontVariant: ['tabular-nums'] },
  footer: {
    flexDirection: 'row', gap: S.sm, padding: S.md,
    backgroundColor: C.chrome, borderTopWidth: 1, borderTopColor: C.rule,
  },
  secondary: {
    minHeight: HIT, flex: 1, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: C.rule, borderRadius: R,
  },
  secondaryText: { fontSize: T['body-16'].size, color: C.ink },
  primary: {
    minHeight: HIT, flex: 2, alignItems: 'center', justifyContent: 'center',
    backgroundColor: C.signal, borderRadius: R,
  },
  primaryText: { fontSize: T['body-16'].size, fontWeight: '600', color: '#FFFFFF' },
});
