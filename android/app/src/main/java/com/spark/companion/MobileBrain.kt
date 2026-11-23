package com.spark.companion

import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/** A deterministic local command core, not an LLM or desktop automation proxy. */
data class MobileTask(val title: String, val done: Boolean = false)
enum class MobileAction { NONE, OPEN_ACTIVITY }
data class MobileReply(val text: String, val action: MobileAction = MobileAction.NONE)

interface MobileMemoryStore {
    fun notes(): List<String>
    fun tasks(): List<MobileTask>
    fun addNote(text: String): Boolean
    fun deleteNote(index: Int): Boolean
    fun addTask(text: String): Boolean
    fun finishTask(index: Int): Boolean
}

/** Personal offline commands; no network calls, cloud models or tool execution. */
class MobileBrain(
    private val memory: MobileMemoryStore,
    private val clock: () -> String = {
        LocalTime.now().format(DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH))
    }
) {
    private val taskCompletion = Regex("^complete task ([0-9]{1,3})$", RegexOption.IGNORE_CASE)
    private val noteDeletion = Regex("^delete note ([1-9][0-9]{0,2})$", RegexOption.IGNORE_CASE)

    fun reply(raw: String): MobileReply {
        if (raw.length > 400) return MobileReply("Use a shorter command (400 characters maximum).")
        if (raw.any { it.code < 32 && it != '\n' && it != '\t' }) {
            return MobileReply("That command contains invalid characters.")
        }
        val input = raw.trim().replace(Regex("[\n\t]+"), " ").trim()
        if (input.isEmpty()) return MobileReply("Enter a command or tap Help.")
        val lower = input.lowercase(Locale.ROOT)

        if (lower in listOf("health", "open health", "open activity", "phone link", "open phone link")) {
            return MobileReply("Opening the Health Connect and USB-link panel.", MobileAction.OPEN_ACTIVITY)
        }
        if (lower in listOf("hello", "hi", "hey spark")) {
            return MobileReply("SPARK Mobile online. Local commands are ready; cloud AI is not connected.")
        }
        if (lower in listOf("help", "commands", "what can you do")) {
            return MobileReply(
                "Offline commands: 'note <text>', 'show notes', 'delete note 1', " +
                "'add task <text>', 'list tasks', 'complete task 1', 'time', 'status', and 'open health'. " +
                "Tasks are local checklist items, not scheduled reminders."
            )
        }
        if (lower in listOf("status", "system status")) {
            return MobileReply(
                "SPARK Mobile: Offline local core active. Notes and tasks stay on this phone. " +
                "Desktop AI, historical conversation sync, voice cloning and autonomous PC control are not connected."
            )
        }
        if (lower in listOf("time", "what time is it", "current time")) {
            return MobileReply("Phone time: " + clock() + ".")
        }
        if (lower in listOf("show notes", "list notes", "notes", "what do you remember")) {
            val entries = memory.notes()
            return MobileReply(if (entries.isEmpty()) "No local notes saved." else
                "Local notes:\n" + entries.mapIndexed { i, item -> (i + 1).toString() + ". " + item }.joinToString("\n"))
        }
        if (lower in listOf("list tasks", "show tasks", "tasks", "my tasks")) {
            val entries = memory.tasks()
            return MobileReply(if (entries.isEmpty()) "No local tasks saved." else
                "Local checklist:\n" + entries.mapIndexed { i, item ->
                    (i + 1).toString() + ". " + (if (item.done) "[done]" else "[open]") + " " + item.title
                }.joinToString("\n"))
        }
        if (lower in listOf("note", "remember", "add task", "task")) {
            return MobileReply("Use a command followed by text, for example: note check tyre pressure.")
        }
        taskCompletion.matchEntire(input)?.let { match ->
            val i = match.groupValues[1].toInt() - 1
            return MobileReply(if (memory.finishTask(i)) "Completed local task " + (i + 1) + "." else "No task " + (i + 1) + " exists.")
        }
        noteDeletion.matchEntire(input)?.let { match ->
            val i = match.groupValues[1].toInt() - 1
            return MobileReply(if (memory.deleteNote(i)) "Deleted local note " + (i + 1) + "." else "No note " + (i + 1) + " exists.")
        }
        val note = when {
            lower.startsWith("note ") -> input.substring(5).trim()
            lower.startsWith("remember ") -> input.substring(9).trim()
            lower.startsWith("save note ") -> input.substring(10).trim()
            else -> null
        }
        if (note != null) {
            if (note.isEmpty() || note.length > 240) return MobileReply("Use a short note (1 to 240 characters).")
            return MobileReply(if (memory.addNote(note)) "Saved to private local notes." else
                "Local notes are full (100 maximum).")
        }
        val task = when {
            lower.startsWith("add task ") -> input.substring(9).trim()
            lower.startsWith("task ") -> input.substring(5).trim()
            else -> null
        }
        if (task != null) {
            if (task.isEmpty() || task.length > 240) return MobileReply("Use a short task (1 to 240 characters).")
            return MobileReply(if (memory.addTask(task)) "Added to the local task checklist (not a scheduled reminder)." else
                "Local tasks are full (100 maximum).")
        }
        return MobileReply(
            "SPARK Mobile's AI is not connected in this build. " +
            "I can take notes, manage local tasks and open the health panel. Type 'help' for commands."
        )
    }
}
