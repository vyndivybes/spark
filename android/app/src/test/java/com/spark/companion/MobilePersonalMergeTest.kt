package com.spark.companion

import org.junit.Assert.*
import org.junit.Test

class MobilePersonalMergeTest {
    @Test fun syncPreservesLocalAndPcEntriesAndCompletionFlags() {
        val phone = MobilePersonalSnapshot(
            listOf("Inspect tyres","Wash bike"),
            listOf(MobileTask("Charge lights",false)))
        val pc = MobilePersonalSnapshot(
            listOf("Wash bike","Ride 100km"),
            listOf(MobileTask("Charge lights",true),MobileTask("Call mechanic",false)))
        val merged = MobileRecordMerge.merge(phone,pc)
        assertEquals(listOf("Inspect tyres","Wash bike","Ride 100km"),merged.notes)
        assertEquals(listOf(MobileTask("Charge lights",true),MobileTask("Call mechanic",false)),merged.tasks)
        assertFalse(phone.tasks.first().done)
    }

    @Test fun capacityDoesNotSilentlyDropData() {
        val pc = MobilePersonalSnapshot((1..100).map { "Record-$it" },emptyList())
        try {
            MobileRecordMerge.merge(pc,MobilePersonalSnapshot(listOf("new"),emptyList()))
            fail("Should reject more than 100 notes")
        } catch (_:IllegalArgumentException){}
    }

    @Test fun notesAndTasksMustBeWithinPersonalDataBounds() {
        try{
            MobileRecordMerge.validate(MobilePersonalSnapshot(listOf("broken\u0000"),emptyList()))
            fail("Must reject control characters")
        }catch(_:IllegalArgumentException){}
        try{
            MobileRecordMerge.validate(MobilePersonalSnapshot(emptyList(),listOf(MobileTask("x".repeat(241)))))
            fail("Must reject oversized task title")
        }catch(_:IllegalArgumentException){}
    }
}
