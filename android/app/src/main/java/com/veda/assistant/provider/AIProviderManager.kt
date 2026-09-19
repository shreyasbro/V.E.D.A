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
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
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

    fun removeProvider(slotId: Int) {
        val index = providerSlots.indexOfFirst { it.id == slotId }
        if (index != -1) {
            val s = providerSlots[index]
            providerSlots[index] = s.copy(
                apiKey = "",
                baseUrl = "",
                enabled = false,
                status = "Not Tested",
                lastLatencyMs = null,
                lastTested = null,
                availableModels = emptyList()
            )
            keyStore.saveProviders(providerSlots)
        }
    }

    fun getActiveProvider(): ProviderSlot? {
        val primary = providerSlots.firstOrNull { it.enabled && it.isPrimary && it.apiKey.isNotBlank() }
        if (primary != null) return primary
        return providerSlots.firstOrNull { it.enabled && it.apiKey.isNotBlank() }
    }

    suspend fun fetchModels(slotId: Int): Result<List<String>> = withContext(Dispatchers.IO) {
        val slot = providerSlots.firstOrNull { it.id == slotId }
            ?: return@withContext Result.failure(Exception("Provider slot not found"))

        if (slot.apiKey.isBlank() && slot.providerPreset != "ollama") {
            return@withContext Result.failure(Exception("API key is required to fetch models"))
        }

        try {
            val models = when (slot.providerPreset) {
                "gemini" -> fetchGeminiModels(slot)
                "anthropic" -> fetchAnthropicModels(slot)
                else -> fetchOpenAiCompatibleModels(slot)
            }

            if (models.isEmpty()) {
                Result.failure(Exception("No models returned by provider"))
            } else {
                val updated = slot.copy(availableModels = models)
                updateSlotInMemory(updated)
                keyStore.saveProviders(providerSlots)
                Result.success(models)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun fetchGeminiModels(slot: ProviderSlot): List<String> {
        val url = "https://generativelanguage.googleapis.com/v1beta/models?key=" + slot.apiKey.trim()
        val req = Request.Builder().url(url).get().build()
        httpClient.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                val errBody = resp.body?.string() ?: ""
                throw IOException("Gemini API error (HTTP ${resp.code}): $errBody")
            }
            val json = JSONObject(resp.body?.string() ?: "{}")
            val modelsArray = json.optJSONArray("models") ?: JSONArray()
            val list = mutableListOf<String>()
            for (i in 0 until modelsArray.length()) {
                val m = modelsArray.getJSONObject(i)
                val name = m.getString("name").removePrefix("models/")
                val supportedMethods = m.optJSONArray("supportedGenerationMethods")
                var canGenerate = false
                if (supportedMethods != null) {
                    for (j in 0 until supportedMethods.length()) {
                        if (supportedMethods.getString(j) == "generateContent") canGenerate = true
                    }
                }
                if (canGenerate && !name.contains("embedding", ignoreCase = true)) {
                    list.add(name)
                }
            }
            return list.ifEmpty { listOf("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro") }
        }
    }

    private fun fetchAnthropicModels(slot: ProviderSlot): List<String> {
        val base = if (slot.baseUrl.isNotBlank()) slot.baseUrl.trimEnd('/') else "https://api.anthropic.com/v1"
        val url = "$base/models"
        val req = Request.Builder()
            .url(url)
            .addHeader("x-api-key", slot.apiKey.trim())
            .addHeader("anthropic-version", "2023-06-01")
            .get()
            .build()
        return try {
            httpClient.newCall(req).execute().use { resp ->
                if (resp.isSuccessful) {
                    val json = JSONObject(resp.body?.string() ?: "{}")
                    val data = json.optJSONArray("data") ?: JSONArray()
                    val list = mutableListOf<String>()
                    for (i in 0 until data.length()) {
                        list.add(data.getJSONObject(i).getString("id"))
                    }
                    list.ifEmpty { listOf("claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022") }
                } else {
                    listOf("claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229")
                }
            }
        } catch (e: Exception) {
            listOf("claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022")
        }
    }

    private fun fetchOpenAiCompatibleModels(slot: ProviderSlot): List<String> {
        val base = if (slot.baseUrl.isNotBlank()) slot.baseUrl.trimEnd('/') else "https://api.openai.com/v1"
        val url = "$base/models"
        val reqBuilder = Request.Builder().url(url).get()
        if (slot.apiKey.isNotBlank() && slot.providerPreset != "ollama") {
            reqBuilder.addHeader("Authorization", "Bearer " + slot.apiKey.trim())
        }
        httpClient.newCall(reqBuilder.build()).execute().use { resp ->
            if (!resp.isSuccessful) {
                val err = resp.body?.string() ?: ""
                throw IOException("Provider HTTP ${resp.code}: $err")
            }
            val json = JSONObject(resp.body?.string() ?: "{}")
            val data = json.optJSONArray("data") ?: JSONArray()
            val list = mutableListOf<String>()
            for (i in 0 until data.length()) {
                val id = data.getJSONObject(i).getString("id")
                if (!id.contains("embedding", ignoreCase = true) && !id.contains("whisper", ignoreCase = true) && !id.contains("tts", ignoreCase = true)) {
                    list.add(id)
                }
            }
            return list
        }
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
                "anthropic" -> testAnthropic(slot)
                else -> testOpenAiCompatible(slot)
            }
            val latency = (System.currentTimeMillis() - startTime).toInt()
            val timeStamp = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            val updated = slot.copy(status = "Connected", lastLatencyMs = latency, lastTested = timeStamp)
            updateSlotInMemory(updated)
            keyStore.saveProviders(providerSlots)
            Triple("Connected", latency, null)
        } catch (e: Exception) {
            val timeStamp = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            val updated = slot.copy(status = "Connection Failed", lastLatencyMs = null, lastTested = timeStamp)
            updateSlotInMemory(updated)
            keyStore.saveProviders(providerSlots)
            Triple("Connection Failed", null, e.message ?: "Connection failed")
        }
    }

    suspend fun testChat(slotId: Int, testMessage: String = "Hello V.E.D.A."): Result<Triple<String, Int, String>> = withContext(Dispatchers.IO) {
        val slot = providerSlots.firstOrNull { it.id == slotId }
            ?: return@withContext Result.failure(Exception("Provider not found"))

        val startTime = System.currentTimeMillis()
        try {
            val responseText = when (slot.providerPreset) {
                "gemini" -> executeSingleGemini(slot, testMessage)
                "anthropic" -> executeSingleAnthropic(slot, testMessage)
                else -> executeSingleOpenAiCompatible(slot, testMessage)
            }
            val latency = (System.currentTimeMillis() - startTime).toInt()
            Result.success(Triple(responseText, latency, slot.model))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun testGemini(slot: ProviderSlot) {
        val url = "https://generativelanguage.googleapis.com/v1beta/models?key=" + slot.apiKey.trim()
        val req = Request.Builder().url(url).get().build()
        httpClient.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw IOException("Gemini API error (HTTP ${resp.code}): " + (resp.body?.string() ?: ""))
            }
        }
    }

    private fun testAnthropic(slot: ProviderSlot) {
        val base = if (slot.baseUrl.isNotBlank()) slot.baseUrl.trimEnd('/') else "https://api.anthropic.com/v1"
        val url = "$base/models"
        val req = Request.Builder()
            .url(url)
            .addHeader("x-api-key", slot.apiKey.trim())
            .addHeader("anthropic-version", "2023-06-01")
            .get()
            .build()
        httpClient.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw IOException("Anthropic HTTP ${resp.code}: " + (resp.body?.string() ?: ""))
            }
        }
    }

    private fun testOpenAiCompatible(slot: ProviderSlot) {
        val base = if (slot.baseUrl.isNotBlank()) slot.baseUrl.trimEnd('/') else "https://api.openai.com/v1"
        val url = "$base/models"
        val reqBuilder = Request.Builder().url(url).get()
        if (slot.apiKey.isNotBlank() && slot.providerPreset != "ollama") {
            reqBuilder.addHeader("Authorization", "Bearer " + slot.apiKey.trim())
        }
        httpClient.newCall(reqBuilder.build()).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw IOException("API error (HTTP ${resp.code}): " + (resp.body?.string() ?: ""))
            }
        }
    }

    private fun executeSingleGemini(slot: ProviderSlot, prompt: String): String {
        val model = if (slot.model.isNotBlank()) slot.model else "gemini-2.0-flash"
        val url = "https://generativelanguage.googleapis.com/v1beta/models/$model:generateContent?key=" + slot.apiKey.trim()

        val body = JSONObject().apply {
            put("contents", JSONArray().put(JSONObject().apply {
                put("parts", JSONArray().put(JSONObject().put("text", prompt)))
            }))
        }.toString().toRequestBody("application/json".toMediaType())

        val req = Request.Builder().url(url).post(body).build()
        httpClient.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw IOException("HTTP ${resp.code}: " + (resp.body?.string() ?: ""))
            val json = JSONObject(resp.body?.string() ?: "{}")
            val cand = json.optJSONArray("candidates")?.getJSONObject(0)
            val parts = cand?.optJSONObject("content")?.optJSONArray("parts")
            return parts?.getJSONObject(0)?.optString("text", "No text received") ?: "Empty response"
        }
    }

    private fun executeSingleAnthropic(slot: ProviderSlot, prompt: String): String {
        val base = if (slot.baseUrl.isNotBlank()) slot.baseUrl.trimEnd('/') else "https://api.anthropic.com/v1"
        val url = "$base/messages"
        val model = if (slot.model.isNotBlank()) slot.model else "claude-3-5-sonnet-20241022"

        val body = JSONObject().apply {
            put("model", model)
            put("max_tokens", 256)
            put("messages", JSONArray().put(JSONObject().apply {
                put("role", "user")
                put("content", prompt)
            }))
        }.toString().toRequestBody("application/json".toMediaType())

        val req = Request.Builder()
            .url(url)
            .addHeader("x-api-key", slot.apiKey.trim())
            .addHeader("anthropic-version", "2023-06-01")
            .post(body)
            .build()

        httpClient.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw IOException("HTTP ${resp.code}: " + (resp.body?.string() ?: ""))
            val json = JSONObject(resp.body?.string() ?: "{}")
            val content = json.optJSONArray("content")?.getJSONObject(0)
            return content?.optString("text", "No response text") ?: "Empty response"
        }
    }

    private fun executeSingleOpenAiCompatible(slot: ProviderSlot, prompt: String): String {
        val base = if (slot.baseUrl.isNotBlank()) slot.baseUrl.trimEnd('/') else "https://api.openai.com/v1"
        val url = "$base/chat/completions"
        val model = if (slot.model.isNotBlank()) slot.model else "gpt-4o"

        val body = JSONObject().apply {
            put("model", model)
            put("max_tokens", 256)
            put("messages", JSONArray().put(JSONObject().apply {
                put("role", "user")
                put("content", prompt)
            }))
        }.toString().toRequestBody("application/json".toMediaType())

        val reqBuilder = Request.Builder().url(url).post(body)
        if (slot.apiKey.isNotBlank() && slot.providerPreset != "ollama") {
            reqBuilder.addHeader("Authorization", "Bearer " + slot.apiKey.trim())
        }

        httpClient.newCall(reqBuilder.build()).execute().use { resp ->
            if (!resp.isSuccessful) throw IOException("HTTP ${resp.code}: " + (resp.body?.string() ?: ""))
            val json = JSONObject(resp.body?.string() ?: "{}")
            val choice = json.optJSONArray("choices")?.getJSONObject(0)
            val msg = choice?.optJSONObject("message")
            return msg?.optString("content", "No response text") ?: "Empty response"
        }
    }

    private fun updateSlotInMemory(slot: ProviderSlot) {
        val index = providerSlots.indexOfFirst { it.id == slot.id }
        if (index != -1) {
            providerSlots[index] = slot
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
                } catch (e: Exception) {}
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
        val url = "$base/chat/completions"
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
        if (slot.apiKey.isNotBlank() && slot.providerPreset != "ollama") {
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
                } catch (e: Exception) {}
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
