package com.spark.companion

/** Intentionally no auto-discovery, LAN address or cloud endpoint. */
object UsbPairingProtocol {
    const val PORT = 38177
    const val BASE_URL = "http://127.0.0.1:38177"
    private val codePattern = Regex("[0-9]{8}")
    private val tokenPattern = Regex("[a-f0-9]{64}")
    private val summaryPattern = Regex(
        """^Last 7 days\n\nActivities: (\d{1,7})\nSteps: (?:\d{1,3}(?:,\d{3})*|\d{1,10})\nDistance: \d{1,8}(?:\.\d{1,2})? km\n\n(?:(?:Source apps: [a-zA-Z0-9._,\s-]+)|(?:No activity-session sources found))(?:\nShowing first 100 activities\.)?\n\nHealth Connect totals may include non-Garmin sources\.$"""
    )
    fun cleanCode(value: String): String {
        val cleaned = value.trim()
        require(codePattern.matches(cleaned)) { "Enter the eight-digit code shown on SPARK." }
        return cleaned
    }
    fun validToken(token: String): Boolean = tokenPattern.matches(token)
    fun validSummary(text: String): Boolean =
        text.length in 45..4000 && summaryPattern.matches(text) &&
        (summaryPattern.find(text)?.groupValues?.get(1)?.toIntOrNull() ?: Int.MAX_VALUE) <= 100_000
    fun nextSequence(previous: Int): Int {
        require(previous in 0 until 1_000_000)
        return previous + 1
    }
}
