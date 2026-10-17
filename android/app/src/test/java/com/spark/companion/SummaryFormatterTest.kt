package com.spark.companion

import org.junit.Assert.*
import org.junit.Test

class SummaryFormatterTest {
    @Test fun formatsMetricsWithoutClaimingGarminOrigin() {
        val report = SummaryFormatter.render(12345, 56.781, 3)
        assertTrue(report.contains("12,345"))
        assertTrue(report.contains("56.78 km"))
        assertTrue(report.contains("Activities: 3"))
        assertFalse(report.contains("Garmin"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsInvalidDistance() { SummaryFormatter.render(1, Double.NaN, 0) }
}
