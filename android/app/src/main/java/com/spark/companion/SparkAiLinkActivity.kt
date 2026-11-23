package com.spark.companion

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.speech.RecognizerIntent
import android.speech.tts.TextToSpeech
import android.text.InputFilter
import android.text.InputType
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.Locale

/**
 * SPARK Mobile's optional PC-backed AI conversation. Always user initiated:
 * no silent prompts, tool calls, autonomous browser/PC actions or secrets.
 * Requires trusted USB + ADB reverse and desktop-side AI consent.
 */
class SparkAiLinkActivity : ComponentActivity() {
    private var token: String? = null
    private var sequence = 0
    private lateinit var promptInput: EditText
    private lateinit var status: TextView
    private lateinit var conversation: TextView
    private lateinit var send: Button
    private lateinit var sync: Button
    private lateinit var mobileStore: MobilePreferencesStore
    private var requestBusy = false
    private lateinit var voiceToggle: Button
    private var tts: TextToSpeech? = null
    private var speaking = false
    private var localVoiceReady = false
    private var transcript = StringBuilder()

    private val speechRecognizer = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val heard = if (result.resultCode == Activity.RESULT_OK)
            result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
        else null
        if (heard != null && UsbPairingProtocol.validChatPrompt(heard))
            promptInput.setText(heard) // Never auto-send microphone transcription.
        else status.text = "No supported speech result. Type your question instead."
    }

    private fun label(value: String, size: Float = 15f): TextView =
        TextView(this).apply {
            text = value
            textSize = size
            setTextColor(Color.rgb(216, 233, 243))
            setPadding(10, 12, 10, 12)
        }

    private fun button(value: String, run: () -> Unit): Button =
        Button(this).apply {
            text = value
            isAllCaps = false
            setOnClickListener { run() }
        }

    private fun append(sender: String, message: String) {
        if (transcript.length > 9000) transcript.delete(0, transcript.length - 6000)
        transcript.append(sender).append(": ").append(message.take(3000)).append("\n\n")
        conversation.text = transcript.toString()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        mobileStore = MobilePreferencesStore(this)
        window.statusBarColor = Color.rgb(9, 16, 32)
        window.navigationBarColor = Color.rgb(9, 16, 32)
        val outer = ScrollView(this).apply { isFillViewport = true }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 18, 24, 24)
            setBackgroundColor(Color.rgb(9, 16, 32))
        }
        root.addView(label("SPARK  /  PC LINK", 24f))
        root.addView(label(
            "Read-only AI replies using your SPARK PC's configured provider. " +
            "Open PC PHONE / WATCH, Start USB pairing, run adb reverse " +
            "tcp:38177 tcp:38177. Enable AI replies and/or personal notes/tasks sync separately on the PC. " +
            "AI questions go to your selected provider via the PC. Personal sync never goes to the cloud. " +
            "No API keys are stored on Android."
        ))
        val code = EditText(this).apply {
            hint = "Eight-digit PC pairing code"
            inputType = InputType.TYPE_CLASS_NUMBER
            filters = arrayOf(InputFilter.LengthFilter(8))
            setTextColor(Color.WHITE)
            setHintTextColor(Color.LTGRAY)
        }
        root.addView(code)
        status = label("Not paired. Offline SPARK Mobile remains usable.")
        root.addView(button("PAIR WITH SPARK PC") {
            val clean = code.text.toString()
            if (clean.length != 8 || !clean.all { it in '0'..'9' }) {
                status.text = "Enter the eight-digit code from SPARK on your PC."
                return@button
            }
            status.text = "Pairing over trusted USB…"
            lifecycleScope.launch {
                try {
                    token = UsbBridgeClient.pair(clean)
                    code.text.clear()
                    sequence = 0
                    send.isEnabled = true
                    sync.isEnabled = true
                    status.text = "Paired for up to 10 minutes. Approve AI and personal sync separately on your PC."
                } catch (_: Exception) {
                    token = null
                    send.isEnabled = false
                    sync.isEnabled = false
                    status.text = "Pairing failed. Check USB debugging, adb reverse and the current code."
                }
            }
        })
        root.addView(status)
        conversation = label(
            "Session conversation is temporary. Closing this screen clears it. " +
            "No historical desktop memory is copied to the phone."
        )
        val transcriptScroll = ScrollView(this).apply {
            addView(conversation)
            setBackgroundColor(Color.rgb(18, 30, 49))
        }
        root.addView(transcriptScroll, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 185
        ))
        promptInput = EditText(this).apply {
            hint = "Ask SPARK via your PC"
            setHintTextColor(Color.LTGRAY)
            setTextColor(Color.WHITE)
            filters = arrayOf(InputFilter.LengthFilter(400))
            maxLines = 4
        }
        root.addView(promptInput)
        send = button("ASK SPARK (READ-ONLY)") {
            val session = token ?: return@button
            if (requestBusy) return@button
            val prompt = promptInput.text.toString()
            if (!UsbPairingProtocol.validChatPrompt(prompt)) {
                status.text = "Ask a question between 3 and 400 characters."
                return@button
            }
            requestBusy = true
            send.isEnabled = false
            sync.isEnabled = false
            status.text = "Waiting for your PC AI…"
            lifecycleScope.launch {
                try {
                    val next = UsbPairingProtocol.nextSequence(sequence)
                    val result = UsbBridgeClient.chat(session, next, prompt)
                    sequence = next
                    append("YOU", prompt)
                    append("SPARK / ${result.provider}", result.answer)
                    promptInput.text.clear()
                    status.text = "Read-only reply received. No computer actions executed."
                    if (speaking && localVoiceReady) tts?.speak(
                        result.answer.take(600), TextToSpeech.QUEUE_FLUSH,
                        null, "spark-mobile-pc-advisory"
                    )
                } catch (_: Exception) {
                    status.text = "AI reply not confirmed. Check PC approval, provider and pairing. No action taken."
                } finally {
                    requestBusy = false
                    send.isEnabled = token != null
                    sync.isEnabled = token != null
                }
            }
        }
        send.isEnabled = false
        root.addView(send)
        sync = button("SYNC PERSONAL NOTES / TASKS") {
            val session = token ?: return@button
            if (requestBusy) return@button
            val local = try { mobileStore.personalSnapshot() } catch (_: Exception) {
                status.text = "Local personal records cannot be read. No sync performed."
                return@button
            }
            requestBusy = true
            send.isEnabled = false
            sync.isEnabled = false
            status.text = "Syncing personal notes and tasks over trusted USB…"
            lifecycleScope.launch {
                try {
                    val next = UsbPairingProtocol.nextSequence(sequence)
                    val merged = UsbBridgeClient.syncPersonal(session, next, local)
                    sequence = next
                    val saved = withContext(Dispatchers.IO) {
                        mobileStore.applyPersonalSync(merged)
                    }
                    if (!saved) throw IllegalStateException("Could not save local snapshot")
                    status.text = "Personal sync completed. ${merged.notes.size} notes and ${merged.tasks.size} tasks. " +
                        "Deleted items can reappear because this is a union merge."
                } catch (_: Exception) {
                    status.text = "Personal sync not confirmed. Check PC consent, pairing and storage capacity. " +
                        "No local records were intentionally discarded."
                } finally {
                    requestBusy = false
                    send.isEnabled = token != null
                    sync.isEnabled = token != null
                }
            }
        }
        sync.isEnabled = false
        root.addView(sync)
        root.addView(label(
            "Personal sync is manual. Notes and tasks are merged by exact text/title; " +
            "completed task status wins. Deletions are not propagated. " +
            "The PC stores a local copy without separate application encryption. " +
            "Do not sync passwords or confidential company records.",
            12f
        ))
        root.addView(button("VOICE IN — FILL QUESTION") {
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.ENGLISH.toLanguageTag())
            }
            try { speechRecognizer.launch(intent) }
            catch (_: ActivityNotFoundException) {
                status.text = "No Android speech recognizer installed. Use the keyboard."
            } catch (_: SecurityException) {
                status.text = "Speech recognition unavailable. Use the keyboard."
            }
        })
        voiceToggle = button("VOICE OUT: OFF") { toggleVoice() }
        root.addView(voiceToggle)
        root.addView(label(
            "VOICE IN requests offline speech recognition, but your selected " +
            "Android recognizer may use the network. VOICE OUT requires an " +
            "installed offline Android voice; it is not the desktop cinematic voice. " +
            "Text is sent to your configured provider only after ASK SPARK is tapped.",
            12f
        ))
        outer.addView(root)
        setContentView(outer)
    }

    private fun toggleVoice() {
        if (speaking) {
            speaking = false
            voiceToggle.text = "VOICE OUT: OFF"
            tts?.stop()
            return
        }
        if (localVoiceReady) {
            speaking = true
            voiceToggle.text = "VOICE OUT: ON"
            return
        }
        if (tts != null) {
            status.text = "No installed offline English Android voice."
            return
        }
        tts = TextToSpeech(this) { result ->
            if (result != TextToSpeech.SUCCESS) {
                status.text = "Android offline speech unavailable."
                return@TextToSpeech
            }
            val voice = tts?.voices?.firstOrNull {
                it.locale.language.equals("en", ignoreCase = true) &&
                !it.isNetworkConnectionRequired
            }
            if (voice != null && tts?.setVoice(voice) != TextToSpeech.ERROR) {
                localVoiceReady = true
                speaking = true
                voiceToggle.text = "VOICE OUT: ON"
            } else status.text = "No installed offline English Android voice."
        }
    }

    override fun onDestroy() {
        token = null
        sequence = 0
        speaking = false
        tts?.stop()
        tts?.shutdown()
        super.onDestroy()
    }
}
