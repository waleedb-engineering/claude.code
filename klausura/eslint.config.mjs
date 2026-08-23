// @ts-check
import js from '@eslint/js';
import tseslint from 'typescript-eslint';

/**
 * Die Grenzregel (docs/klausura/08-architecture.md):
 * packages/core ist reine Domäne. Kein IO, keine Uhr, kein Zufall.
 * Zeit kommt aus ClockPort, Zufall aus einem injizierten Seed.
 * Erzwungen wird das hier, nicht durch Disziplin.
 */
const coreForbidden = [
  {
    selector: "CallExpression[callee.object.name='Date'][callee.property.name='now']",
    message: 'core darf keine Uhr lesen. Zeit kommt aus ClockPort.',
  },
  {
    selector: "NewExpression[callee.name='Date'][arguments.length=0]",
    message: 'core darf keine Uhr lesen. Zeit kommt aus ClockPort.',
  },
  {
    selector: "CallExpression[callee.object.name='Math'][callee.property.name='random']",
    message: 'core darf keinen ungeseedeten Zufall ziehen.',
  },
  {
    selector: "CallExpression[callee.name='fetch']",
    message: 'core darf kein Netz benutzen. Netzzugriff gehört in einen Adapter.',
  },
];

export default tseslint.config(
  { ignores: ['**/node_modules/**', '**/dist/**', '**/*.d.ts', '**/.expo/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',
    },
  },
  {
    files: ['packages/core/**/*.ts', 'packages/model/**/*.ts'],
    rules: {
      'no-restricted-syntax': ['error', ...coreForbidden],
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            { group: ['node:*', 'fs', 'path', 'http', 'https', 'crypto'], message: 'core kennt kein IO.' },
            { group: ['react', 'react-*', '@tauri-apps/*', 'expo*'], message: 'core kennt keine Plattform.' },
            { group: ['@klausura/adapters-*', '@klausura/storage-*', '@klausura/ui-*'], message: 'core kennt nur model und ports.' },
          ],
        },
      ],
    },
  },
  {
    // Tests duerfen die verbotenen Konstrukte nennen, um sie zu pruefen, und
    // duerfen die Attrappen importieren — der Produktionscode von core darf
    // beides nicht. Genau darum steht adapters-fake dort als devDependency.
    files: ['**/*.test.ts'],
    rules: { 'no-restricted-syntax': 'off', 'no-restricted-imports': 'off' },
  },
);
