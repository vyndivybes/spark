package com.spark.companion

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.json.JSONArray
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

    data class Advisory(val answer: String, val provider: String)

    suspend fun chat(token: String, sequence: Int, prompt: String): Advisory =
        withContext(Dispatchers.IO) {
            require(UsbPairingProtocol.validToken(token))
            require(sequence in 1..1_000_000)
            require(UsbPairingProtocol.validChatPrompt(prompt))
            val body = JSONObject().put("sequence", sequence).put("prompt", prompt.trim())
            val reply = post("/mobile-chat", body, token)
            if (reply.status != 200)
                throw IllegalStateException(
                    if (reply.status == 403) "AI replies must be enabled on the PC."
                    else "SPARK PC AI is unavailable or the session has expired.")
            val parsed = JSONObject(reply.body)
            val actual = parsed.keys().asSequence().toSet()
            if (actual != setOf("ok", "answer", "provider", "advisoryOnly", "sequence")
                || !parsed.optBoolean("ok")
                || !parsed.optBoolean("advisoryOnly")
                || parsed.optInt("sequence") != sequence)
                throw IllegalStateException("Invalid SPARK PC AI response")
            val answer = parsed.optString("answer")
            val provider = parsed.optString("provider")
            if (!UsbPairingProtocol.validChatAnswer(answer, provider))
                throw IllegalStateException("Invalid SPARK PC AI response")
            Advisory(answer, provider)
        }

    suspend fun syncPersonal(
        token: String, sequence: Int, records: MobilePersonalSnapshot
    ): MobilePersonalSnapshot = withContext(Dispatchers.IO) {
        require(UsbPairingProtocol.validToken(token))
        require(sequence in 1..1_000_000)
        val clean = MobileRecordMerge.validate(records)
        val notes = JSONArray()
        clean.notes.forEach { notes.put(it) }
        val tasks = JSONArray()
        clean.tasks.forEach { tasks.put(
            JSONObject().put("title", it.title).put("done", it.done)) }
        val outgoing = JSONObject().put("sequence", sequence).put("records",
            JSONObject().put("notes", notes).put("tasks", tasks))
        val response = post("/mobile-sync", outgoing, token)
        if (response.status != 200)
            throw IllegalStateException(
                if (response.status == 403) "Personal sync requires PC approval."
                else "Personal sync was refused. Check the PC session and capacity.")
        val result = JSONObject(response.body)
        if (result.keys().asSequence().toSet() !=
                setOf("ok", "personalOnly", "records", "sequence")
            || !result.optBoolean("ok") || !result.optBoolean("personalOnly")
            || result.optInt("sequence") != sequence)
            throw IllegalStateException("Unexpected SPARK personal sync reply")
        val returned = result.optJSONObject("records")
            ?: throw IllegalStateException("No personal records returned")
        if (returned.keys().asSequence().toSet() != setOf("notes", "tasks"))
            throw IllegalStateException("Unexpected personal sync record fields")
        val returnedNotes = returned.optJSONArray("notes")
            ?: throw IllegalStateException("No personal notes returned")
        val returnedTasks = returned.optJSONArray("tasks")
            ?: throw IllegalStateException("No personal tasks returned")
        require(returnedNotes.length() <= 100 && returnedTasks.length() <= 100)
        val cleanNotes = (0 until returnedNotes.length()).map { index ->
            returnedNotes.opt(index) as? String
                ?: throw IllegalStateException("Invalid personal note")
        }
        val cleanTasks = (0 until returnedTasks.length()).map { index ->
            val item = returnedTasks.optJSONObject(index)
                ?: throw IllegalStateException("Invalid personal task")
            if (item.keys().asSequence().toSet() != setOf("title", "done"))
                throw IllegalStateException("Unexpected personal task fields")
            val title = item.opt("title") as? String
                ?: throw IllegalStateException("Invalid personal task name")
            val done = item.opt("done") as? Boolean
                ?: throw IllegalStateException("Invalid personal task status")
            MobileTask(title, done)
        }
        MobileRecordMerge.validate(MobilePersonalSnapshot(cleanNotes, cleanTasks))
    }

    private fun post(path: String, payload: JSONObject, token: String?): Reply {
        require(path in setOf("/pair", "/summary", "/mobile-chat", "/mobile-sync"))
        val body = payload.toString().toByteArray(StandardCharsets.UTF_8)
        require(body.size <= 6000)
        val conn = URL(UsbPairingProtocol.BASE_URL + path)
            .openConnection(Proxy.NO_PROXY) as HttpURLConnection
        conn.connectTimeout = 4000
        conn.readTimeout = if (path == "/mobile-chat") 45000 else 7000
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
            val response = stream?.use { input -> input.readNBytes(if (path == "/mobile-sync") 256001 else 5001) }
                ?: ByteArray(0)
            if (response.size > (if (path == "/mobile-sync") 256000 else 5000)) throw IllegalStateException("Unexpected USB response")
            return Reply(status, response.toString(StandardCharsets.UTF_8))
        } finally {
            conn.disconnect()
        }
    }
}
