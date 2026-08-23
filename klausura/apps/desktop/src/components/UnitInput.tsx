import { useId } from 'react';

/**
 * Komponente 4 aus dem Handoff. Zweigeteiltes Feld: Zahl links, Einheit rechts.
 *
 * Rechnet Präfixe NIE stillschweigend um — kΩ und Ω sind getrennte Eingaben
 * (CLAUDE.md Regel 8). Die Einheit ist ein eigenes Feld, kein Suffix im Text,
 * damit gar nicht erst die Versuchung entsteht, sie zu normalisieren.
 */
export function UnitInput({
  value, unit, onValueChange, onUnitChange, disabled = false, units = ['Ω', 'kΩ', 'MΩ', 'V', 'mV', 'A', 'mA', 'W'],
}: {
  value: string;
  unit: string;
  onValueChange: (v: string) => void;
  onUnitChange: (u: string) => void;
  disabled?: boolean;
  units?: readonly string[];
}) {
  const id = useId();
  return (
    <div className="unit-input" data-disabled={disabled || undefined}>
      <input
        id={`${id}-value`}
        className="unit-input__value"
        data-testid="answer-value"
        inputMode="decimal"
        autoComplete="off"
        aria-label="Ergebniswert"
        value={value}
        disabled={disabled}
        onChange={(e) => onValueChange(e.target.value)}
      />
      <span className="unit-input__divider" aria-hidden="true" />
      <select
        id={`${id}-unit`}
        className="unit-input__unit"
        data-testid="answer-unit"
        aria-label="Einheit"
        value={unit}
        disabled={disabled}
        onChange={(e) => onUnitChange(e.target.value)}
      >
        <option value="">—</option>
        {units.map((u) => <option key={u} value={u}>{u}</option>)}
      </select>
    </div>
  );
}
