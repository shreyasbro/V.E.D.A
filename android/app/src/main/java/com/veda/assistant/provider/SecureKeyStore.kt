package com.veda.assistant.provider

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import org.json.JSONArray
import org.json.JSONObject

class SecureKeyStore(context: Context) {

    private val prefs: SharedPreferences = try {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "veda_secure_providers",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) {
        // Fallback to private preferences if Keystore hardware is unavailable
        context.getSharedPreferences("veda_secure_providers_fb", Context.MODE_PRIVATE)
    }

    fun saveProviders(slots: List<ProviderSlot>) {
        val array = JSONArray()
        slots.forEach { slot ->
            val obj = JSONObject().apply {
                put("id", slot.id)
                put("name", slot.name)
                put("model", slot.model)
                put("baseUrl", slot.baseUrl)
                put("apiKey", slot.apiKey)
                put("enabled", slot.enabled)
                put("isPrimary", slot.isPrimary)
                put("providerPreset", slot.providerPreset)
                put("status", slot.status)
                if (slot.lastLatencyMs != null) put("lastLatencyMs", slot.lastLatencyMs)
                if (slot.lastTested != null) put("lastTested", slot.lastTested)
                val modelsArr = JSONArray()
                slot.availableModels.forEach { modelsArr.put(it) }
                put("availableModels", modelsArr)
            }
            array.put(obj)
        }
        prefs.edit().putString("provider_slots_json", array.toString()).apply()
    }

    fun loadProviders(): List<ProviderSlot> {
        val raw = prefs.getString("provider_slots_json", null)
        if (raw.isNullOrBlank()) {
            return defaultProviderSlots()
        }

        return try {
            val array = JSONArray(raw)
            val list = mutableListOf<ProviderSlot>()
            for (i in 0 until array.length()) {
                val obj = array.getJSONObject(i)
                val modelsList = mutableListOf<String>()
                val modelsArr = obj.optJSONArray("availableModels")
                if (modelsArr != null) {
                    for (j in 0 until modelsArr.length()) {
                        modelsList.add(modelsArr.getString(j))
                    }
                }

                list.add(
                    ProviderSlot(
                        id = obj.getInt("id"),
                        name = obj.getString("name"),
                        model = obj.getString("model"),
                        baseUrl = obj.optString("baseUrl", ""),
                        apiKey = obj.optString("apiKey", ""),
                        enabled = obj.optBoolean("enabled", true),
                        isPrimary = obj.optBoolean("isPrimary", i == 0),
                        status = obj.optString("status", "Not Tested"),
                        lastLatencyMs = if (obj.has("lastLatencyMs") && !obj.isNull("lastLatencyMs")) obj.getInt("lastLatencyMs") else null,
                        lastTested = if (obj.has("lastTested") && !obj.isNull("lastTested")) obj.getString("lastTested") else null,
                        providerPreset = obj.optString("providerPreset", "custom"),
                        availableModels = modelsList
                    )
                )
            }
            if (list.isEmpty()) defaultProviderSlots() else list
        } catch (e: Exception) {
            defaultProviderSlots()
        }
    }

    private fun defaultProviderSlots(): List<ProviderSlot> {
        return listOf(
            ProviderSlot(
                id = 1,
                name = "Google Gemini",
                model = "gemini-2.0-flash",
                baseUrl = "https://generativelanguage.googleapis.com/v1beta",
                apiKey = "",
                enabled = true,
                isPrimary = true,
                providerPreset = "gemini",
                availableModels = listOf("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro")
            ),
            ProviderSlot(
                id = 2,
                name = "OpenAI",
                model = "gpt-4o",
                baseUrl = "https://api.openai.com/v1",
                apiKey = "",
                enabled = true,
                isPrimary = false,
                providerPreset = "openai",
                availableModels = listOf("gpt-4o", "gpt-4o-mini", "gpt-4-turbo")
            ),
            ProviderSlot(
                id = 3,
                name = "Anthropic Claude",
                model = "claude-3-5-sonnet-20241022",
                baseUrl = "https://api.anthropic.com/v1",
                apiKey = "",
                enabled = true,
                isPrimary = false,
                providerPreset = "anthropic",
                availableModels = listOf("claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022")
            ),
            ProviderSlot(
                id = 4,
                name = "Groq",
                model = "llama-3.3-70b-versatile",
                baseUrl = "https://api.groq.com/openai/v1",
                apiKey = "",
                enabled = true,
                isPrimary = false,
                providerPreset = "groq",
                availableModels = listOf("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768")
            ),
            ProviderSlot(
                id = 5,
                name = "Ollama Local API",
                model = "llama3.2",
                baseUrl = "http://10.0.2.2:11434/v1",
                apiKey = "ollama",
                enabled = false,
                isPrimary = false,
                providerPreset = "ollama",
                availableModels = listOf("llama3.2", "llama3.1", "mistral", "qwen2.5")
            ),
            ProviderSlot(
                id = 6,
                name = "Custom OpenAI Compatible",
                model = "default-model",
                baseUrl = "",
                apiKey = "",
                enabled = false,
                isPrimary = false,
                providerPreset = "custom",
                availableModels = emptyList()
            )
        )
    }
}
