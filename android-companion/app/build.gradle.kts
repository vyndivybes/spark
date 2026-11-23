plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "com.vayushastr.sparkcompanion"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.vayushastr.sparkcompanion"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
    buildTypes {
        release { isMinifyEnabled = false }
    }
}
kotlin { jvmToolchain(17) }
