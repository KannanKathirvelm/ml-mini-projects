import { readFileSync } from 'node:fs';
const meta = JSON.parse(readFileSync(new URL('../src/flavors.json', import.meta.url), 'utf8'));
export const FLAVOR_META = meta;
export const FLAVORS = Object.keys(meta);
export const appIdOf = (f) => `com.kannan.mlapps.${f}`;
