# UniMind Android

This native shell tracks the current web application (v1.5.1), including language preferences, account settings, institution workspaces, course authorization and saved courses. The unmerged KnowledgeBuilder implementation is not included.

## Build

Use Node 22.13+ (Node 24 is supported), JDK 21 and Android SDK platform/build tools 36. Install dependencies in this checkout only; do not overwrite a macOS checkout's `node_modules` or Python environments.

From `frontend`:

```sh
npm ci
npx tsc -b
npm run build
npx cap sync android
cd android
./gradlew assembleDebug
```

On Windows use `npm.cmd`, `npx.cmd` if PowerShell blocks npm scripts, and `gradlew.bat assembleDebug`. Set `JAVA_HOME` and `ANDROID_HOME` in the build shell or configure Android Studio. Keep `local.properties`, `.gradle`, build directories, `app/src/main/assets/public`, APKs and AppleDouble `._*` files out of Git. The Gradle wrapper script must remain executable on macOS.

The package is `com.korsonedu.unimind`, app name `UniMind`, minSdk 24 and targetSdk 36. `adjustResize` and SystemBars CSS insets support the keyboard and edge-to-edge layout. HTTP is enabled for explicitly selected LAN/USB development servers; use HTTPS for the deployed server.

## Server and authentication

Android login/register screens and Settings → General expose the server selector and `/health/` check. Presets support emulator (`10.0.2.2:8000`), USB (`127.0.0.1:8000`, with `adb reverse tcp:8000 tcp:8000`) and HTTPS production. Changing the server cancels queries, clears the session/query cache and reloads login before new requests can carry credentials.

Native tokens live in Capacitor Preferences and are restored before authenticated requests. Web/Electron retain Cookie + CSRF behavior and only persist user information in localStorage. Native REST/SSE use Authorization, WebSockets use one-use 30-second tickets, and protected media use path-bound 300-second tickets. Video renews its ticket while preserving playback position. Preferences uses app-private platform storage; this is not a keystore-backed secret vault.

The corresponding backend must enable `CORS_ALLOW_CAPACITOR_ORIGINS=true` or explicitly allow the configured native origin in both CORS and `WS_ALLOWED_ORIGINS`. Use shared Redis cache for one-use WebSocket tickets across backend workers. Existing institution/course authorization still applies when media tickets are redeemed.

## Offline trial and verification

Login offers a server-free trial with local notes, a practice sample and a learning calendar. Demo data, real users and server origins have separate cache partitions. Demo edits never sync to a real account. A cached real session can read available offline data after network failure; an explicit authentication rejection revokes access. Server-dependent actions require reconnection.

```sh
node --test tests/serverConfig.test.ts tests/offlineCache.test.ts tests/offlineSession.test.ts
npm run preview -- --host 127.0.0.1 --port 4173
node tests/mobile-touch.e2e.mjs
node tests/native-auth.e2e.mjs
node tests/offline-native.e2e.mjs
```

Browser checks require a local Playwright installation and Chromium. Optional `PLAYWRIGHT_MODULE` and `CHROMIUM_PATH` select existing installations. The offline test uses an ESM module URL; the other runners accept a package/directory path. `MOBILE_LOCALE=en` runs the layout suite in English. Test evidence is written to ignored `releases/test-artifacts/`.

Before release, install on a physical Android device and check keyboard resize, status/navigation bars, hardware back, background/resume, weak networking, real backend login, institution course grants, protected media playback and offline edits/reconnection. Browser bridge mocks do not replace native device validation.
