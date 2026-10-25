#!/usr/bin/env node
// Build debug APKs for one, several or all flavors.
//   npm run build:android -- upi            (one)
//   npm run build:android -- upi faces      (several)
//   npm run build:all                       (all seven)
// Steps per flavor: vite build (VITE_APP_FLAVOR) -> cap sync android (APP_ID/APP_NAME) ->
// gradlew assemble<Flavor>Debug -> copy to dist-apk/<flavor>-debug.apk
import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { FLAVORS, FLAVOR_META, appIdOf } from './flavors.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const ANDROID = join(ROOT, 'android');
const OUT = join(ROOT, 'dist-apk');

// JDK: Capacitor 6 / AGP 8.2.1 needs JDK 17+. Order: BUILD_JAVA_HOME, then JAVA_HOME (what actions/setup-java sets in CI),
// then the Oracle JDK 23 on the author's Mac. A GraalVM JAVA_HOME is skipped: its JDK 17 breaks AGP's jlink step
// (missing jdk.internal.vm.ci).
const isGraal = (p) => /graal/i.test(p);
const JDK_CANDIDATES = [
  process.env.BUILD_JAVA_HOME,
  process.env.JAVA_HOME && !isGraal(process.env.JAVA_HOME) ? process.env.JAVA_HOME : null,
  process.platform === 'darwin' ? '/Library/Java/JavaVirtualMachines/jdk-23.jdk/Contents/Home' : null,
  process.env.JAVA_HOME,
].filter(Boolean);
const JAVA_HOME = JDK_CANDIDATES.find((p) => existsSync(join(p, 'bin', process.platform === 'win32' ? 'java.exe' : 'java')));
if (!JAVA_HOME) { console.error('No JDK found. Set JAVA_HOME (or BUILD_JAVA_HOME) to a JDK 17+ (not GraalVM).'); process.exit(1); }
// Android SDK: ANDROID_HOME / ANDROID_SDK_ROOT (set by GitHub runners and android-actions/setup-android), else the
// default Android Studio location for this OS. No local.properties needed.
const HOME = process.env.HOME || process.env.USERPROFILE || '';
const SDK_DEFAULT = process.platform === 'darwin' ? join(HOME, 'Library/Android/sdk')
  : process.platform === 'win32' ? join(process.env.LOCALAPPDATA || HOME, 'Android/Sdk') : join(HOME, 'Android/Sdk');
const ANDROID_HOME = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT || SDK_DEFAULT;
if (!existsSync(ANDROID_HOME)) { console.error(`Android SDK not found at ${ANDROID_HOME}. Set ANDROID_HOME.`); process.exit(1); }

// Accepts "upi faces", "upi,faces" or "all".
const args = process.argv.slice(2).filter((a) => !a.startsWith('-')).flatMap((a) => a.split(/[,\s]+/)).filter(Boolean);
const targets = args.length === 0 || args.includes('all') ? FLAVORS : args;
const bad = targets.filter((t) => !FLAVORS.includes(t));
if (bad.length) { console.error(`Unknown flavor(s): ${bad.join(', ')}. Valid: ${FLAVORS.join(', ')}, all`); process.exit(1); }

const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
const gradlew = join(ANDROID, process.platform === 'win32' ? 'gradlew.bat' : 'gradlew');
const run = (cmd, argv, opts = {}) => execFileSync(cmd, argv, { stdio: 'inherit', cwd: ROOT, ...opts });
const cap = (f) => f[0].toUpperCase() + f.slice(1);

console.log(`JAVA_HOME=${JAVA_HOME}\nANDROID_HOME=${ANDROID_HOME}\nVITE_API_URL=${process.env.VITE_API_URL ?? '(from .env)'}\nFlavors: ${targets.join(', ')}`);
if (!existsSync(join(ANDROID, 'app/src', targets[0], 'res/values/flavor.xml'))) run('python3', ['scripts/gen-icons.py']);
run(npx, ['tsc', '--noEmit']);
mkdirSync(OUT, { recursive: true });

const results = [];
for (const f of targets) {
  const t0 = Date.now();
  const meta = FLAVOR_META[f];
  console.log(`\n========== ${f}: ${meta.appName} (${appIdOf(f)}) ==========`);
  run(npx, ['vite', 'build', '--logLevel', 'warn'], { env: { ...process.env, VITE_APP_FLAVOR: f, WEB_OUT_DIR: 'dist' } });
  run(npx, ['cap', 'sync', 'android'], { env: { ...process.env, APP_ID: appIdOf(f), APP_NAME: meta.appName } });
  run(gradlew, [`assemble${cap(f)}Debug`, '--console=plain', '-q', '--warning-mode=none'], {
    cwd: ANDROID, env: { ...process.env, JAVA_HOME, ANDROID_HOME, ANDROID_SDK_ROOT: ANDROID_HOME },
  });
  const apk = join(ANDROID, 'app/build/outputs/apk', f, 'debug', `app-${f}-debug.apk`);
  const dest = join(OUT, `${f}-debug.apk`);
  copyFileSync(apk, dest);
  results.push({ flavor: f, appId: appIdOf(f), apk: dest, mb: (statSync(dest).size / 1048576).toFixed(1), s: ((Date.now() - t0) / 1000).toFixed(0) });
}
console.log('\nBuilt:');
for (const r of results) console.log(`  ${r.flavor.padEnd(11)} ${r.appId.padEnd(30)} ${r.mb.padStart(5)} MB  ${r.s}s  ${r.apk}`);
