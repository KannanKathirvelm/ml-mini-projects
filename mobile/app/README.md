# ML Mini Apps: seven Android apps from one codebase

Ionic 8 + React 18 + Capacitor 6 (TypeScript, Vite). One shared codebase builds **seven separately
installable apps**, one per ML project, all talking to the FastAPI server in `../server`
(contract: `../API.md`). APKs are built for free by **GitHub Actions**; download them from the
[Releases page](https://github.com/KannanKathirvelm/ml-mini-projects/releases) or the Actions run artifacts.

| Flavor       | App name              | Application ID                   | Screens |
|--------------|-----------------------|----------------------------------|---------|
| `creditcard` | Card Fraud Check      | `com.kannan.mlapps.creditcard`   | Check form + probability gauge/verdict, Metrics |
| `upi`        | UPI Scam Shield       | `com.kannan.mlapps.upi`          | Example picker + full form, LOW/MEDIUM/HIGH badge + reasons, Metrics incl. recall by scam type |
| `stocks`     | Stock Forecast AI     | `com.kannan.mlapps.stocks`       | **Markets** tab: NSE open/closed pill, debounced search over all ~2,600 NSE listings, watchlist with live quotes, popular stocks/indices. **Forecast** tab: live quote header (₹, day range, as-of IST, auto-refresh every 30 s while NSE is open and the app is visible), intraday 1m/5m chart, history + RNN/LSTM forecast, 1-30 day slider, RNN/LSTM/naive metrics + back-test chart, model badge ("Universal India model (trained on ~50 NSE stocks)" or per-ticker; "Train" only offered for per-ticker servers), why-it-can't-beat-naive note, pull-to-refresh |
| `finance`    | Market Insight Agents | `com.kannan.mlapps.finance`      | Live quote header, popular Indian picker + NSE search, outlook badge, sector/industry/market cap, summary, price + SMA chart, vs NIFTY 50 card (1m/3m/1y returns, beta, relative strength), indicators, one card per agent, bullish/bearish/risks, headlines, offline/LLM mode label, disclaimer |
| `prices`     | Price Compare         | `com.kannan.mlapps.prices`       | Search, product groups with best deal and savings, offer list, history chart, track with target; Tracked tab with alerts check |
| `faces`      | Face Detect           | `com.kannan.mlapps.faces`        | Camera/gallery (`@capacitor/camera`), YuNet/Haar/Both, blur, threshold, annotated image(s), counts, times |
| `objects`    | Object Detect         | `com.kannan.mlapps.objects`      | Camera/gallery, model select, class filter (from `/classes`), conf/IoU sliders, annotated image, per-class counts, time |

Every app also has a **Settings** tab: server URL (saved with `@capacitor/preferences`), presets,
**Test connection** (`GET /health`) and a **mock mode** toggle (an offline backend with the same shapes, India data included).

While the server is asleep (Render free plan), every screen shows a **"Server waking up… (free hosting, up to a minute)"**
banner. Until the first successful response, requests get a 95 s timeout and are retried twice (GETs on timeout; any
method on connection/502/503/504 errors, so a POST is never run twice), and the app pings `/health` at start-up to begin
waking the server before you tap anything.

## Architecture

```
src/
  flavors.json        single source of truth: name, letter, colour per flavor (used by Vite, Gradle and the icon script)
  flavor.ts           current flavor (VITE_APP_FLAVOR is a build-time constant)
  App.tsx             tab shell; loads only the built flavor's feature module (other flavors are tree-shaken out)
  settings.tsx        server URL + mock flag (Capacitor Preferences; localStorage on web)
  hooks.ts            useAsync/useLoad with a "slow" flag after 5 s
  api/types.ts        types mirroring API.md (India fields optional, so older servers still work)
  api/client.ts       typed fetch client, long timeouts (120 s, 300 s for training), cold-start retry + "waking up" state, {"detail"} error parsing
  api/live.ts         India quotes/intraday, normalised so screens see one shape
  api/mock.ts         offline mock backend with the same shapes (draws boxes on your own photo for faces/objects)
  components/         Page (+ waking banner), Status (loading/error/empty), Chart (chart.js), ImagePicker, India (NSE pill, popular picker, search), Live (quote header, intraday, watchlist, polling), forms
  features/<flavor>.tsx   screens for each app
android/              ONE Capacitor Android project with Gradle productFlavors
scripts/build-android.mjs   build one/several/all APKs (macOS and Linux/CI)
../../.github/workflows/android-apks.yml   CI build + releases
scripts/gen-icons.py        per-flavor launcher icons, adaptive icons, splash colour, app name
```

### Why Android `productFlavors` (and not seven Android projects)

A single `android/` directory with seven `productFlavors` (generated in `android/app/build.gradle`
from `src/flavors.json`) gives each APK its own `applicationId`, app name, icon and splash colour
through flavor source sets (`android/app/src/<flavor>/res`, plus a flavor manifest that adds camera/photo
permissions only for `faces` and `objects`). Shared native code, plugins and Gradle caches are reused,
so the second and later builds take a few seconds, and there is only one `node_modules` and one
Android project on disk (the machine is short on space). The web bundle differs per flavor, so the
build script rebuilds it, runs `cap sync`, then `assemble<Flavor>Debug`, one flavor at a time.

## Toolchain

- Capacitor **6.2** (Android Gradle Plugin 8.2.1, compileSdk/targetSdk 34, minSdk 22), Gradle wrapper **8.10**.
- **CI (GitHub Actions): Temurin JDK 17**, the JDK AGP 8.2 is built and tested against.
- **Local Mac:** JDK 23 (`/Library/Java/JavaVirtualMachines/jdk-23.jdk`). The GraalVM JDK 17 on this machine fails
  AGP's `JdkImageTransform` (`jlink`: *Module jdk.internal.vm.ci not found*), so the script skips a GraalVM `JAVA_HOME`.
  Order used: `BUILD_JAVA_HOME`, `JAVA_HOME` (unless GraalVM), the Mac JDK 23.
- Android SDK from `ANDROID_HOME` / `ANDROID_SDK_ROOT`, else the default Android Studio path for the OS.
  `local.properties` is not needed (and is git-ignored).
- The project path contains a space (`My new project /`); Gradle, AAPT and Capacitor handle it fine.

## Run in the browser

```bash
npm install
VITE_APP_FLAVOR=upi npm run dev          # http://localhost:5173
VITE_APP_FLAVOR=stocks VITE_API_URL=http://localhost:7860 npm run dev
```

On the web, Camera/Gallery fall back to a file picker. Turn on mock mode in Settings to work without a server.

## Build

```bash
npm run build                 # typecheck + web build of the flavor in .env
npm run build:flavors         # typecheck + web build of all 7 flavors (into .build/web/<flavor>)
npm run build:android -- upi  # one APK -> dist-apk/upi-debug.apk
npm run build:android -- upi faces stocks
npm run build:all             # all 7 APKs -> dist-apk/<flavor>-debug.apk
npm run icons                 # regenerate icons/app names after editing src/flavors.json (needs Pillow)
```

APKs are debug-signed (installable, not for the Play Store).

## GitHub Actions builds (free)

`.github/workflows/android-apks.yml` runs on a free `ubuntu-latest` runner:

- **Triggers:** every push to `main` that touches `mobile/app/**` (or the workflow); tags `v*`;
  **Actions → Android APKs → Run workflow** (inputs: `flavors`, default `all`, e.g. `upi faces`; `release` checkbox).
- **Steps:** Node 20 (npm cache) → `npm ci` → Temurin 17 → Android SDK (`android-actions/setup-android`) →
  Gradle wrapper validation + Gradle cache → `npm run build:flavors` (typecheck + web build of all 7) →
  `npm run build:android -- <flavors>` (vite build → `cap sync` → `assemble<Flavor>Debug`, per flavor). About 10-15 min for all 7.
- **Where to download:**
  - every run: the run page → **Artifacts** → `ml-mini-apps-apks` (a zip of the APKs, kept 30 days; needs a GitHub login);
  - tags `v*` and runs with `release` ticked: **https://github.com/KannanKathirvelm/ml-mini-projects/releases**.
    A `v1.2.0` tag gets its own release; a manual `release` run updates the rolling pre-release **`apks-latest`**.
    Release assets download directly on a phone, no login needed.

### Server URL

The build-time default comes from `VITE_API_URL` (CI: the `API_URL` repo variable, falling back to
`https://ml-mini-projects.onrender.com`; locally: `.env`). Change it at runtime in **Settings**:

| Where the app runs | URL to use |
|--------------------|------------|
| Anywhere (hosted) | `https://ml-mini-projects.onrender.com` (free; first request after idle ~1 min) |
| Android emulator, server on this Mac | `http://10.0.2.2:7860` (preset button) |
| Browser on this Mac | `http://localhost:7860` |
| Real phone on the same Wi-Fi | `http://<your Mac's LAN IP>:7860` (find it with `ipconfig getifaddr en0`; the server must listen on `0.0.0.0`) |
| Real phone anywhere, server on this Mac | an HTTPS tunnel URL (Cloudflare quick-tunnel URLs change on every restart) |

Plain `http://` works because the Android apps allow cleartext traffic
(`res/xml/network_security_config.xml`) and Capacitor `allowMixedContent`. Tighten this before any release build.

## Install on a phone

1. On the phone, open **https://github.com/KannanKathirvelm/ml-mini-projects/releases** in Chrome and tap the
   `<flavor>-debug.apk` you want (e.g. `stocks-debug.apk`). (Or download the Actions artifact zip on a computer and copy the APKs over.)
2. Open the downloaded file. Android says installing from this source is blocked: tap **Settings** and turn on
   **Install unknown apps** (Allow from this source) for Chrome (or your file manager), then go back and tap **Install**.
   On older Android: Settings → Security → **Unknown sources**.
3. Play Protect may warn about an unrecognised developer (the APKs are debug-signed): choose **Install anyway**.
4. Repeat for each app. All seven install side by side because their application IDs differ. Updating needs the same
   signing key: unless the optional `ANDROID_DEBUG_KEYSTORE_BASE64` secret is set (below), every CI run signs with a fresh
   debug key, so if an update says "App not installed", uninstall the old app first.

**Optional: stable signing key for CI** (so new builds install as updates). Create a debug keystore once and store it
as a repository **secret** (Settings → Secrets and variables → Actions → Secrets) named `ANDROID_DEBUG_KEYSTORE_BASE64`:

```bash
keytool -genkeypair -v -keystore debug.keystore -storepass android -keypass android -alias androiddebugkey \
  -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US"
base64 -i debug.keystore | pbcopy   # paste as the secret value; keep the file out of git
```

USB alternative: enable Developer options + USB debugging, then `adb install -r dist-apk/upi-debug.apk`.

## Server deviations noticed (app follows the server where harmless)

- Store name is `FakeStoreAPI` (API.md example says `FakeStore`); offer `image` is always `null`.
- Haar face `score` is a cascade weight (e.g. 8.05), not 0-1; the app doesn't display it.
- Money values come back as floats (e.g. `14990.17`); the app rounds for display.
- India endpoints (API.md sections 8 and 9) are optional in the app: on an older server without them the NSE pill,
  live quote, intraday chart and benchmark card are hidden, search becomes a plain symbol box, a built-in popular list
  is used, and a forecast 404 offers "Train this ticker". On a v1.1 server (`/api/stocks/tickers` has `"universal": true`)
  a 404 means "no price data" and training is not offered for universal forecasts.
- `display.change` from the quote endpoint already contains the percentage (`"+₹5.50 (+0.38%)"`), so the app does not append it again.
- IST timestamps are ISO-8601 (`2026-10-23T15:29:00+05:30`); the app shows them as `23 Oct, 15:29 IST` (or `15:29 IST` today).
