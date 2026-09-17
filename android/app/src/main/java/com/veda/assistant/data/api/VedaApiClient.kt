package com.veda.assistant.data.api

import com.veda.assistant.data.model.ProviderSlot
import com.veda.assistant.data.model.ServerStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
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

class VedaApiClient(private var baseUrl: String = "http://10.0.2.2:8765") {

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    private val sseFactory = EventSources.createFactory(client)

    fun updateBaseUrl(url: String) {
        baseUrl = url.trimEnd('/')
    }

    fun getBaseUrl(): String = baseUrl

    suspend fun fetchStatus(): Result<ServerStatus> = withContext(Dispatchers.IO) {
        try {
            val req = Request.Builder().url(baseUrl + "/api/status").get().build()
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return@withContext Result.failure(IOException("HTTP " + resp.code))
                val json = JSONObject(resp.body?.string() ?: "{}")
                Result.success(
                    ServerStatus(
                        status = json.optString("status", "offline"),
                        activeProvider = json.optString("active_provider", "Offline"),
                        providerMode = json.optString("provider_mode", "AUTOMATIC"),
                        selectedProvider = json.optString("selected_provider", "GEMINI"),
                        desktopConnected = json.optString("status") == "online",
                        pairingPin = json.optString("pairing_pin", "")
                    )
                )
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun fetchProviders(): Result<List<ProviderSlot>> = withContext(Dispatchers.IO) {
        try {
            val req = Request.Builder().url(baseUrl + "/api/providers").get().build()
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return@withContext Result.failure(IOException("HTTP " + resp.code))
                val json = JSONObject(resp.body?.string() ?: "{}")
                val slotsArray = json.optJSONArray("slots") ?: JSONArray()
                val list = mutableListOf<ProviderSlot>()
                for (i in 0 until slotsArray.length()) {
                    val s = slotsArray.getJSONObject(i)
                    list.add(
                        ProviderSlot(
                            id = s.getInt("id"),
                            name = s.getString("name"),
                            model = s.getString("model"),
                            enabled = s.getBoolean("enabled"),
                            status = s.getString("status"),
                            lastLatencyMs = if (s.has("last_latency_ms") && !s.isNull("last_latency_ms")) s.getInt("last_latency_ms") else null,
                            providerPreset = s.optString("provider_preset", "custom")
                        )
                    )
                }
                Result.success(list)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    fun streamChat(
        prompt: String,
        history: List<Pair<String, String>>,
        languageMode: String = "AUTO"
    ): Flow<Pair<String, String>> = callbackFlow {
        val payload = JSONObject().apply {
            put("prompt", prompt)
            put("language_mode", languageMode)
            val histArray = JSONArray()
            history.takeLast(6).forEach { pair ->
                histArray.put(JSONObject().apply {
                    put("role", pair.first)
                    put("content", pair.second)
                })
            }
            put("history", histArray)
        }

        val body = payload.toString().toRequestBody("application/json".toMediaType())
        val req = Request.Builder()
            .url(baseUrl + "/api/chat")
            .post(body)
            .build()

        val eventSource = sseFactory.newEventSource(req, object : EventSourceListener() {
            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                try {
                    val obj = JSONObject(data)
                    if (obj.has("chunk")) {
                        val chunk = obj.getString("chunk")
                        val prov = obj.optString("provider", "Gemini")
                        trySend(Pair(chunk, prov))
                    }
                    if (obj.optBoolean("done", false)) {
                        channel.close()
                    }
                    if (obj.has("error")) {
                        trySend(Pair("\n[Error: " + obj.getString("error") + "]", "Error"))
                        channel.close()
                    }
                } catch (e: Exception) {
                    trySend(Pair("\n[Parse error]", "Error"))
                }
            }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                trySend(Pair(" [Connection error: offline fallback]", "Offline"))
                channel.close(t)
            }

            override fun onClosed(eventSource: EventSource) {
                channel.close()
            }
        })

        awaitClose {
            eventSource.cancel()
        }
    }

    suspend fun analyzeImage(base64Image: String, prompt: String): Result<String> = withContext(Dispatchers.IO) {
        try {
            val payload = JSONObject().apply {
                put("image", base64Image)
                put("prompt", prompt)
            }
            val body = payload.toString().toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(baseUrl + "/api/vision").post(body).build()
            client.newCall(req).execute().use { resp ->
                val json = JSONObject(resp.body?.string() ?: "{}")
                if (json.optBoolean("success", false)) {
                    Result.success(json.optString("analysis", "Image analyzed successfully."))
                } else {
                    Result.failure(Exception(json.optString("error", "Vision analysis failed")))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun pairWithDesktop(pin: String): Result<String> = withContext(Dispatchers.IO) {
        try {
            val payload = JSONObject().apply {
                put("pin", pin)
                put("device_name", "V.E.D.A. Android Client")
            }
            val body = payload.toString().toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(baseUrl + "/api/pair").post(body).build()
            client.newCall(req).execute().use { resp ->
                val json = JSONObject(resp.body?.string() ?: "{}")
                if (json.optBoolean("success", false)) {
                    Result.success(json.getString("token"))
                } else {
                    Result.failure(Exception(json.optString("error", "Pairing failed")))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
