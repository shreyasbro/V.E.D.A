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
        // Fallback to standard private preferences if device lacks Keystore hardware
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
                list.add(
                    ProviderSlot(
                        id = obj.getInt("id"),
                        name = obj.getString("name"),
                        model = obj.getString("model"),
                        baseUrl = obj.optString("baseUrl", ""),
                        apiKey = obj.optString("apiKey", ""),
                        enabled = obj.optBoolean("enabled", true),
                        isPrimary = obj.optBoolean("isPrimary", i == 0),
                        status = "IDLE",
                        providerPreset = obj.optString("providerPreset", "custom")
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
                providerPreset = "gemini"
            ),
            ProviderSlot(
                id = 2,
                name = "OpenAI",
                model = "gpt-4o",
                baseUrl = "https://api.openai.com/v1",
                apiKey = "",
                enabled = true,
                isPrimary = false,
                providerPreset = "openai"
            ),
            ProviderSlot(
                id = 3,
                name = "Anthropic Claude",
                model = "claude-3-5-sonnet-20241022",
                baseUrl = "https://api.anthropic.com/v1",
                apiKey = "",
                enabled = true,
                isPrimary = false,
                providerPreset = "anthropic"
            ),
            ProviderSlot(
                id = 4,
                name = "Groq Llama 3",
                model = "llama-3.3-70b-versatile",
                baseUrl = "https://api.groq.com/openai/v1",
                apiKey = "",
                enabled = true,
                isPrimary = false,
                providerPreset = "groq"
            ),
            ProviderSlot(
                id = 5,
                name = "Ollama Local API",
                model = "llama3.2",
                baseUrl = "http://localhost:11434/v1",
                apiKey = "ollama",
                enabled = false,
                isPrimary = false,
                providerPreset = "ollama"
            ),
            ProviderSlot(
                id = 6,
                name = "Custom OpenAI Compatible",
                model = "default-model",
                baseUrl = "",
                apiKey = "",
                enabled = false,
                isPrimary = false,
                providerPreset = "custom"
            )
        )
    }
}
