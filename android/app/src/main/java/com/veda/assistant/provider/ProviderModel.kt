package com.veda.assistant.provider

data class ProviderSlot(
    val id: Int,
    val name: String,
    val model: String,
    val baseUrl: String = "",
    val apiKey: String = "",
    val enabled: Boolean = true,
    val isPrimary: Boolean = false,
    val status: String = "Not Tested", // "Connected", "Connection Failed", "Not Tested", "Testing..."
    val lastLatencyMs: Int? = null,
    val lastTested: String? = null,
    val providerPreset: String = "custom", // "gemini", "openai", "anthropic", "groq", "ollama", "custom"
    val availableModels: List<String> = emptyList()
) {
    fun maskedApiKey(): String {
        if (apiKey.isBlank()) return "Not configured"
        if (apiKey.length <= 8) return "••••••••"
        return "••••••••" + apiKey.takeLast(4)
    }
}
