# ML Mini Apps: seven Android apps from one codebase

Ionic 8 + React 18 + Capacitor 6 (TypeScript, Vite). One shared codebase builds **seven separately
installable apps**, one per ML project, all talking to the FastAPI server in `../server`
(contract: `../API.md`).

| Flavor       | App name              | Application ID                   | Screens |
|--------------|-----------------------|----------------------------------|---------|
| `creditcard` | Card Fraud Check      | `com.kannan.mlapps.creditcard`   | Check form + probability gauge/verdict, Metrics |
| `upi`        | UPI Scam Shield       | `com.kannan.mlapps.upi`          | Example picker + full form, LOW/MEDIUM/HIGH badge + reasons, Metrics incl. recall by scam type |
| `stocks`     | Stock Forecast AI     | `com.kannan.mlapps.stocks`       | NSE status pill, popular Indian stocks/indices + trained tickers + free text, history + RNN/LSTM forecast chart, 1-30 day slider, RNN/LSTM/naive metrics + test chart, "Train this ticker", why-it-can't-beat-naive note |
| `finance`    | Market Insight Agents | `com.kannan.mlapps.finance`      | NSE status pill, popular Indian picker + search, outlook badge, summary, price + SMA chart, vs NIFTY 50 card, indicators, one card per agent, bullish/bearish/risks, headlines, offline/LLM mode label, disclaimer |
| `prices`     | Price Compare         | `com.kannan.mlapps.prices`       | Search, product groups with best deal and savings, offer list, history chart, track with target; Tracked tab with alerts check |
| `faces`      | Face Detect           | `com.kannan.mlapps.faces`        | Camera/gallery (`@capacitor/camera`), YuNet/Haar/Both, blur, threshold, annotated image(s), counts, times |
| `objects`    | Object Detect         | `com.kannan.mlapps.objects`      | Camera/gallery, model select, class filter (from `/classes`), conf/IoU sliders, annotated image, per-class counts, time |

Every app also has a **Settings** tab: server URL (saved with `@capacitor/preferences`), presets,
**Test connection** (`GET /health`) and a **mock mode** toggle.

## Architecture

```
src/
  flavors.json        single source of truth: name, letter, colour per flavor (used by Vite, Gradle and the icon script)
  flavor.ts           current flavor (VITE_APP_FLAVOR is a build-time constant)
  App.tsx             tab shell; loads only the built flavor's feature module (other flavors are tree-shaken out)
  settings.tsx        server URL + mock flag (Capacitor Preferences; localStorage on web)
  hooks.ts            useAsync/useLoad with a "slow" flag after 5 s ("Server waking up…")
  api/types.ts        types mirroring API.md
  api/client.ts       typed fetch client, long timeouts (120 s, 300 s for training), {"detail"} error parsing
  api/mock.ts         offline mock backend with the same shapes (draws boxes on your own photo for faces/objects)
  components/         Page, Status (loading/error/empty), Chart (chart.js), ImagePicker, India (NSE pill, popular picker), forms
  features/<flavor>.tsx   screens for each app
android/              ONE Capacitor Android project with Gradle productFlavors
scripts/build-android.mjs   build one/several/all APKs
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

## Toolchain (what actually builds on this Mac)

- Capacitor **6.2** (Android Gradle Plugin 8.2.1, compileSdk/targetSdk 34, minSdk 22).
- Gradle wrapper set to **8.10** (already in `~/.gradle`; avoids downloading another 440 MB distribution).
- **JDK 23** (`/Library/Java/JavaVirtualMachines/jdk-23.jdk`). The GraalVM JDK 17 on this machine fails
  AGP's `JdkImageTransform` (`jlink`: *Module jdk.internal.vm.ci not found*), so the script uses JDK 23
  and sets `JAVA_HOME` only for the Gradle process. Override with `BUILD_JAVA_HOME=/path/to/jdk`.
- The project path contains a space (`My new project /`); Gradle, AAPT and Capacitor handle it fine, so
  no symlink or copy is needed.

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

## Server URL

The build-time default comes from `VITE_API_URL` in `.env` (currently the public Cloudflare quick tunnel
`https://web-subsidiary-makers-infinite.trycloudflare.com`). Change it at runtime in **Settings**:

| Where the app runs | URL to use |
|--------------------|------------|
| Android emulator, server on this Mac | `http://10.0.2.2:7860` (preset button) |
| Browser on this Mac | `http://localhost:7860` |
| Real phone on the same Wi-Fi | `http://<your Mac's LAN IP>:7860` (find it with `ipconfig getifaddr en0`; the server must listen on `0.0.0.0`) |
| Real phone anywhere | the HTTPS tunnel/hosted URL |

**Quick-tunnel URLs change every time the tunnel restarts.** When that happens, paste the new URL
into Settings (it is remembered), or set `VITE_API_URL` in `.env` and rebuild.

Plain `http://` works because the Android apps allow cleartext traffic
(`res/xml/network_security_config.xml`) and Capacitor `allowMixedContent`. Tighten this before any release build.

## Install on a phone

- USB: enable Developer options + USB debugging, then
  `~/Library/Android/sdk/platform-tools/adb install -r dist-apk/upi-debug.apk` (repeat per APK).
- Without USB: copy the `.apk` to the phone (cloud drive, email, cable), open it, and allow
  "Install unknown apps" for the app you opened it from.

All seven install side by side because their application IDs differ.

## Server deviations noticed (app follows the server where harmless)

- Store name is `FakeStoreAPI` (API.md example says `FakeStore`); offer `image` is always `null`.
- Haar face `score` is a cascade weight (e.g. 8.05), not 0-1; the app doesn't display it.
- Money values come back as floats (e.g. `14990.17`); the app rounds for display.
- India endpoints (`/api/india/popular`, `/api/india/market-status`) and the finance `benchmark` field are
  optional in the app: when missing, the NSE pill and benchmark card are hidden and a built-in
  popular list is used.
