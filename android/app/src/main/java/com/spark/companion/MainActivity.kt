package com.spark.companion

import android.content.Intent
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import android.graphics.Color
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.text.InputFilter
import android.text.InputType
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.temporal.ChronoUnit

/** Health Connect only. No Garmin password, desktop-server listener or background upload. */
class MainActivity : ComponentActivity() {
    private lateinit var output: TextView
    private lateinit var share: Button
    private lateinit var copyButton: Button
    private var summary: String? = null
    private var usbSessionToken: String? = null
    private var usbSequence: Int = 0
    private lateinit var usbSendButton: Button
    private lateinit var usbStatus: TextView
    private val permissions = setOf(
        HealthPermission.getReadPermission(ExerciseSessionRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(DistanceRecord::class)
    )
    private val permissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        if (granted.containsAll(permissions)) refresh() else
            output.text = "Health Connect access was not granted. Nothing was read."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 34, 28, 28)
            setBackgroundColor(Color.rgb(246, 248, 247))
        }
        val title = TextView(this).apply {
            text = "SPARK  /  COMPANION"
            textSize = 25f
            setTextColor(Color.rgb(20, 69, 67))
            setPadding(0, 0, 0, 16)
        }
        val detail = TextView(this).apply {
            text = "Read your last 7 days of activity from Android Health Connect. Garmin Connect data appears only after you enable its one-way Health Connect sharing and approve these permissions. Data stays on your device until you choose to Share, Copy or Send to your SPARK PC over USB."
            textSize = 17f
            setTextColor(Color.rgb(46, 62, 61))
            setPadding(0, 0, 0, 20)
        }
        val connect = Button(this).apply {
            text = "Connect Health Connect"
            setOnClickListener { connectAndRead() }
        }
        output = TextView(this).apply {
            text = "Not connected. No personal activity data has been read."
            textSize = 20f
            setTextColor(Color.rgb(24, 51, 49))
            setPadding(0, 25, 0, 24)
        }
        share = Button(this).apply {
            text = "Share activity summary"
            isEnabled = false
            setOnClickListener {
                val data = summary ?: return@setOnClickListener
                val intent = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_SUBJECT, "SPARK Health Connect summary")
                    putExtra(Intent.EXTRA_TEXT, data)
                }
                startActivity(Intent.createChooser(intent, "Share summary"))
            }
        }
        // Explicit user action only: no automatic upload or background relay.
        // Shared activity is private; other apps can inspect clipboard data.
        val copy = Button(this).apply {
            text = "Copy summary"
            isEnabled = false
            setOnClickListener {
                val data = summary ?: return@setOnClickListener
                val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("SPARK Health Connect summary", data))
                Toast.makeText(this@MainActivity,
                    "Copied. Paste into SPARK's PHONE / WATCH panel on your PC.", Toast.LENGTH_LONG).show()
            }
        }
        copyButton = copy
        val usbHeading = TextView(this).apply {
            text = "USB PC PAIRING  /  EXPLICIT TRANSFER"
            textSize = 17f
            setTextColor(Color.rgb(20, 69, 67))
            setPadding(0, 28, 0, 8)
        }
        val usbHelp = TextView(this).apply {
            text = "On the Windows PC, open SPARK PHONE / WATCH and select Start USB pairing. With trusted USB debugging enabled, run adb reverse tcp:38177 tcp:38177 on the PC. Enter the eight-digit code shown in SPARK here. Pairing does not transfer your health data."
            textSize = 15f
            setTextColor(Color.rgb(46, 62, 61))
        }
        val codeInput = EditText(this).apply {
            hint = "Eight-digit code from SPARK"
            inputType = InputType.TYPE_CLASS_NUMBER
            filters = arrayOf(InputFilter.LengthFilter(8))
            contentDescription = "SPARK one-time USB pairing code"
        }
        usbStatus = TextView(this).apply {
            text = "Not paired. All activity stays on this Android phone."
            textSize = 15f
            setTextColor(Color.rgb(46, 62, 61))
            setPadding(0, 8, 0, 6)
        }
        val pairButton = Button(this).apply {
            text = "Pair with SPARK over USB"
            setOnClickListener {
                val code = codeInput.text.toString()
                if (code.length != 8 || !code.all { ch -> ch.isDigit() }) {
                    usbStatus.text = "Enter the eight-digit code shown in SPARK."
                    return@setOnClickListener
                }
                isEnabled = false
                lifecycleScope.launch {
                    try {
                        val token = UsbBridgeClient.pair(code)
                        usbSessionToken = token
                        usbSequence = 0
                        codeInput.text.clear()
                        usbStatus.text = "Paired with SPARK for this session. No activity transferred yet."
                        usbSendButton.isEnabled = summary != null
                    } catch (_: Exception) {
                        usbSessionToken = null
                        usbSendButton.isEnabled = false
                        usbStatus.text = "USB pairing failed. Check the PC code, USB debugging and adb reverse tunnel."
                    } finally {
                        isEnabled = true
                    }
                }
            }
        }
        usbSendButton = Button(this).apply {
            text = "Send current summary to SPARK PC"
            isEnabled = false
            setOnClickListener {
                val token = usbSessionToken ?: return@setOnClickListener
                val report = summary ?: return@setOnClickListener
                isEnabled = false
                lifecycleScope.launch {
                    try {
                        val next = UsbPairingProtocol.nextSequence(usbSequence)
                        val sent = UsbBridgeClient.sendSummary(token, next, report)
                        if (!sent) throw IllegalStateException("Unconfirmed receipt")
                        usbSequence = next
                        usbStatus.text = "Summary delivered to SPARK's in-memory PHONE / WATCH inbox."
                    } catch (_: Exception) {
                        usbStatus.text = "Transfer not confirmed. Reopen pairing on the PC if the session expired."
                    } finally {
                        isEnabled = usbSessionToken != null && summary != null
                    }
                }
            }
        }
        root.addView(title)
        root.addView(detail)
        root.addView(connect)
        root.addView(output)
        root.addView(copy)
        root.addView(share)
        root.addView(usbHeading)
        root.addView(usbHelp)
        root.addView(codeInput)
        root.addView(pairButton)
        root.addView(usbSendButton)
        root.addView(usbStatus)
        setContentView(ScrollView(this).apply { addView(root) })
    }

    override fun onDestroy() {
        usbSessionToken = null
        usbSequence = 0
        super.onDestroy()
    }

    private fun connectAndRead() {
        val status = HealthConnectClient.getSdkStatus(this)
        if (status != HealthConnectClient.SDK_AVAILABLE) {
            output.text = "Health Connect is not available. This preview requires Android 14+ with Health Connect enabled."
            return
        }
        lifecycleScope.launch {
            try {
                val client = HealthConnectClient.getOrCreate(this@MainActivity)
                val granted = client.permissionController.getGrantedPermissions()
                if (!granted.containsAll(permissions)) permissionLauncher.launch(permissions)
                else refresh()
            } catch (error: Exception) {
                output.text = "Could not access Health Connect: ${error.javaClass.simpleName}. Check its permissions."
            }
        }
    }

    private fun refresh() {
        lifecycleScope.launch {
            try {
                output.text = "Reading permissioned activity records…"
                val client = HealthConnectClient.getOrCreate(this@MainActivity)
                val end = Instant.now()
                val start = end.minus(7, ChronoUnit.DAYS)
                val range = TimeRangeFilter.between(start, end)
                val totals = client.aggregate(
                    AggregateRequest(
                        metrics = setOf(StepsRecord.COUNT_TOTAL, DistanceRecord.DISTANCE_TOTAL),
                        timeRangeFilter = range
                    )
                )
                val sessions = client.readRecords(
                    ReadRecordsRequest(
                        recordType = ExerciseSessionRecord::class,
                        timeRangeFilter = range,
                        pageSize = 100
                    )
                )
                val count = sessions.records.size
                val summaryText = SummaryFormatter.render(
                    totals[StepsRecord.COUNT_TOTAL] ?: 0L,
                    totals[DistanceRecord.DISTANCE_TOTAL]?.inKilometers ?: 0.0,
                    count
                )
                val sourcePackages = sessions.records.map { it.metadata.dataOrigin.packageName }.distinct()
                val sources = if (sourcePackages.isEmpty()) "No activity-session sources found" else
                    "Source apps: " + sourcePackages.joinToString(", ")
                val paging = if (sessions.pageToken != null) "\nShowing first 100 activities." else ""
                summary = "$summaryText\n\n$sources$paging\n\nHealth Connect totals may include non-Garmin sources."
                output.text = summary
                share.isEnabled = true
                copyButton.isEnabled = true
                usbSendButton.isEnabled = usbSessionToken != null
            } catch (error: Exception) {
                summary = null
                share.isEnabled = false
                copyButton.isEnabled = false
                usbSendButton.isEnabled = false
                output.text = "Activity read failed: ${error.javaClass.simpleName}. Check permissions and try again."
            }
        }
    }
}
