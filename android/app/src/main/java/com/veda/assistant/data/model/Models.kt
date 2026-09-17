package com.veda.assistant.data.model

data class ChatMessage(
    val id: String = java.util.UUID.randomUUID().toString(),
    val sender: String, // "user" or "assistant"
    val content: String,
    val provider: String = "Gemini",
    val timestamp: Long = System.currentTimeMillis(),
    val isStreaming: Boolean = false
)

data class ProviderSlot(
    val id: Int,
    val name: String,
    val model: String,
    val enabled: Boolean,
    val status: String,
    val lastLatencyMs: Int?,
    val providerPreset: String
)

data class ServerStatus(
    val status: String, // "online" or "offline"
    val activeProvider: String,
    val providerMode: String,
    val selectedProvider: String,
    val desktopConnected: Boolean,
    val pairingPin: String
)
