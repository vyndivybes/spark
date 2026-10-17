# SPARK Android Companion — ported from ARKUS

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

## Build and install

GitHub Actions workflow **Build SPARK Android Companion** runs Gradle
`testDebugUnitTest assembleDebug` and publishes a `spark-android-health-connect-debug`
APK artifact from `android/app/build/outputs/apk/debug/app-debug.apk`.
The debug build is for personal evaluation; it is **unsigned for production
distribution** and not a Play Store app. Download the artifact from that
successful Actions run, transfer it to your Android phone and install only
after reviewing Android's sideload/security prompt.

In the SPARK Companion app, tap **Connect Health Connect**, approve read
permissions in Android, and view a **Last 7 days** summary. Tap
**Copy summary** or **Share activity summary**. Transfer the text to your
Windows PC by a method you choose and paste it into SPARK's **PHONE / WATCH**
panel. The summary stays in that visible panel's memory; closing the panel
discards it. Nothing is automatically uploaded or stored in SPARK.

**Privacy:** The Android clipboard may be read by other apps; do not copy
sensitive activity summaries on an untrusted device. Sharing through Android's
chooser is an explicit user action and uses the receiving app's security
properties. No Android INTERNET or Bluetooth permission is requested.

No background sync, Windows↔Android account pairing, remote control,
direct Garmin cloud access, workout writeback, GPS route retrieval,
live heart-rate feeds, or continuous wearable tracking is implemented.
Do not describe the preview as those capabilities.

### Original ARKUS source

- `vyndivybes/ARKUS/android/app/src/main/java/com/arkus/companion/MainActivity.kt`
- `vyndivybes/ARKUS/android/app/src/main/java/com/arkus/companion/SummaryFormatter.kt`
- ARKUS's Gradle and manifest definitions and Android unit tests

Code was adapted to package `com.spark.companion`, app label **SPARK
Companion**, and an explicit manual Copy Summary affordance. Existing
SPARK voice/AI control paths remain unchanged.
