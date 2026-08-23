/**
 * Zahl und Einheit bleiben getrennt, und das Präfix bleibt stehen.
 *
 * CLAUDE.md Regel 8: die Eingabe rechnet NIE stillschweigend um. `kΩ` und `Ω`
 * sind getrennte Eingaben. Erst die Bewertung (M2) darf umrechnen — und
 * vergibt dabei den Fehlercode E-POT, wenn die Grössenordnung abweicht.
 * Ohne diese Trennung verschluckt die tolerante Bewertung genau die
 * Fehlerklasse, die das Produkt sichtbar machen soll.
 */
export interface Quantity {
  readonly value: number;
  readonly unit: string;
}

/**
 * Liest eine Dezimalzahl in deutscher Schreibweise. Der Punkt wird ebenfalls
 * akzeptiert, weil Zehnerblöcke ihn liefern — aber nur einer von beiden.
 */
export function parseDecimal(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === '') return null;

  const separators = (trimmed.match(/[.,]/g) ?? []).length;
  if (separators > 1) return null;

  const normalized = trimmed.replace(',', '.');
  if (!/^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/.test(normalized)) return null;

  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

export function parseQuantity(value: string, unit: string): Quantity | null {
  const parsed = parseDecimal(value);
  if (parsed === null) return null;
  return { value: parsed, unit: unit.trim() };
}

export function formatDecimal(value: number): string {
  return String(value).replace('.', ',');
}
