// Typecheck once, then build the web bundle for every flavor into .build/web/<flavor> (sanity check for CI / `npm run build:flavors`).
import { execSync } from 'node:child_process';
import { FLAVORS } from './flavors.mjs';

execSync('npx tsc --noEmit', { stdio: 'inherit' });
for (const f of FLAVORS) {
  console.log(`\n=== vite build: ${f} ===`);
  execSync('npx vite build --logLevel warn', { stdio: 'inherit', env: { ...process.env, VITE_APP_FLAVOR: f, WEB_OUT_DIR: `.build/web/${f}` } });
}
console.log('\nAll flavors built.');
