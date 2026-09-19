package com.veda.assistant.tools

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import org.json.JSONObject

class OpenAppTool(private val context: Context) : AndroidTool {
    override val name = "open_app"
    override val description = "Opens an installed Android application by name or package identifier."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("app_name", JSONObject().put("type", "string").put("description", "Name of the app (e.g. 'WhatsApp', 'Chrome', 'YouTube', 'Settings')"))
            put("package_name", JSONObject().put("type", "string").put("description", "Optional exact package name"))
        })
        put("required", org.json.JSONArray().put("app_name"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val appName = args.optString("app_name", "").trim()
        val pkgArg = args.optString("package_name", "").trim()

        val pm = context.packageManager
        var targetPkg: String? = null

        if (pkgArg.isNotEmpty()) {
            targetPkg = pkgArg
        } else {
            // Match against installed apps
            val packages = pm.getInstalledApplications(0)
            val matched = packages.firstOrNull { appInfo ->
                val label = pm.getApplicationLabel(appInfo).toString()
                label.equals(appName, ignoreCase = true) || label.contains(appName, ignoreCase = true)
            }
            if (matched != null) {
                targetPkg = matched.packageName
            }
        }

        if (targetPkg == null) {
            // Common fallbacks
            targetPkg = when (appName.lowercase()) {
                "chrome", "google chrome" -> "com.android.chrome"
                "youtube" -> "com.google.android.youtube"
                "whatsapp" -> "com.whatsapp"
                "maps", "google maps" -> "com.google.android.apps.maps"
                "camera" -> "com.android.camera"
                "settings" -> "com.android.settings"
                "clock", "alarm" -> "com.google.android.deskclock"
                "calculator" -> "com.google.android.calculator"
                else -> null
            }
        }

        if (targetPkg == null) {
            return ToolResult(
                success = false,
                resultText = "App '$appName' was not found on this Android device."
            )
        }

        val launchIntent = pm.getLaunchIntentForPackage(targetPkg)
        return if (launchIntent != null) {
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(launchIntent)
            ToolResult(
                success = true,
                resultText = "Successfully opened $appName ($targetPkg) on device."
            )
        } else {
            ToolResult(
                success = false,
                resultText = "App $targetPkg is installed but has no launchable activity."
            )
        }
    }
}

class OpenUrlTool(private val context: Context) : AndroidTool {
    override val name = "open_url"
    override val description = "Opens a web URL or deep-link in the user's default browser or associated application."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("url", JSONObject().put("type", "string").put("description", "Full URL to open (e.g. 'https://github.com/shreyasbro/V.E.D.A')"))
        })
        put("required", org.json.JSONArray().put("url"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        var url = args.optString("url", "").trim()
        if (url.isEmpty()) return ToolResult(false, "No URL provided")
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "https://" + url
        }

        return try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            ToolResult(true, "Opened URL: $url")
        } catch (e: Exception) {
            ToolResult(false, "Failed to open URL: ${e.message}")
        }
    }
}

class OpenSettingsTool(private val context: Context) : AndroidTool {
    override val name = "open_android_settings"
    override val description = "Opens specific Android system settings (e.g. wifi, bluetooth, accessibility, apps, display)."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("setting_type", JSONObject().put("type", "string").put("description", "Type of setting: 'wifi', 'bluetooth', 'accessibility', 'notifications', 'apps', 'sound', 'main'"))
        })
        put("required", org.json.JSONArray().put("setting_type"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val type = args.optString("setting_type", "main").lowercase()
        val action = when (type) {
            "wifi" -> Settings.ACTION_WIFI_SETTINGS
            "bluetooth" -> Settings.ACTION_BLUETOOTH_SETTINGS
            "accessibility" -> Settings.ACTION_ACCESSIBILITY_SETTINGS
            "notifications" -> Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS
            "apps" -> Settings.ACTION_APPLICATION_SETTINGS
            "sound" -> Settings.ACTION_SOUND_SETTINGS
            else -> Settings.ACTION_SETTINGS
        }

        return try {
            val intent = Intent(action).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            ToolResult(true, "Opened Android $type settings.")
        } catch (e: Exception) {
            ToolResult(false, "Unable to open settings: ${e.message}")
        }
    }
}

class ShareContentTool(private val context: Context) : AndroidTool {
    override val name = "share_content"
    override val description = "Shares text or a message using Android's native Share Sheet to any messaging or social app."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("text", JSONObject().put("type", "string").put("description", "Text content to share"))
            put("title", JSONObject().put("type", "string").put("description", "Optional share sheet title"))
        })
        put("required", org.json.JSONArray().put("text"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val text = args.optString("text", "")
        val title = args.optString("title", "Share with V.E.D.A.")

        val sendIntent = Intent(Intent.ACTION_SEND).apply {
            putExtra(Intent.EXTRA_TEXT, text)
            type = "text/plain"
        }
        val shareIntent = Intent.createChooser(sendIntent, title).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }

        return try {
            context.startActivity(shareIntent)
            ToolResult(true, "Invoked Android share sheet with text.")
        } catch (e: Exception) {
            ToolResult(false, "Failed to share: ${e.message}")
        }
    }
}
