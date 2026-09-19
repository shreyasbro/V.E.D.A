package com.veda.assistant.tools

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

class ToolRegistry(context: Context) {

    private val tools = mutableMapOf<String, AndroidTool>()

    init {
        register(OpenAppTool(context))
        register(OpenUrlTool(context))
        register(OpenSettingsTool(context))
        register(ShareContentTool(context))
        register(AccessibilityInspectTool())
        register(AccessibilityClickTool())
        register(AccessibilityNavTool())
        register(ClipboardTool(context))
        register(MediaControlTool(context))
        register(FileSearchTool(context))
        register(FileManageTool(context))
        register(DeviceInfoTool(context))
        register(CreateNotificationTool(context))
    }

    fun register(tool: AndroidTool) {
        tools[tool.name] = tool
    }

    fun getTool(name: String): AndroidTool? = tools[name]

    fun getAllTools(): List<AndroidTool> = tools.values.toList()

    fun getToolsSchemaJson(): JSONArray {
        val array = JSONArray()
        tools.values.forEach { tool ->
            val obj = JSONObject().apply {
                put("name", tool.name)
                put("description", tool.description)
                put("parameters", tool.parametersSchema)
            }
            array.put(obj)
        }
        return array
    }

    fun generateSystemPromptToolDescriptions(): String {
        val sb = StringBuilder()
        sb.appendLine("AVAILABLE ANDROID TOOLS ON THIS DEVICE:")
        tools.values.forEach { tool ->
            sb.appendLine("- ${tool.name}: ${tool.description}")
        }
        return sb.toString()
    }
}
