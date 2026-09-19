package com.veda.assistant.agent

import android.content.Context
import com.veda.assistant.provider.AIProviderManager
import com.veda.assistant.tools.ToolRegistry
import com.veda.assistant.tools.ToolResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.regex.Pattern

class AgentCore(private val context: Context) {

    val providerManager = AIProviderManager(context)
    val toolRegistry = ToolRegistry(context)

    private val conversationHistory = mutableListOf<Pair<String, String>>()

    fun getHistory(): List<Pair<String, String>> = conversationHistory.toList()

    fun clearHistory() {
        conversationHistory.clear()
    }

    private fun buildSystemPrompt(): String {
        val toolsDesc = toolRegistry.generateSystemPromptToolDescriptions()
        return """
You are V.E.D.A. (Virtual Executive Desktop Assistant) — Standalone Mobile Edition, created by Shreyas.
You run natively as a real Android application on the user's mobile device.
You have genuine system access through official Android APIs and the Tool Registry below.

Languages Supported:
- English, Hindi, and Hinglish. Understand informal and colloquial phrases naturally.

$toolsDesc

IMPORTANT TOOL INVOCATION FORMAT:
When the user asks you to perform an action on the phone, execute a tool using this EXACT JSON markdown format on a separate line:

```json
{"tool": "open_app", "args": {"app_name": "WhatsApp"}}
```

Do NOT ask permission for supported tools. Execute them directly.
If no tool is required, respond conversationally with helpful insight.
Never hallucinate or pretend an action succeeded without using the tool.
        """.trimIndent()
    }

    suspend fun processUserMessageStream(
        userText: String,
        onToolActionStart: ((String) -> Unit)? = null,
        onToolActionComplete: ((String, ToolResult) -> Unit)? = null
    ): Flow<String> = flow {
        conversationHistory.add(Pair("user", userText))

        val active = providerManager.getActiveProvider()
        if (active == null) {
            val err = "V.E.D.A. requires an active AI provider. Please tap Settings ⚙ -> AI Providers to configure your API key."
            emit(err)
            conversationHistory.add(Pair("assistant", err))
            return@flow
        }

        var accumulatedReply = ""

        try {
            val stream = providerManager.executeChat(
                systemPrompt = buildSystemPrompt(),
                messages = conversationHistory
            )

            stream.collect { chunk ->
                accumulatedReply += chunk
                emit(chunk)
            }

            // Check if accumulated response contains a tool call
            val toolCallPattern = Pattern.compile("```json\\s*(\\{.*?\\})\\s*```", Pattern.DOTALL)
            val matcher = toolCallPattern.matcher(accumulatedReply)
            if (matcher.find()) {
                val jsonStr = matcher.group(1)
                try {
                    val jsonObj = JSONObject(jsonStr)
                    val toolName = jsonObj.optString("tool", "")
                    val args = jsonObj.optJSONObject("args") ?: JSONObject()

                    val tool = toolRegistry.getTool(toolName)
                    if (tool != null) {
                        onToolActionStart?.invoke(toolName)
                        emit("\n\n[⚡ Executing: ${tool.name}...]\n")
                        val result = withContext(Dispatchers.IO) {
                            tool.execute(args)
                        }
                        onToolActionComplete?.invoke(toolName, result)

                        val statusPrefix = if (result.success) "✓ " else "✕ "
                        emit("\n$statusPrefix${result.resultText}\n")
                        accumulatedReply += "\n$statusPrefix${result.resultText}"
                    }
                } catch (e: Exception) {
                    // Tool JSON parsing error
                }
            }

            conversationHistory.add(Pair("assistant", accumulatedReply))
        } catch (e: Exception) {
            emit("\n[Agent Error: ${e.message}]")
        }
    }
}
