package com.vayushastr.sparkcompanion

import android.app.Activity
import android.os.Bundle
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.graphics.Color
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.spec.ECGenParameterSpec

/** Offline device-identity setup. No pairing, network calls, or remote commands. */
class MainActivity : Activity() {
    private val alias = "spark_companion_p256_v1"

    private fun publicIdentity(): Pair<String, String> {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (!store.containsAlias(alias)) {
            val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
            generator.initialize(
                KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                    .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256)
                    .build()
            )
            generator.generateKeyPair()
        }
        val key = store.getCertificate(alias).publicKey.encoded
        val encoded = Base64.encodeToString(key, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        val fingerprint = MessageDigest.getInstance("SHA-256").digest(encoded.toByteArray(Charsets.US_ASCII))
            .joinToString("") { "%02x".format(it) }
        return encoded to fingerprint
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 56, 36, 36)
            setBackgroundColor(Color.rgb(14, 21, 34))
            gravity = Gravity.CENTER_HORIZONTAL
        }
        val title = TextView(this).apply {
            text = "SPARK COMPANION"
            textSize = 24f
            setTextColor(Color.WHITE)
        }
        val state = TextView(this).apply {
            text = "Not paired — secure transport is not yet commissioned."
            textSize = 16f
            setTextColor(Color.LTGRAY)
            setPadding(0, 20, 0, 20)
        }
        val identity = TextView(this).apply {
            text = "Device identity not generated"
            textSize = 12f
            setTextColor(Color.LTGRAY)
            setPadding(0, 16, 0, 20)
            setTextIsSelectable(true)
        }
        val generate = Button(this).apply {
            text = "Generate local device identity"
            setOnClickListener {
                try {
                    val (key, fingerprint) = publicIdentity()
                    identity.text = "Fingerprint: $fingerprint\n\nPublic key (shareable):\n$key"
                } catch (_: Exception) {
                    identity.text = "Device identity unavailable. Check Android Keystore support."
                }
            }
        }
        layout.addView(title)
        layout.addView(state)
        layout.addView(generate)
        layout.addView(identity)
        setContentView(layout)
    }
}
