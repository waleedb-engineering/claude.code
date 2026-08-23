import { useState } from 'react';
import { SafeAreaView, StatusBar, StyleSheet, Text, View } from 'react-native';
import type { Task } from '@klausura/model';
import { AtlasScreen } from './screens/Atlas';
import { SolveScreen } from './screens/Solve';
import { C, MONO, S, T } from './theme';

export function App() {
  const [task, setTask] = useState<Task | null>(null);

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.bar}>
        <Text style={styles.wordmark}>KLAUSURA</Text>
        <Text style={styles.context}>ET2 · WS 2023</Text>
      </View>
      {task === null
        ? <AtlasScreen onOpen={setTask} />
        : <SolveScreen task={task} onBack={() => setTask(null)} />}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.paper },
  bar: {
    height: 52, flexDirection: 'row', alignItems: 'center', gap: S.md,
    paddingHorizontal: S.lg, backgroundColor: C.panel,
    borderBottomWidth: 1, borderBottomColor: C.rule,
  },
  wordmark: { fontFamily: MONO, fontSize: T['num-13'].size, fontWeight: '600', letterSpacing: 2, color: C.ink },
  context: { fontFamily: MONO, fontSize: T['label-11'].size, color: C.ink60 },
});
