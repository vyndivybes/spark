package com.spark.companion

import org.junit.Assert.*
import org.junit.Test

class MobileAiProtocolTest {
    @Test fun rejectsControlCharactersAndOversizedChatPrompts() {
        assertTrue(UsbPairingProtocol.validChatPrompt("How do wings produce lift?"))
        assertFalse(UsbPairingProtocol.validChatPrompt("no"))
        assertFalse(UsbPairingProtocol.validChatPrompt("x".repeat(401)))
        assertFalse(UsbPairingProtocol.validChatPrompt("Run\u0000this"))
    }

    @Test fun allowsOnlyTextAnswerAndAdvisoryStatus() {
        assertTrue(UsbPairingProtocol.validChatAnswer("A wing deflects air.", "gemini"))
        assertTrue(UsbPairingProtocol.validChatAnswer("Aircraft engines", "groq"))
        assertFalse(UsbPairingProtocol.validChatAnswer("", "groq"))
        assertFalse(UsbPairingProtocol.validChatAnswer("x".repeat(2801),"gemini"))
        assertFalse(UsbPairingProtocol.validChatAnswer("Text","remote-shell"))
    }
}
