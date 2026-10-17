package com.spark.companion

import android.content.Intent
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import android.graphics.Color
import android.os.Bundle
import android.widget.Button
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
            text = "Read your last 7 days of activity from Android Health Connect. Garmin Connect data appears only after you enable its one-way Health Connect sharing and approve these permissions. Data stays on your device until you choose Share."
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
        root.addView(title)
        root.addView(detail)
        root.addView(connect)
        root.addView(output)
        root.addView(copy)
        root.addView(share)
        setContentView(ScrollView(this).apply { addView(root) })
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
            } catch (error: Exception) {
                summary = null
                share.isEnabled = false
                copyButton.isEnabled = false
                output.text = "Activity read failed: ${error.javaClass.simpleName}. Check permissions and try again."
            }
        }
    }
}
