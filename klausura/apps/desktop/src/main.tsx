import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { buildTokenCss } from '@klausura/ui-tokens';
import { App } from './App.js';
import './styles.css';

// Das Token-Stylesheet wird aus den Konstanten ERZEUGT, nicht danebengelegt.
// Damit gibt es genau eine Quelle und die Werte können nicht auseinanderlaufen.
const style = document.createElement('style');
style.dataset['source'] = 'klausura-tokens';
style.textContent = buildTokenCss();
document.head.prepend(style);

const host = document.getElementById('root');
if (host === null) throw new Error('Wurzelelement fehlt.');
createRoot(host).render(<StrictMode><App /></StrictMode>);
