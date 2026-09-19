package com.veda.assistant.tools

import com.veda.assistant.accessibility.VedaAccessibilityService
import org.json.JSONObject

class AccessibilityInspectTool : AndroidTool {
    override val name = "accessibility_inspect_screen"
    override val description = "Inspects and reads visible UI elements, buttons, and text from the active screen using Accessibility Service."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject())
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val service = VedaAccessibilityService.instance
            ?: return ToolResult(
                success = false,
                resultText = "Accessibility Service is not enabled. Please enable V.E.D.A. Accessibility Service in Android Settings.",
                permissionRequired = "android.permission.BIND_ACCESSIBILITY_SERVICE",
                actionHint = "OPEN_ACCESSIBILITY_SETTINGS"
            )

        val dump = service.dumpVisibleText()
        return ToolResult(
            success = true,
            resultText = "Current Visible Screen Content:\n$dump"
        )
    }
}

class AccessibilityClickTool : AndroidTool {
    override val name = "accessibility_click"
    override val description = "Clicks a button, link, or accessible element on the screen matching the specified label or text."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("target_text", JSONObject().put("type", "string").put("description", "Text or description of the button/element to click"))
        })
        put("required", org.json.JSONArray().put("target_text"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val service = VedaAccessibilityService.instance
            ?: return ToolResult(
                success = false,
                resultText = "Accessibility Service is not enabled. Please enable it in Settings.",
                permissionRequired = "android.permission.BIND_ACCESSIBILITY_SERVICE"
            )

        val targetText = args.optString("target_text", "").trim()
        val success = service.performClickOnNode(targetText)
        return if (success) {
            ToolResult(true, "Successfully clicked on UI element '$targetText'.")
        } else {
            ToolResult(false, "Could not find a clickable element matching '$targetText'. Try inspecting screen first.")
        }
    }
}

class AccessibilityNavTool : AndroidTool {
    override val name = "accessibility_navigation"
    override val description = "Performs global navigation actions: 'back', 'home', 'recents', 'scroll_down', 'scroll_up'."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("action", JSONObject().put("type", "string").put("description", "'back', 'home', 'recents', 'scroll_down', 'scroll_up'"))
        })
        put("required", org.json.JSONArray().put("action"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val service = VedaAccessibilityService.instance
            ?: return ToolResult(
                success = false,
                resultText = "Accessibility Service is not enabled.",
                permissionRequired = "android.permission.BIND_ACCESSIBILITY_SERVICE"
            )

        val action = args.optString("action", "").lowercase()
        val ok = when (action) {
            "back", "home", "recents" -> service.performGlobalActionNav(action)
            "scroll_down" -> service.performScroll(true)
            "scroll_up" -> service.performScroll(false)
            else -> false
        }

        return ToolResult(ok, if (ok) "Performed action $action" else "Failed to perform action $action")
    }
}
