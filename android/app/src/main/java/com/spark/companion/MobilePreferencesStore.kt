package com.spark.companion

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

/**
 * App-private local storage; Android backup is disabled in the manifest.
 * Personal notes are not encrypted with a dedicated application passphrase:
 * do not use this for account passwords, secrets or company approval evidence.
 */
class MobilePreferencesStore(context: Context) : MobileMemoryStore {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("spark_mobile_local_v1", Context.MODE_PRIVATE)
    private val limit = 100

    private fun storedNotes(): MutableList<String>? = try {
        val source = JSONArray(prefs.getString("notes", "[]") ?: "[]")
        if (source.length() > limit) null else {
            val items = mutableListOf<String>()
            for (i in 0 until source.length()) {
                val text = source.getString(i)
                if (text.length !in 1..240) throw IllegalStateException("Invalid stored note")
                items.add(text)
            }
            items
        }
    } catch (_: Exception) { null }

    private fun storedTasks(): MutableList<MobileTask>? = try {
        val source = JSONArray(prefs.getString("tasks", "[]") ?: "[]")
        if (source.length() > limit) null else {
            val items = mutableListOf<MobileTask>()
            for (i in 0 until source.length()) {
                val value = source.getJSONObject(i)
                val title = value.getString("title")
                if (title.length !in 1..240) throw IllegalStateException("Invalid stored task")
                items.add(MobileTask(title, value.getBoolean("done")))
            }
            items
        }
    } catch (_: Exception) { null }

    private fun saveNotes(items: List<String>): Boolean {
        val json = JSONArray()
        items.forEach { json.put(it) }
        return prefs.edit().putString("notes", json.toString()).commit()
    }
    private fun saveTasks(items: List<MobileTask>): Boolean {
        val json = JSONArray()
        items.forEach { json.put(JSONObject().put("title", it.title).put("done", it.done)) }
        return prefs.edit().putString("tasks", json.toString()).commit()
    }

    override fun notes(): List<String> = storedNotes()?.toList() ?: emptyList()
    override fun tasks(): List<MobileTask> = storedTasks()?.toList() ?: emptyList()
    override fun addNote(text: String): Boolean {
        if (text.length !in 1..240) return false
        val items = storedNotes() ?: return false
        if (items.size >= limit) return false
        items.add(text)
        return saveNotes(items)
    }
    override fun deleteNote(index: Int): Boolean {
        val items = storedNotes() ?: return false
        if (index !in items.indices) return false
        items.removeAt(index)
        return saveNotes(items)
    }
    override fun addTask(text: String): Boolean {
        if (text.length !in 1..240) return false
        val items = storedTasks() ?: return false
        if (items.size >= limit) return false
        items.add(MobileTask(text))
        return saveTasks(items)
    }
    override fun finishTask(index: Int): Boolean {
        val items = storedTasks() ?: return false
        if (index !in items.indices) return false
        items[index] = items[index].copy(done = true)
        return saveTasks(items)
    }
}
