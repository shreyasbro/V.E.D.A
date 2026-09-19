package com.veda.assistant.provider

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class AIProviderManager(context: Context) {

    private val keyStore = SecureKeyStore(context)
    private var providerSlots: MutableList<ProviderSlot> = keyStore.loadProviders().toMutableList()

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    private val sseFactory = EventSources.createFactory(httpClient)

    fun getProviders(): List<ProviderSlot> = providerSlots.toList()

    fun updateProvider(slot: ProviderSlot) {
        val index = providerSlots.indexOfFirst { it.id == slot.id }
        if (index != -1) {
            providerSlots[index] = slot
            keyStore.saveProviders(providerSlots)
        }
    }

    fun setPrimaryProvider(slotId: Int) {
        for (i in 0 until providerSlots.size) {
            val s = providerSlots[i]
            providerSlots[i] = s.copy(isPrimary = (s.id == slotId))
        }
        keyStore.saveProviders(providerSlots)
    }

    fun getActiveProvider(): ProviderSlot? {
        val primary = providerSlots.firstOrNull { it.enabled && it.isPrimary && it.apiKey.isNotBlank() }
        if (primary != null) return primary
        return providerSlots.firstOrNull { it.enabled && it.apiKey.isNotBlank() }
    }

    suspend fun testConnection(slotId: Int): Triple<String, Int?, String?> = withContext(Dispatchers.IO) {
        val slot = providerSlots.firstOrNull { it.id == slotId }
            ?: return@withContext Triple("ERROR", null, "Provider not found")

        if (slot.apiKey.isBlank() && slot.providerPreset != "ollama") {
            return@withContext Triple("ERROR", null, "API key is not configured")
        }

        val startTime = System.currentTimeMillis()
        try {
            when (slot.providerPreset) {
                "gemini" -> testGemini(slot)
                else -> testOpenAiCompatible(slot)
            }
            val latency = (System.currentTimeMillis() - startTime).toInt()
            val updated = slot.copy(status = "CONNECTED", lastLatencyMs = latency)
            updateSlotInMemory(updated)
            Triple("CONNECTED", latency, null)
        } catch (e: Exception) {
            val updated = slot.copy(status = "ERROR", lastLatencyMs = null)
            updateSlotInMemory(updated)
            Triple("ERROR", null, e.message ?: "Connection failed")
        }
    }

    private fun updateSlotInMemory(slot: ProviderSlot) {
        val index = providerSlots.indexOfFirst { it.id == slot.id }
        if (index != -1) {
            providerSlots[index] = slot
        }
    }

    private fun testGemini(slot: ProviderSlot) {
        val url = "https://generativelanguage.googleapis.com/v1beta/models?key=" + slot.apiKey.trim()
        val req = Request.Builder().url(url).get().build()
        httpClient.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw IOException("Gemini API error (HTTP " + resp.code + "): " + (resp.body?.string() ?: ""))
            }
        }
    }

    private fun testOpenAiCompatible(slot: ProviderSlot) {
        val base = if (slot.baseUrl.isNotBlank()) slot.baseUrl.trimEnd('/') else "https://api.openai.com/v1"
        val url = base + "/models"
        val reqBuilder = Request.Builder().url(url).get()
        if (slot.apiKey.isNotBlank()) {
            reqBuilder.addHeader("Authorization", "Bearer " + slot.apiKey.trim())
        }
        httpClient.newCall(reqBuilder.build()).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw IOException("API error (HTTP " + resp.code + "): " + (resp.body?.string() ?: ""))
            }
        }
    }

    suspend fun executeChat(
        systemPrompt: String,
        messages: List<Pair<String, String>>,
        toolsSchema: JSONArray? = null
    ): Flow<String> = callbackFlow {
        val active = getActiveProvider()
        if (active == null) {
            trySend("Error: No configured and enabled AI provider found. Please open Settings -> AI Providers and configure your API key.")
            close()
            return@callbackFlow
        }

        if (active.providerPreset == "gemini") {
            streamGemini(active, systemPrompt, messages, this)
        } else {
            streamOpenAiCompatible(active, systemPrompt, messages, this)
        }
    }

    private fun streamGemini(
        slot: ProviderSlot,
        systemPrompt: String,
        messages: List<Pair<String, String>>,
        flowScope: kotlinx.coroutines.channels.ProducerScope<String>
    ) {
        val model = if (slot.model.isNotBlank()) slot.model else "gemini-2.0-flash"
        val url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":streamGenerateContent?alt=sse&key=" + slot.apiKey.trim()

        val contents = JSONArray()
        messages.forEach { pair ->
            val role = if (pair.first == "assistant") "model" else "user"
            contents.put(JSONObject().apply {
                put("role", role)
                put("parts", JSONArray().put(JSONObject().put("text", pair.second)))
            })
        }

        val bodyJson = JSONObject().apply {
            put("systemInstruction", JSONObject().apply {
                put("parts", JSONArray().put(JSONObject().put("text", systemPrompt)))
            })
            put("contents", contents)
        }

        val reqBody = bodyJson.toString().toRequestBody("application/json".toMediaType())
        val req = Request.Builder().url(url).post(reqBody).build()

        val eventSource = sseFactory.newEventSource(req, object : EventSourceListener() {
            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                try {
                    val root = JSONObject(data)
                    val cands = root.optJSONArray("candidates")
                    if (cands != null && cands.length() > 0) {
                        val firstCand = cands.getJSONObject(0)
                        val content = firstCand.optJSONObject("content")
                        val parts = content?.optJSONArray("parts")
                        if (parts != null && parts.length() > 0) {
                            val text = parts.getJSONObject(0).optString("text", "")
                            if (text.isNotEmpty()) {
                                flowScope.trySend(text)
                            }
                        }
                    }
                } catch (e: Exception) {
                    // JSON partial chunk parsing
                }
            }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                flowScope.trySend("\n[Network / API Error: " + (t?.message ?: response?.message ?: "Unknown") + "]")
                flowScope.channel.close(t)
            }

            override fun onClosed(eventSource: EventSource) {
                flowScope.channel.close()
            }
        })

        flowScope.invokeOnClose { eventSource.cancel() }
    }

    private fun streamOpenAiCompatible(
        slot: ProviderSlot,
        systemPrompt: String,
        messages: List<Pair<String, String>>,
        flowScope: kotlinx.coroutines.channels.ProducerScope<String>
    ) {
        val base = if (slot.baseUrl.isNotBlank()) slot.baseUrl.trimEnd('/') else "https://api.openai.com/v1"
        val url = base + "/chat/completions"
        val model = if (slot.model.isNotBlank()) slot.model else "gpt-4o"

        val msgArray = JSONArray()
        msgArray.put(JSONObject().put("role", "system").put("content", systemPrompt))
        messages.forEach { pair ->
            msgArray.put(JSONObject().put("role", pair.first).put("content", pair.second))
        }

        val bodyJson = JSONObject().apply {
            put("model", model)
            put("stream", true)
            put("messages", msgArray)
        }

        val reqBody = bodyJson.toString().toRequestBody("application/json".toMediaType())
        val reqBuilder = Request.Builder().url(url).post(reqBody)
        if (slot.apiKey.isNotBlank()) {
            reqBuilder.addHeader("Authorization", "Bearer " + slot.apiKey.trim())
        }

        val eventSource = sseFactory.newEventSource(reqBuilder.build(), object : EventSourceListener() {
            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                if (data.trim() == "[DONE]") {
                    flowScope.channel.close()
                    return
                }
                try {
                    val root = JSONObject(data)
                    val choices = root.optJSONArray("choices")
                    if (choices != null && choices.length() > 0) {
                        val delta = choices.getJSONObject(0).optJSONObject("delta")
                        val text = delta?.optString("content", "") ?: ""
                        if (text.isNotEmpty()) {
                            flowScope.trySend(text)
                        }
                    }
                } catch (e: Exception) {
                    // Ignore parse errors on SSE events
                }
            }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                flowScope.trySend("\n[Network / API Error: " + (t?.message ?: response?.message ?: "Unknown") + "]")
                flowScope.channel.close(t)
            }

            override fun onClosed(eventSource: EventSource) {
                flowScope.channel.close()
            }
        })

        flowScope.invokeOnClose { eventSource.cancel() }
    }
}
