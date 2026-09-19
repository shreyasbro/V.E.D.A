package com.veda.assistant.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class VedaAccessibilityService : AccessibilityService() {

    companion object {
        var instance: VedaAccessibilityService? = null
            private set

        val isRunning: Boolean
            get() = instance != null
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Can track active package name or screen transitions
    }

    override fun onInterrupt() {
        instance = null
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
    }

    fun findNodesByText(text: String): List<AccessibilityNodeInfo> {
        val root = rootInActiveWindow ?: return emptyList()
        return root.findAccessibilityNodeInfosByText(text) ?: emptyList()
    }

    fun findNodesById(viewId: String): List<AccessibilityNodeInfo> {
        val root = rootInActiveWindow ?: return emptyList()
        return root.findAccessibilityNodeInfosByViewId(viewId) ?: emptyList()
    }

    fun dumpVisibleText(): String {
        val root = rootInActiveWindow ?: return "Screen is empty or accessibility root unavailable."
        val builder = StringBuilder()
        traverseNodes(root, builder, 0)
        return builder.toString()
    }

    private fun traverseNodes(node: AccessibilityNodeInfo?, sb: StringBuilder, depth: Int) {
        if (node == null) return
        val text = node.text?.toString()?.trim()
        val desc = node.contentDescription?.toString()?.trim()
        val isClickable = node.isClickable
        val isEditable = node.isEditable

        if (!text.isNullOrEmpty() || !desc.isNullOrEmpty()) {
            val indent = "  ".repeat(depth.coerceAtMost(4))
            val label = text ?: desc
            val flags = mutableListOf<String>()
            if (isClickable) flags.add("clickable")
            if (isEditable) flags.add("editable")
            val flagStr = if (flags.isNotEmpty()) " [${flags.joinToString(", ")}]" else ""
            sb.appendLine("$indent• $label$flagStr")
        }

        for (i in 0 until node.childCount) {
            traverseNodes(node.getChild(i), sb, depth + 1)
        }
    }

    fun performClickOnNode(text: String): Boolean {
        val matches = findNodesByText(text)
        for (node in matches) {
            var current: AccessibilityNodeInfo? = node
            while (current != null) {
                if (current.isClickable) {
                    val clicked = current.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    if (clicked) return true
                }
                current = current.parent
            }
        }
        return false
    }

    fun performScroll(forward: Boolean): Boolean {
        val root = rootInActiveWindow ?: return false
        val action = if (forward) AccessibilityNodeInfo.ACTION_SCROLL_FORWARD else AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        return root.performAction(action)
    }

    fun performGlobalActionNav(actionType: String): Boolean {
        val act = when (actionType.lowercase()) {
            "back" -> GLOBAL_ACTION_BACK
            "home" -> GLOBAL_ACTION_HOME
            "recents" -> GLOBAL_ACTION_RECENTS
            "notifications" -> GLOBAL_ACTION_NOTIFICATIONS
            else -> return false
        }
        return performGlobalAction(act)
    }
}
