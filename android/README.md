# SPARK Mobile for Android — offline core + optional PC-backed AI (0.4 preview)

The Android application runs **independently offline** for local notes, tasks,
voice input and Health Connect. A new **SPARK DESKTOP AI / SECURE USB LINK**
screen also offers text-based conversational replies from the **existing**
Gemini or Groq provider configured on your Windows SPARK PC.

## Commission read-only mobile AI (no Android API key)

1. Install the latest debug APK (workflow below) on Android 14+.
2. Open desktop SPARK, select **PHONE / WATCH**, then **Start USB pairing**.
3. On your own Windows PC with an authorized Android USB cable and ADB:
   `adb devices` then `adb reverse tcp:38177 tcp:38177`.
   Verify Android authorizes this PC for debugging.
4. Select **Enable AI replies to Android** in desktop PHONE / WATCH.
   This explicit desktop action authorizes only text-generation replies.
5. In SPARK Mobile, open **SPARK DESKTOP AI / SECURE USB LINK**. Enter the
   short-lived eight-digit code and tap **PAIR WITH SPARK PC**.
6. Enter a question and tap **ASK SPARK (READ-ONLY)**. Android voice input,
   if available, only fills the question box: tap ASK separately to send.
7. Choose VOICE OUT if an installed Android *offline* English TTS voice is
   present. This is **not** VoiceStudio or cinematic voice.
8. Select **Disable mobile AI replies** or **Stop / revoke** on the PC,
   close the PHONE / WATCH panel, disconnect USB, and run
   `adb reverse --remove tcp:38177` after use.

**Privacy and credentials:** Android only knows an ephemeral per-pairing
session bearer. The desktop alone holds its workspace token and provider key.
The backend accepts the workspace token only from localhost and never exposes
agent tools to the mobile route. Text questions are sent to the selected
Gemini or Groq provider via the existing PC; they **may leave your device**
under the provider's processing policies. AI is OFF until the owner explicitly
enables it on the PC, and pairing expires after 10 minutes.

**Free-only policy:** No new subscription, API key or paid service is created.
SPARK uses whichever previously configured desktop provider you selected,
subject to its own free-tier availability and rate limits. No automatic paid
fallback, autonomous actions, business writes, purchase orders, emails,
browser operations, file edits or remote phone control are permitted.

**Limitations:** This is a PC-assisted AI chat, not an independent on-phone
Gemini model. It requires trusted USB and a running desktop SPARK backend.
Phone-to-PC conversation history is kept in temporary memory only until the
session is revoked. Desktop historical memory, arbitrary automation, skills,
wireless connectivity, cinematic voice and shared persistent conversation
sync are **not yet implemented on the phone**. CI and APK compilation do not
replace a real-device confirmation.

---

## Prior offline Android 0.3 functionality

**This APK runs SPARK Mobile independently on an Android 14+ phone.**
It is no longer just a Health Connect companion. It is a native Android
application and does not require the Windows SPARK desktop to launch,
make notes, maintain a local checklist or respond to supported commands.

## Available on the phone

- Native SPARK Mobile cockpit: dark console, text command input, quick
  access to Notes, Tasks, Status and the existing Health/USB panel.
- Offline command engine: 'note <text>', 'remember <text>', 'show notes',
  'delete note 1', 'add task <text>', 'list tasks', 'complete task 1',
  'time', 'status', 'help', and 'open health'.
- Up to 100 notes and 100 tasks, saved across app restarts in Android's
  app-private local preferences. No Cloudflare, Gemini, OpenAI token or
  paid API is needed. Clearing the app's data or uninstalling removes the
  local records. They are not automatically transferred to Windows.
- VOICE IN uses the installed Android speech-recognition provider on a tap.
  SPARK requests an offline result; this is a best-effort hint and the
  recognizer may use network processing depending on your phone's speech
  service. Text-only mode always works.
- VOICE OUT is off by default. It enables only when Android reports an
  installed offline English TTS voice. This is not Windows VoiceStudio.
- Existing Health Connect read and USB-only, manually paired summary
  transfer remain available under HEALTH CONNECT / USB PHONE LINK.

**Still not running independently on the phone:** desktop Python/Electron tools,
local on-device Gemini/Groq, browser control, historical memory, cross-device
sync, autonomous skill learning, wake word, remote phone automation,
VYNDI/VAOS business mutations. Unsupported questions receive an explicit
limitation rather than a fabricated AI answer. Tasks are not scheduled alerts.

**Privacy:** App backup is disabled. Notes/tasks are app-private but not
protected by a separate application passphrase. Do not save credentials,
sensitive records or company secrets in local notes. Android's VOICE IN
provider may contact the network; check your selected recognizer settings.
Existing USB/Health consent and permissions are unchanged.

## Installing SPARK Mobile

Open the green Build SPARK Android Companion GitHub Actions workflow for the
merged revision, download its spark-mobile-android-debug artifact, and install
app-debug.apk on an Android 14+ phone after reviewing the sideload warning.
The package name is still com.spark.companion, upgrading the earlier test
companion in place; the launcher display name becomes SPARK Mobile.

The GitHub artifact is a debug evaluation build, not a store-signed production
release. GitHub CI does not prove Android voice quality or your phone's
performance until physical-device acceptance is performed.

---

## Existing Health Connect and USB functions

## What SPARK actually supports

This is an **Android 14+ Health Connect seven-day activity reader**, ported from
the user's own `vyndivybes/ARKUS` Android companion. It reads three
permissioned record types: **exercise sessions, steps and distance**. It
does not connect directly to the Garmin fēnix 7 over Bluetooth and does not
log in to Garmin Connect. No Garmin cloud API credentials are needed or used.

**Garmin flow:** Pair/sync the fēnix 7 with the official Garmin Connect app,
enable **Garmin Connect → Health Connect** sharing on Android 14+, and grant
the SPARK Companion permission to read these types in Android's Health
Connect permission screen. Garmin transfers supported data *one way* after
successful device sync. Summaries from Health Connect may include other
apps or the phone itself; the source packages shown describe exercise
sessions only and cannot prove totals come exclusively from Garmin.

Official source: https://support.garmin.com/lv-LV/?faq=JToBEy0jfe6pIygark2Ui5

## Controlled ADB USB pairing (preview)

Requirements: Android 14+, an unlocked, trusted USB-connected Android phone,
free Android Platform Tools (`adb`) on the PC, and USB debugging approved
**on the phone for that specific PC**. Disable USB debugging and revoke the
PC's debug authorization afterward.

1. Open SPARK's **PHONE / WATCH** panel and click **Start USB pairing**. An
   eight-digit one-time code is displayed for two minutes.
2. With the phone connected by USB, on Windows run:

   ```powershell
   adb devices
   adb reverse tcp:38177 tcp:38177
   ```

   Confirm your device lists as authorized. If the reverse command reports
   an error, resolve USB debugging authorization; never enable a listener on
   `0.0.0.0` or expose the API to Wi-Fi.
3. On Android, enter the displayed code and press **Pair with SPARK over
   USB**. This does **not** transmit health information.
4. Press **Connect Health Connect** to grant the existing read-only
   permissions. Inspect the seven-day summary.
5. If you choose to share it, press **Send current summary to SPARK PC**.
   Open the PC's PHONE / WATCH panel to see the received summary, held only
   in memory. You can repeat the action after SPARK consumes the previous
   summary. No other phone content is accessible.
6. To revoke immediately, press **Stop / revoke** or close the desktop panel.
   Disconnect the cable, then run `adb reverse --remove tcp:38177` to clear
   forwarding and turn off USB debugging when finished.

**Scope and threat model:** The Windows listener binds only
`127.0.0.1:38177` and does not start unless the PC user clicks Start.
An eight-digit code has a five-attempt lockout; pairing grants a randomly
generated, in-memory session token for up to ten minutes. Transfer requests
are authenticated, replay-protected, bounded, single-summary only and never
auto-executed. Only the owning Electron cockpit may display the code, read
the accepted summary or revoke the listener. No account, paid service, API
token, Bluetooth or cloud sync is involved.

Cleartext on the phone's loopback is appropriate **only because the route
is an ADB USB reverse tunnel to your trusted PC**, not a network service.
Do not use this mechanism with an untrusted USB debugging host.
Pairing and transport tests are not proof of a successful real-device
session. The preview does not establish full Android phone control or
seamless wireless pairing.

## Build and install

GitHub Actions workflow **Build SPARK Android Companion** runs Gradle
`testDebugUnitTest assembleDebug` and publishes a `spark-mobile-android-debug`
APK artifact from `android/app/build/outputs/apk/debug/app-debug.apk`.
The debug build is for personal evaluation; it is **unsigned for production
distribution** and not a Play Store app. Download the artifact from that
successful Actions run, transfer it to your Android phone and install only
after reviewing Android's sideload/security prompt.

In the SPARK Companion app, tap **Connect Health Connect**, approve read
permissions in Android, and view a **Last 7 days** summary. Tap **Copy summary** or **Share activity summary** to transfer text manually
as before. A second option, described below, uses a manually paired Android
Debug Bridge (ADB) USB reverse tunnel. SPARK's **PHONE / WATCH** panel
discards either imported summary when it closes; no import is automatically
written to disk or uploaded to cloud services.

**Privacy:** The Android clipboard may be read by other apps; do not copy
sensitive activity summaries on an untrusted device. Sharing through Android's
chooser is an explicit user action and uses the receiving app's security
properties. Android requests INTERNET permission **only to contact a fixed 127.0.0.1:38177 endpoint** over ADB USB reverse forwarding. Cleartext Android network-security rules are scoped to loopback. No Bluetooth permission is requested.

There is no background sync, account pairing, LAN/Wi-Fi phone access,
remote desktop control, direct Garmin cloud access, workout writeback,
GPS route retrieval, live heart-rate feed or continuous wearable tracking.
Do not describe the preview as those capabilities.

### Original ARKUS source

- `vyndivybes/ARKUS/android/app/src/main/java/com/arkus/companion/MainActivity.kt`
- `vyndivybes/ARKUS/android/app/src/main/java/com/arkus/companion/SummaryFormatter.kt`
- ARKUS's Gradle and manifest definitions and Android unit tests

Code was adapted to package `com.spark.companion`, app label **SPARK
Companion**, and an explicit manual Copy Summary affordance. Existing
SPARK voice/AI control paths remain unchanged.
