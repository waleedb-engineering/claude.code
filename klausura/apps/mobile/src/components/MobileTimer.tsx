import { StyleSheet, Text, View } from 'react-native';
import { consumedRatio, timerPhase, type TimerPhase } from '@klausura/core';
import { C, MONO, S, T } from '../theme';

const COLOR: Record<TimerPhase, string> = {
  fresh: C.track, running: C.signal, warning: C.warn, over: C.over,
};
const LABEL: Record<TimerPhase, string> = {
  fresh: 'BEREIT', running: 'LÄUFT', warning: 'ZEIT 70 %', over: 'ÜBERZOGEN',
};

export function formatClock(ms: number): string {
  const total = Math.floor(Math.abs(ms) / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/**
 * Mobil ersetzt ein Balken den Ring — das ist im Design-Handoff ohnehin die
 * Darstellung bei hoher Prüfungsangst und mobil die ruhigere Form.
 * Der Balken wächst über scaleX, nicht über width.
 */
export function MobileTimer({ elapsedMs, budgetMs }: { elapsedMs: number; budgetMs: number }) {
  const phase = timerPhase(elapsedMs, budgetMs);
  const ratio = consumedRatio(elapsedMs, budgetMs);
  const remaining = budgetMs - elapsedMs;

  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel={`Zeit ${formatClock(remaining)}, ${LABEL[phase]}`}
    >
      <View style={styles.row}>
        <Text style={[styles.value, { color: COLOR[phase] }]}>
          {remaining < 0 ? '+' : ''}{formatClock(remaining)}
        </Text>
        <Text style={styles.label}>{LABEL[phase]}</Text>
      </View>
      <View style={styles.track}>
        <View
          style={[
            styles.fill,
            { backgroundColor: COLOR[phase], transform: [{ scaleX: ratio }] },
          ]}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'baseline', gap: S.md },
  value: { fontFamily: MONO, fontSize: T['num-26'].size, fontWeight: '600', fontVariant: ['tabular-nums'] },
  label: { fontFamily: MONO, fontSize: T['label-10'].size, letterSpacing: 1.4, color: C.ink60 },
  track: { height: 4, backgroundColor: C.track, marginTop: S.sm, overflow: 'hidden' },
  fill: { height: 4, width: '100%', transformOrigin: 'left' },
});
