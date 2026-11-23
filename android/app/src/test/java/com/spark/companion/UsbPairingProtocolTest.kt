package com.spark.companion

import org.junit.Assert.*
import org.junit.Test

class UsbPairingProtocolTest {
    private val summary = "Last 7 days\n\nActivities: 3\nSteps: 12,345\nDistance: 56.78 km\n\nSource apps: com.example.fitness\n\nHealth Connect totals may include non-Garmin sources."
    @Test fun validatesManualEightDigitPairingCode() {
        assertEquals("12345678", UsbPairingProtocol.cleanCode(" 12345678 "))
        for (invalid in listOf("1234567", "123456789", "abcd1234", "1234 5678"))
            try { UsbPairingProtocol.cleanCode(invalid); fail("accepted invalid code") }
            catch (_: IllegalArgumentException) {}
    }
    @Test fun restrictsBearerTokenAndSequenceToBoundedValues() {
        assertTrue(UsbPairingProtocol.validToken("a".repeat(64)))
        assertFalse(UsbPairingProtocol.validToken("b".repeat(63)))
        assertFalse(UsbPairingProtocol.validToken("z".repeat(64)))
        assertEquals(2, UsbPairingProtocol.nextSequence(1))
        try { UsbPairingProtocol.nextSequence(1_000_000); fail("overflow") }
        catch (_: IllegalArgumentException) {}
    }
    @Test fun acceptsOnlyExactHealthConnectSummaryForExplicitTransfer() {
        assertTrue(UsbPairingProtocol.validSummary(summary))
        assertFalse(UsbPairingProtocol.validSummary("execute purchase"))
        assertFalse(UsbPairingProtocol.validSummary(summary+"\nsecret"))
    }
}
