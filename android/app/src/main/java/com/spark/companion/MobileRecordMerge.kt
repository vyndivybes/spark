package com.spark.companion

/** Personal text-only records. Not the desktop AI's conversation/skill memory. */
data class MobilePersonalSnapshot(
    val notes: List<String>,
    val tasks: List<MobileTask>
)

object MobileRecordMerge {
    private fun validText(s: String): Boolean =
        s.trim().isNotEmpty() && s.length <= 240 &&
            s.none { ch -> ch.code < 32 || ch.code == 127 }

    fun validate(snapshot: MobilePersonalSnapshot): MobilePersonalSnapshot {
        require(snapshot.notes.size <= 100 && snapshot.tasks.size <= 100) {
            "Mobile notes/tasks exceed the personal sync capacity."
        }
        require(snapshot.notes.all(::validText))
        require(snapshot.tasks.all { validText(it.title) })
        return MobilePersonalSnapshot(
            snapshot.notes.map { it.trim() },
            snapshot.tasks.map { it.copy(title = it.title.trim()) }
        )
    }

    fun merge(current: MobilePersonalSnapshot, incoming: MobilePersonalSnapshot): MobilePersonalSnapshot {
        val old = validate(current)
        val new = validate(incoming)
        val notes = (old.notes + new.notes).distinct()
        val tasks = linkedMapOf<String, Boolean>()
        for (task in old.tasks + new.tasks) {
            tasks[task.title] = (tasks[task.title] ?: false) || task.done
        }
        require(notes.size <= 100 && tasks.size <= 100) {
            "Mobile notes/tasks reached the limit. Nothing was discarded."
        }
        return MobilePersonalSnapshot(
            notes,
            tasks.map { (title, done) -> MobileTask(title, done) }
        )
    }
}
