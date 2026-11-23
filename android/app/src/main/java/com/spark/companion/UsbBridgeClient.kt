package com.spark.companion

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.Proxy
import java.net.URL
import java.nio.charset.StandardCharsets

/**
 * Fixed localhost client over Android Debug Bridge reverse-port forwarding.
 * A user must explicitly pair and tap Send; no background data collection.
 */
object UsbBridgeClient {
    private data class Reply(val status: Int, val body: String)

    suspend fun pair(rawCode: String): String = withContext(Dispatchers.IO) {
        val code = UsbPairingProtocol.cleanCode(rawCode)
        val reply = post("/pair", JSONObject().put("code", code), null)
        if (reply.status != 200) throw IllegalStateException("USB pairing was refused")
        val parsed = JSONObject(reply.body)
        if (!parsed.optBoolean("ok")) throw IllegalStateException("USB pairing failed")
        val token = parsed.optString("sessionToken")
        if (!UsbPairingProtocol.validToken(token)) throw IllegalStateException("Invalid USB session")
        token
    }

    suspend fun sendSummary(token: String, sequence: Int, summary: String): Boolean =
        withContext(Dispatchers.IO) {
            require(UsbPairingProtocol.validToken(token))
            require(sequence in 1..1_000_000)
            require(UsbPairingProtocol.validSummary(summary))
            val payload = JSONObject().put("sequence", sequence).put("summary", summary)
            val reply = post("/summary", payload, token)
            if (reply.status != 200) throw IllegalStateException("USB summary was not accepted")
            val parsed = JSONObject(reply.body)
            parsed.optBoolean("ok") && parsed.optBoolean("received") &&
                parsed.optInt("sequence") == sequence
        }

    private fun post(path: String, payload: JSONObject, token: String?): Reply {
        require(path == "/pair" || path == "/summary")
        val body = payload.toString().toByteArray(StandardCharsets.UTF_8)
        require(body.size <= 6000)
        val conn = URL(UsbPairingProtocol.BASE_URL + path)
            .openConnection(Proxy.NO_PROXY) as HttpURLConnection
        conn.connectTimeout = 4000
        conn.readTimeout = 7000
        conn.instanceFollowRedirects = false
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json")
        conn.setRequestProperty("Accept", "application/json")
        if (token != null) conn.setRequestProperty("Authorization", "Bearer $token")
        try {
            conn.outputStream.use { it.write(body) }
            val status = conn.responseCode
            // Never retain an unbounded or untrusted server response.
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val response = stream?.use { input -> input.readNBytes(2049) }
                ?: ByteArray(0)
            if (response.size > 2048) throw IllegalStateException("Unexpected USB response")
            return Reply(status, response.toString(StandardCharsets.UTF_8))
        } finally {
            conn.disconnect()
        }
    }
}
