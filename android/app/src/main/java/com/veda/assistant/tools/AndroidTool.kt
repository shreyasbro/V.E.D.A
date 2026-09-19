package com.veda.assistant.tools

import org.json.JSONObject

interface AndroidTool {
    val name: String
    val description: String
    val parametersSchema: JSONObject

    suspend fun execute(args: JSONObject): ToolResult
}

data class ToolResult(
    val success: Boolean,
    val resultText: String,
    val data: JSONObject? = null,
    val permissionRequired: String? = null,
    val actionHint: String? = null
)
