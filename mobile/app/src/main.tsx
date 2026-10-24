import '@ionic/react/css/core.css';
import '@ionic/react/css/normalize.css';
import '@ionic/react/css/structure.css';
import '@ionic/react/css/typography.css';
import '@ionic/react/css/padding.css';
import '@ionic/react/css/flex-utils.css';
import '@ionic/react/css/display.css';
import '@ionic/react/css/palettes/dark.system.css';
import './theme.css';

import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { FLAVOR } from './flavor';

function applyBrand() {
  const hex = FLAVOR.color;
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  const shade = (k: number) => '#' + [r, g, b].map((c) => Math.round(c * k).toString(16).padStart(2, '0')).join('');
  const tint = (k: number) => '#' + [r, g, b].map((c) => Math.round(c + (255 - c) * k).toString(16).padStart(2, '0')).join('');
  const s = document.documentElement.style;
  s.setProperty('--ion-color-primary', hex);
  s.setProperty('--ion-color-primary-rgb', `${r},${g},${b}`);
  s.setProperty('--ion-color-primary-contrast', '#ffffff');
  s.setProperty('--ion-color-primary-contrast-rgb', '255,255,255');
  s.setProperty('--ion-color-primary-shade', shade(0.88));
  s.setProperty('--ion-color-primary-tint', tint(0.1));
  document.title = FLAVOR.appName;
}
applyBrand();

createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
);
