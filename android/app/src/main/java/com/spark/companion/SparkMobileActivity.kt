package com.spark.companion

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.speech.RecognizerIntent
import android.speech.tts.TextToSpeech
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import java.util.Locale

/**
 * SPARK Mobile: a usable independent Android cockpit.
 * The local command core does not pretend to be the Windows Python/Electron AI.
 * All sensitive external actions remain unavailable in this build.
 */
class SparkMobileActivity : ComponentActivity() {
    private lateinit var brain: MobileBrain
    private lateinit var commandInput: EditText
    private lateinit var transcript: TextView
    private lateinit var audioToggle: Button
    private var tts: TextToSpeech? = null
    private var localVoiceReady = false
    private var speakReplies = false
    private val history = StringBuilder()

    private val speechResult = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val heard = if (result.resultCode == Activity.RESULT_OK)
            result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull()
        else null
        if (!heard.isNullOrBlank()) {
            handleCommand(heard)
        } else {
            appendSession("SPARK", "No spoken command was returned by the Android speech service.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        brain = MobileBrain(MobilePreferencesStore(this))
        window.statusBarColor = Color.rgb(10, 16, 32)
        window.navigationBarColor = Color.rgb(10, 16, 32)
        renderCockpit()
        appendSession("SPARK", "SPARK Mobile online. Independent local notes and tasks ready. No LLM is connected.")
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density + 0.5f).toInt()

    private fun panel(color: Int, corner: Float = 22f): GradientDrawable =
        GradientDrawable().apply {
            setColor(color)
            cornerRadius = corner * resources.displayMetrics.density
            setStroke(1, Color.rgb(35, 74, 91))
        }

    private fun text(value: String, size: Float, color: Int, bold: Boolean = false): TextView =
        TextView(this).apply {
            this.text = value
            textSize = size
            setTextColor(color)
            if (bold) typeface = Typeface.create("sans-serif-medium", Typeface.BOLD)
        }

    private fun button(label: String, action: () -> Unit): Button =
        Button(this).apply {
            text = label
            isAllCaps = false
            setTextColor(Color.rgb(223, 249, 255))
            background = panel(Color.rgb(24, 62, 84), 18f)
            setOnClickListener { action() }
        }

    private fun renderCockpit() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(10, 16, 32))
            setPadding(dp(22), dp(20), dp(22), dp(18))
        }
        val title = text("SPARK  /  MOBILE", 27f, Color.rgb(102, 232, 240), true).apply {
            setPadding(0, dp(8), 0, dp(5))
        }
        val subtitle = text("LOCAL CORE  •  PERSONAL  •  FREE", 12f, Color.rgb(181, 193, 213)).apply {
            setPadding(0, 0, 0, dp(16))
        }
        root.addView(title)
        root.addView(subtitle)

        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val commands = listOf(
            "NOTES" to "show notes",
            "TASKS" to "list tasks",
            "STATUS" to "status"
        )
        for ((label, command) in commands) {
            val item = button(label) { handleCommand(command) }
            actions.addView(item, LinearLayout.LayoutParams(0, dp(52), 1f).apply {
                marginEnd = dp(6)
            })
        }
        root.addView(actions)

        val healthButton = button("HEALTH CONNECT  /  USB PHONE LINK") {
            startActivity(Intent(this, MainActivity::class.java))
        }
        root.addView(healthButton, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(53)
        ).apply { topMargin = dp(8); bottomMargin = dp(8) })

        val desktopAiButton = button("SPARK DESKTOP AI  /  SECURE USB LINK") {
            startActivity(Intent(this, SparkAiLinkActivity::class.java))
        }
        root.addView(desktopAiButton, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(53)
        ).apply { bottomMargin = dp(10) })

        val notice = text(
            "This is the independent Android edition: offline notes, task checklist and phone services. " +
            "Optional read-only PC-backed AI is available through trusted USB. " +
            "Desktop control, historic memory sync and cinematic voice remain unavailable.",
            13f, Color.rgb(191, 206, 219)
        ).apply {
            setPadding(dp(15), dp(15), dp(15), dp(15))
            background = panel(Color.rgb(18, 31, 51))
        }
        root.addView(notice)

        val heading = text("SPARK CONSOLE", 17f, Color.rgb(103, 224, 238), true).apply {
            setPadding(0, dp(16), 0, dp(8))
        }
        root.addView(heading)
        val logScroll = ScrollView(this).apply { isFillViewport = true }
        transcript = text("", 15f, Color.rgb(218, 236, 244)).apply {
            setPadding(15, 15, 15, 15)
            background = panel(Color.rgb(14, 25, 44))
            setTextIsSelectable(true)
        }
        logScroll.addView(transcript)
        root.addView(logScroll, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f
        ).apply { bottomMargin = dp(12) })

        commandInput = EditText(this).apply {
            hint = "Ask SPARK or type: note ..., add task ..."
            setHintTextColor(Color.rgb(159, 173, 189))
            setTextColor(Color.WHITE)
            textSize = 15f
            maxLines = 3
            setSingleLine(false)
            setPadding(dp(16), dp(12), dp(16), dp(12))
            background = panel(Color.rgb(20, 37, 59))
            contentDescription = "SPARK Mobile text command"
        }
        commandInput.filters = arrayOf(android.text.InputFilter.LengthFilter(400))
        root.addView(commandInput, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ))

        val controls = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val send = button("SEND") {
            val command = commandInput.text.toString()
            commandInput.text.clear()
            handleCommand(command)
        }
        controls.addView(send, LinearLayout.LayoutParams(0, dp(50), 1f).apply { marginEnd = dp(5) })
        val microphone = button("VOICE IN") { beginSpeechRecognition() }
        controls.addView(microphone, LinearLayout.LayoutParams(0, 50, 1f).apply { marginEnd = 5 })
        audioToggle = button("VOICE OUT: OFF") { toggleVoiceOut() }
        controls.addView(audioToggle, LinearLayout.LayoutParams(0, dp(50), 1.5f))
        root.addView(controls, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = dp(10) })

        val disclaimer = text(
            "Voice input uses your selected Android speech service; an offline result is requested " +
            "but the provider may use the network. Voice output uses an installed offline Android voice only. " +
            "Do not save passwords or secrets in unencrypted app notes.",
            11f, Color.rgb(155, 175, 190)
        ).apply { setPadding(0, dp(10), 0, 0) }
        root.addView(disclaimer)
        setContentView(root)
    }

    private fun appendSession(who: String, value: String) {
        if (history.length > 12000) history.delete(0, history.length - 8000)
        history.append(who).append("\n").append(value).append("\n\n")
        transcript.text = history.toString()
    }

    private fun handleCommand(command: String) {
        val value = command.trim()
        if (value.isEmpty()) return
        appendSession("YOU", value.take(400))
        val reply = brain.reply(value)
        appendSession("SPARK", reply.text)
        if (reply.action == MobileAction.OPEN_ACTIVITY) {
            startActivity(Intent(this, MainActivity::class.java))
        } else if (speakReplies && localVoiceReady) {
            tts?.speak(reply.text.take(600), TextToSpeech.QUEUE_FLUSH, null, "spark-mobile-response")
        }
    }

    private fun beginSpeechRecognition() {
        // User gesture only. EXTRA_PREFER_OFFLINE is a hint, not proof the
        // selected Android speech provider never contacts the network.
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.ENGLISH.toLanguageTag())
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Speak a SPARK Mobile command")
        }
        try {
            speechResult.launch(intent)
        } catch (_: ActivityNotFoundException) {
            appendSession("SPARK", "No Android speech recognizer is available. Use text commands.")
        } catch (_: SecurityException) {
            appendSession("SPARK", "The installed speech recognizer could not be opened.")
        }
    }

    private fun toggleVoiceOut() {
        if (speakReplies) {
            speakReplies = false
            audioToggle.text = "VOICE OUT: OFF"
            tts?.stop()
            return
        }
        if (localVoiceReady) {
            speakReplies = true
            audioToggle.text = "VOICE OUT: ON"
            appendSession("SPARK", "Offline Android voice enabled.")
            return
        }
        if (tts != null) {
            appendSession("SPARK", "No installed offline Android English voice is available.")
            return
        }
        tts = TextToSpeech(this) { status ->
            if (status != TextToSpeech.SUCCESS) {
                appendSession("SPARK", "Android text-to-speech could not start.")
                return@TextToSpeech
            }
            val localEnglish = tts?.voices?.firstOrNull { v ->
                v.locale.language.equals("en", ignoreCase = true) && !v.isNetworkConnectionRequired
            }
            if (localEnglish != null && tts?.setVoice(localEnglish) != TextToSpeech.ERROR) {
                localVoiceReady = true
                speakReplies = true
                audioToggle.text = "VOICE OUT: ON"
                appendSession("SPARK", "Installed offline Android voice ready. This is not cinematic VoiceStudio.")
            } else {
                appendSession("SPARK", "No installed offline English Android voice. Text mode remains available.")
            }
        }
    }

    override fun onDestroy() {
        speakReplies = false
        tts?.stop()
        tts?.shutdown()
        tts = null
        super.onDestroy()
    }
}
