# SPARK Companion — Android foundation

Personal-use Android starter. It generates a non-exportable private P-256 signing
key inside Android Keystore and displays the corresponding public key and
SHA-256 fingerprint. It uses no remote APIs and makes no network calls.

**Important:** This is **not yet a paired device application**. The desktop
`spark_android_pairing.PairingRegistry` is an ephemeral approval registry only.
It does not implement cryptographic proof of private-key possession, session
authentication, TLS/Noise transport, desktop relay, Android commands, or phone
permissions. Never treat a displayed public key as proof that the phone is
connected or authorized. The Android app has no remote-control permissions.

Open this directory in Android Studio with Android SDK 35 and JDK 17.
Use Gradle sync and the standard Run/Build workflow. A Gradle wrapper is
intentionally not checked in until its binary and distribution checksum can be
independently verified. An APK has not been built or tested on a device.

Next gates: authenticated key-possession challenge, owner-approved QR exchange,
mutually authenticated encrypted transport, replay-resistant sessions, revocation,
Android runtime permission UX and device/on-PC acceptance tests. All remain disabled.
