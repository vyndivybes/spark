package com.spark.companion

import org.junit.Assert.*
import org.junit.Test

class MobileBrainTest {
    private class Memory : MobileMemoryStore {
        val entries = mutableListOf<String>()
        val work = mutableListOf<MobileTask>()
        override fun notes() = entries.toList()
        override fun tasks() = work.toList()
        override fun addNote(text: String): Boolean {
            if (entries.size >= 100) return false
            entries.add(text)
            return true
        }
        override fun deleteNote(index: Int): Boolean =
            if (index in entries.indices) { entries.removeAt(index); true } else false
        override fun addTask(text: String): Boolean {
            if (work.size >= 100) return false
            work.add(MobileTask(text))
            return true
        }
        override fun finishTask(index: Int): Boolean =
            if (index in work.indices) { work[index] = work[index].copy(done = true); true } else false
    }
    @Test fun supportsOfflineLocalNotesAndTasksWithExplicitCommands() {
        val mem = Memory()
        val brain = MobileBrain(mem) { "20:15" }
        assertTrue(brain.reply("note inspect bicycle geometry").text.contains("Saved"))
        assertEquals(listOf("inspect bicycle geometry"), mem.notes())
        assertTrue(brain.reply("remember order replacement brake pads").text.contains("Saved"))
        assertTrue(brain.reply("show notes").text.contains("inspect bicycle geometry"))
        assertTrue(brain.reply("add task review design dossier").text.contains("Added"))
        assertTrue(brain.reply("list tasks").text.contains("review design dossier"))
        assertTrue(brain.reply("complete task 1").text.contains("Completed"))
        assertTrue(mem.tasks()[0].done)
        assertTrue(brain.reply("delete note 1").text.contains("Deleted"))
        assertEquals("order replacement brake pads", mem.notes().single())
        assertTrue(brain.reply("time").text.contains("20:15"))
    }
    @Test fun mobileStatusNeverClaimsFullLlmDesktopOrBackgroundSync() {
        val brain = MobileBrain(Memory()) { "20:15" }
        assertTrue(brain.reply("status").text.contains("Offline"))
        assertTrue(brain.reply("Who is the current president of India?").text.contains("not connected"))
        assertEquals(MobileAction.OPEN_ACTIVITY, brain.reply("open health").action)
        assertEquals(MobileAction.OPEN_ACTIVITY, brain.reply("phone link").action)
    }
    @Test fun arbitraryConversationNeverExecutesToolsOrPersists() {
        val mem = Memory()
        val brain = MobileBrain(mem)
        val x = brain.reply("issue a purchase order and send an email")
        assertEquals(MobileAction.NONE, x.action)
        assertTrue(x.text.contains("not connected"))
        assertTrue(mem.notes().isEmpty())
        assertTrue(mem.tasks().isEmpty())
    }
    @Test fun guardInputLengthsControlCharactersAndExplicitDestructiveActions() {
        val mem = Memory()
        val brain = MobileBrain(mem)
        assertTrue(brain.reply("note ").text.contains("command"))
        assertTrue(brain.reply("note " + "x".repeat(300)).text.contains("short"))
        assertTrue(brain.reply("hello\u0000").text.contains("invalid"))
        assertTrue(brain.reply("hello " + "x".repeat(500)).text.contains("short"))
        assertTrue(brain.reply("delete note 5").text.contains("No note"))
        assertTrue(mem.notes().isEmpty())
    }
    @Test fun capacityErrorsAndIndexValidationFailClosed() {
        val mem = Memory()
        repeat(100) { mem.addNote("note-$it") }
        val brain = MobileBrain(mem)
        assertTrue(brain.reply("note over limit").text.contains("full"))
        assertTrue(brain.reply("complete task 0").text.contains("No task"))
        assertTrue(brain.reply("delete note -1").text.contains("not connected"))
        assertEquals(100, mem.notes().size)
    }
}
