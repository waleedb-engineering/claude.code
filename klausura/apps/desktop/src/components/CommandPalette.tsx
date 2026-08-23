import { useEffect, useMemo, useState } from 'react';

export interface Command {
  readonly id: string;
  readonly label: string;
  readonly kind: 'AKTION' | 'AUFGABE';
  readonly hint?: string;
  readonly run: () => void;
}

/**
 * Komponente 13 aus dem Handoff. Öffnet mit ⌘K bzw. Strg+K.
 * Vollständig mit der Tastatur bedienbar: Pfeile wählen, Enter führt aus,
 * Escape schliesst.
 */
export function CommandPalette({ commands }: { commands: readonly Command[] }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery('');
        setIndex(0);
      } else if (e.key === 'Escape') {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const hits = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q === '' ? commands : commands.filter((c) => c.label.toLowerCase().includes(q));
  }, [commands, query]);

  if (!open) return null;

  return (
    <div className="palette-backdrop" role="presentation" onClick={() => setOpen(false)}>
      <div
        className="palette" role="dialog" aria-modal="true" aria-label="Befehlspalette"
        data-testid="command-palette" onClick={(e) => e.stopPropagation()}
      >
        <input
          autoFocus
          className="palette__input mono"
          data-testid="palette-input"
          aria-label="Befehl suchen"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setIndex(0); }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setIndex((i) => Math.min(hits.length - 1, i + 1)); }
            if (e.key === 'ArrowUp') { e.preventDefault(); setIndex((i) => Math.max(0, i - 1)); }
            if (e.key === 'Enter') { hits[index]?.run(); setOpen(false); }
          }}
        />
        <ul className="palette__list">
          {hits.map((c, i) => (
            <li key={c.id}>
              <button
                type="button"
                data-active={i === index || undefined}
                onClick={() => { c.run(); setOpen(false); }}
              >
                <span className="label-9">{c.kind}</span>
                <span className="body-14">{c.label}</span>
                {c.hint !== undefined && <span className="mono small muted">{c.hint}</span>}
              </button>
            </li>
          ))}
          {hits.length === 0 && <li className="body-13 muted palette__empty">Kein Treffer.</li>}
        </ul>
      </div>
    </div>
  );
}
