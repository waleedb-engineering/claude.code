import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { formatPoints, type Task } from '@klausura/model';
import { listExamPapers, listTasks } from '@klausura/storage-sqlite';
import { db } from '../platform/expo-storage';
import { C, HIT, MONO, R, S, T } from '../theme';

/** Screen 03, mobile Fassung: eine Spalte, kompaktere Karte, Hit-Targets ≥ 44 px. */
export function AtlasScreen({ onOpen }: { onOpen: (task: Task) => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => {
    void (async () => {
      const storage = await db();
      const all: Task[] = [];
      for (const p of await listExamPapers(storage)) all.push(...(await listTasks(storage, p.id)));
      setTasks(all);
    })();
  }, []);

  if (tasks.length === 0) {
    return (
      <View style={styles.empty}>
        <Text style={styles.label}>03 · AUFGABEN-ATLAS</Text>
        <Text style={styles.emptyTitle}>Noch keine Aufgabe erfasst</Text>
        <Text style={styles.body}>
          Klausuren werden am Rechner importiert und zerlegt. Hier erscheinen sie,
          sobald das geschehen ist.
        </Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.list}>
      {tasks.map((t) => (
        <Pressable key={t.id} style={styles.card} onPress={() => onOpen(t)} accessibilityRole="button">
          <View style={styles.cardHead}>
            <Text style={styles.ordinal}>{t.ordinal}</Text>
            <Text style={styles.badge}>{formatPoints(t.points)} P</Text>
          </View>
          <Text style={styles.title}>{t.title}</Text>
          <Text style={styles.meta}>
            {(t.topic ?? 'OHNE THEMA').toUpperCase()} · {Math.round(t.timeBudgetSeconds / 60)} MIN
          </Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  list: { padding: S.lg, gap: S.md },
  card: {
    minHeight: HIT, padding: S.lg, gap: S.xs,
    backgroundColor: C.chrome, borderWidth: 1, borderColor: C.rule, borderRadius: R,
  },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  ordinal: { fontFamily: MONO, fontWeight: '600', fontSize: T['num-13'].size, color: C.ink },
  badge: {
    fontFamily: MONO, fontSize: T['num-13'].size, color: C.ink60,
    borderWidth: 1, borderColor: C.rule, borderRadius: R, paddingHorizontal: S.sm, paddingVertical: 3,
  },
  title: { fontSize: T['title-18'].size, fontWeight: '600', color: C.ink },
  meta: { fontFamily: MONO, fontSize: T['label-10'].size, color: C.ink60, letterSpacing: 1.2 },
  empty: { flex: 1, justifyContent: 'center', padding: S.xl, gap: S.sm, backgroundColor: C.grid },
  emptyTitle: { fontSize: T['title-18'].size, fontWeight: '600', color: C.ink },
  body: { fontSize: T['body-14'].size, lineHeight: T['body-14'].size * 1.65, color: C.ink60 },
  label: { fontFamily: MONO, fontSize: T['label-10'].size, letterSpacing: 1.4, color: C.ink60 },
});
