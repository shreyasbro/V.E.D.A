package com.veda.assistant.tools

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.media.AudioManager
import android.view.KeyEvent
import org.json.JSONObject

class ClipboardTool(private val context: Context) : AndroidTool {
    override val name = "clipboard_manage"
    override val description = "Reads or sets the Android system clipboard text."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("action", JSONObject().put("type", "string").put("description", "'get' to read clipboard, 'set' to copy new text, 'clear' to empty"))
            put("text", JSONObject().put("type", "string").put("description", "Text to copy when action is 'set'"))
        })
        put("required", org.json.JSONArray().put("action"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val action = args.optString("action", "get").lowercase()
        val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
            ?: return ToolResult(false, "ClipboardManager unavailable")

        return when (action) {
            "set" -> {
                val text = args.optString("text", "")
                val clip = ClipData.newPlainText("VEDA", text)
                cm.setPrimaryClip(clip)
                ToolResult(true, "Copied text to clipboard: \"$text\"")
            }
            "clear" -> {
                cm.clearPrimaryClip()
                ToolResult(true, "Cleared system clipboard.")
            }
            else -> {
                val clip = cm.primaryClip
                if (clip != null && clip.itemCount > 0) {
                    val text = clip.getItemAt(0).coerceToText(context).toString()
                    ToolResult(true, "Clipboard content: \"$text\"")
                } else {
                    ToolResult(true, "Clipboard is currently empty.")
                }
            }
        }
    }
}

class MediaControlTool(private val context: Context) : AndroidTool {
    override val name = "media_control"
    override val description = "Controls media playback on the Android phone (play, pause, toggle, next, previous)."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("command", JSONObject().put("type", "string").put("description", "'play', 'pause', 'toggle', 'next', 'previous'"))
        })
        put("required", org.json.JSONArray().put("command"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val cmd = args.optString("command", "toggle").lowercase()
        val am = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            ?: return ToolResult(false, "AudioManager unavailable")

        val keyCode = when (cmd) {
            "play" -> KeyEvent.KEYCODE_MEDIA_PLAY
            "pause" -> KeyEvent.KEYCODE_MEDIA_PAUSE
            "next" -> KeyEvent.KEYCODE_MEDIA_NEXT
            "previous" -> KeyEvent.KEYCODE_MEDIA_PREVIOUS
            else -> KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE
        }

        return try {
            am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, keyCode))
            am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_UP, keyCode))
            ToolResult(true, "Dispatched media command: $cmd")
        } catch (e: Exception) {
            ToolResult(false, "Failed to control media: ${e.message}")
        }
    }
}
