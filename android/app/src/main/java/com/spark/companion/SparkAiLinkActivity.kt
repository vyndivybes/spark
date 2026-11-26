package com.spark.companion

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.UtteranceProgressListener
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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.Locale

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

    private lateinit var handsFreeToggle: Button
    private var handsFreeRecognizer: SpeechRecognizer? = null
    private var nextListen: Job? = null
    private var replyUtterance = 0
    private var pairing = false
    private var sessionExpiry: Job? = null
    private val commands = mapOf(
        "show spark" to "show-spark",
        "open calculator" to "open-calculator",
        "open notepad" to "open-notepad",
        "open whatsapp" to "open-whatsapp",
        "open whats app" to "open-whatsapp"
    )
    private val microphonePermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted && hasWindowFocus()) startHandsFree()
        else status.text = "To start hands-free mode, allow microphone access and tap Hands-free."
    }

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
            "AI answers and optional PC controls over trusted USB. " +
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
            if (pairing || requestBusy || token != null) return@button
            val clean = code.text.toString()
            if (clean.length != 8 || !clean.all { it in '0'..'9' }) {
                status.text = "Enter the eight-digit code from SPARK on your PC."
                return@button
            }
            pairing = true
            status.text = "Pairing over trusted USB…"
            lifecycleScope.launch {
                try {
                    token = UsbBridgeClient.pair(clean)
                    code.text.clear()
                    sequence = 0
                    sessionExpiry?.cancel()
                    sessionExpiry = lifecycleScope.launch {
                        delay(10 * 60 * 1000L)
                        token = null
                        send.isEnabled = false
                        sync.isEnabled = false
                        stopHandsFree()
                        status.text = "Pairing expired. Restart USB pairing on your PC."
                    }
                    send.isEnabled = true
                    sync.isEnabled = true
                    status.text = "Paired for up to 10 minutes. Enable AI answers, PC control or personal sync on your PC."
                } catch (_: Exception) {
                    token = null
                    send.isEnabled = false
                    sync.isEnabled = false
                    status.text = "Pairing failed. Check USB debugging, adb reverse and the current code."
                } finally { pairing = false }
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
        send = button("ASK OR RUN COMMAND") {
            stopHandsFree()
            submit(promptInput.text.toString())
        }
        send.isEnabled = false
        root.addView(send)
        sync = button("SYNC PERSONAL NOTES / TASKS") {
            val session = token ?: return@button
            if (requestBusy) return@button
            stopHandsFree()
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
        handsFreeToggle = button("Start hands-free") {
            if (handsFreeRecognizer != null) {
                stopHandsFree()
                status.text = "Hands-free mode stopped."
            } else if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED) startHandsFree()
            else microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
        }
        root.addView(handsFreeToggle)
        root.addView(label(
            "Keep this screen open and say “Hey Spark” followed by a question, or say " +
            "“Hey Spark, open WhatsApp.” Other commands are Show Spark, Open Calculator and Open Notepad. " +
            "Questions transcribed on the phone go to your PC’s configured AI provider.",
            12f
        ))
        root.addView(button("VOICE IN — FILL QUESTION") {
            stopHandsFree()
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
            "Hands-free uses on-device recognition and sends questions after “Hey Spark.”",
            12f
        ))
        outer.addView(root)
        setContentView(outer)
    }

    private fun submit(text: String) {
        val session = token ?: return
        if (requestBusy) return
        val prompt = text.trim()
        if (!UsbPairingProtocol.validChatPrompt(prompt)) {
            status.text = "Enter a question or supported PC command between 3 and 400 characters."
            listenAgain()
            return
        }
        val command = commands[prompt.lowercase(Locale.ROOT).trimEnd('.', '!', '?')]
        requestBusy = true
        send.isEnabled = false
        sync.isEnabled = false
        status.text = if (command == null) "Waiting for your PC AI…" else "Sending command to your PC…"
        lifecycleScope.launch {
            try {
                val next = UsbPairingProtocol.nextSequence(sequence)
                val answer = if (command == null) {
                    val result = UsbBridgeClient.chat(session, next, prompt)
                    append("YOU", prompt)
                    append("SPARK / ${result.provider}", result.answer)
                    result.answer
                } else {
                    val accepted = UsbBridgeClient.control(session, next, command)
                    val message = if (accepted) "PC accepted: $prompt."
                        else "PC could not start: $prompt."
                    append("PC", message)
                    message
                }
                sequence = next
                promptInput.text.clear()
                status.text = if (command == null) "Read-only AI reply received." else answer
                speakOrListen(answer)
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                stopHandsFree()
                status.text = if (command == null) "AI reply unconfirmed. Check PC consent, provider and pairing."
                    else "Command unconfirmed. Check your PC before retrying."
            } finally {
                requestBusy = false
                send.isEnabled = token != null
                sync.isEnabled = token != null
            }
        }
    }

    private fun speakOrListen(answer: String) {
        val engine = tts
        if (speaking && localVoiceReady && engine != null && hasWindowFocus()) {
            val utterance = "spark-pc-${++replyUtterance}"
            if (engine.speak(answer.take(2800), TextToSpeech.QUEUE_FLUSH, null, utterance)
                == TextToSpeech.SUCCESS) return
        }
        listenAgain()
    }

    private fun startHandsFree() {
        if (token == null || requestBusy) {
            status.text = "Pair with your PC before starting hands-free."
            return
        }
        if (!localVoiceReady) {
            status.text = "Enable Voice Out and install an offline English voice first."
            return
        }
        if (!SpeechRecognizer.isOnDeviceRecognitionAvailable(this)) {
            status.text = "On-device speech recognition is unavailable. You can still type questions."
            return
        }
        val recognizer = try {
            SpeechRecognizer.createOnDeviceSpeechRecognizer(this)
        } catch (_: RuntimeException) {
            status.text = "Could not start on-device speech recognition."
            return
        }
        handsFreeRecognizer = recognizer
        speaking = true
        voiceToggle.text = "VOICE OUT: ON"
        handsFreeToggle.text = "Stop hands-free"
        recognizer.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {
                if (handsFreeRecognizer === recognizer) status.text = "Listening for “Hey Spark”…"
            }
            override fun onResults(results: Bundle?) {
                if (handsFreeRecognizer !== recognizer) return
                val heard = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull()?.trim().orEmpty()
                val prompt = Regex("^hey spark[ ,.!?]+(.+)$", RegexOption.IGNORE_CASE)
                    .matchEntire(heard)?.groupValues?.get(1)
                if (prompt == null) listenAgain() else submit(prompt)
            }
            override fun onError(error: Int) {
                if (handsFreeRecognizer !== recognizer) return
                if (error == SpeechRecognizer.ERROR_NO_MATCH ||
                    error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT) listenAgain()
                else {
                    stopHandsFree()
                    status.text = "On-device speech stopped. Check your Android speech settings."
                }
            }
            override fun onBeginningOfSpeech() = Unit
            override fun onRmsChanged(rmsdB: Float) = Unit
            override fun onBufferReceived(buffer: ByteArray?) = Unit
            override fun onEndOfSpeech() = Unit
            override fun onPartialResults(partialResults: Bundle?) = Unit
            override fun onEvent(eventType: Int, params: Bundle?) = Unit
        })
        replyUtterance++
        tts?.stop()
        listenAgain()
    }

    private fun listenAgain() {
        val recognizer = handsFreeRecognizer ?: return
        nextListen?.cancel()
        nextListen = lifecycleScope.launch {
            delay(450)
            if (handsFreeRecognizer !== recognizer || !hasWindowFocus() || requestBusy) return@launch
            try {
                recognizer.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.ENGLISH.toLanguageTag())
                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                })
            } catch (_: RuntimeException) {
                stopHandsFree()
                status.text = "Could not start on-device speech recognition."
            }
        }
    }

    private fun stopHandsFree() {
        nextListen?.cancel()
        val recognizer = handsFreeRecognizer
        handsFreeRecognizer = null
        recognizer?.destroy()
        if (recognizer != null) tts?.stop()
        if (::handsFreeToggle.isInitialized) handsFreeToggle.text = "Start hands-free"
    }

    override fun onPause() {
        stopHandsFree()
        tts?.stop()
        super.onPause()
    }

    private fun toggleVoice() {
        if (speaking) {
            stopHandsFree()
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
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) = Unit
                    override fun onDone(utteranceId: String?) = resumeListening(utteranceId)
                    override fun onError(utteranceId: String?) = resumeListening(utteranceId)
                    private fun resumeListening(utteranceId: String?) = runOnUiThread {
                        if (utteranceId == "spark-pc-$replyUtterance") listenAgain()
                    }
                })
                localVoiceReady = true
                speaking = true
                voiceToggle.text = "VOICE OUT: ON"
            } else status.text = "No installed offline English Android voice."
        }
    }

    override fun onDestroy() {
        stopHandsFree()
        token = null
        sequence = 0
        speaking = false
        tts?.stop()
        tts?.shutdown()
        super.onDestroy()
    }
}
