# SPARK Android Companion — Health Connect + controlled USB pairing preview

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
`testDebugUnitTest assembleDebug` and publishes a `spark-android-health-connect-debug`
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
