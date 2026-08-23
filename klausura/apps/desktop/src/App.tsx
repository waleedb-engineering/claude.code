import { useEffect, useMemo, useState } from 'react';
import type { ExamPaperId, Task } from '@klausura/model';
import { ImportScreen } from './screens/Import.js';
import { SegmentScreen } from './screens/Segment.js';
import { AtlasScreen } from './screens/Atlas.js';
import { SolveScreen } from './screens/Solve.js';
import { CommandPalette, type Command } from './components/CommandPalette.js';

type Route =
  | { readonly name: 'import' }
  | { readonly name: 'segment'; readonly examId: ExamPaperId }
  | { readonly name: 'atlas' }
  | { readonly name: 'solve'; readonly task: Task };

export function App() {
  const [route, setRoute] = useState<Route>({ name: 'atlas' });
  const [mode, setMode] = useState<'light' | 'dark'>('light');

  useEffect(() => { document.documentElement.dataset['mode'] = mode; }, [mode]);

  const commands = useMemo<Command[]>(() => [
    { id: 'atlas', kind: 'AKTION', label: 'Zum Aufgaben-Atlas', run: () => setRoute({ name: 'atlas' }) },
    { id: 'import', kind: 'AKTION', label: 'Altklausur importieren', run: () => setRoute({ name: 'import' }) },
    {
      id: 'mode', kind: 'AKTION', label: 'Fokus-Dunkel umschalten',
      run: () => setMode((m) => (m === 'light' ? 'dark' : 'light')),
    },
  ], []);

  return (
    <div className="app">
      <header className="topbar">
        <span className="wordmark">KLAUSURA</span>
        <span className="mono muted small">ET2 · WS 2023</span>
        <nav>
          <button type="button" data-testid="nav-atlas" onClick={() => setRoute({ name: 'atlas' })}>Atlas</button>
          <button type="button" data-testid="nav-import" onClick={() => setRoute({ name: 'import' })}>Import</button>
          <button
            type="button" data-testid="nav-mode" aria-pressed={mode === 'dark'}
            onClick={() => setMode((m) => (m === 'light' ? 'dark' : 'light'))}
          >
            {mode === 'light' ? 'Fokus-Dunkel' : 'Hell'}
          </button>
        </nav>
        <span className="mono muted small kbd-hint">⌘K BEFEHLE</span>
      </header>

      <main>
        {route.name === 'import' && (
          <ImportScreen onImported={(examId) => setRoute({ name: 'segment', examId })} />
        )}
        {route.name === 'segment' && (
          <SegmentScreen examId={route.examId} onDone={() => setRoute({ name: 'atlas' })} />
        )}
        {route.name === 'atlas' && (
          <AtlasScreen onOpenTask={(task) => setRoute({ name: 'solve', task })} />
        )}
        {route.name === 'solve' && (
          <SolveScreen task={route.task} onBack={() => setRoute({ name: 'atlas' })} />
        )}
      </main>

      <CommandPalette commands={commands} />
    </div>
  );
}
