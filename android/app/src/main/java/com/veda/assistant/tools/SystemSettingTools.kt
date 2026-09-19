package com.veda.assistant.tools

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import androidx.core.app.NotificationCompat
import org.json.JSONObject

class DeviceInfoTool(private val context: Context) : AndroidTool {
    override val name = "device_info"
    override val description = "Retrieves real-time status of the Android phone: battery level, charging status, Android version, manufacturer, and memory."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject())
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val ifilter = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
        val batteryStatus: Intent? = context.registerReceiver(null, ifilter)

        val level: Int = batteryStatus?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale: Int = batteryStatus?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val batteryPct = if (level >= 0 && scale > 0) (level * 100 / scale) else -1

        val status: Int = batteryStatus?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val isCharging: Boolean = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                status == BatteryManager.BATTERY_STATUS_FULL

        val manufacturer = Build.MANUFACTURER
        val model = Build.MODEL
        val androidVersion = Build.VERSION.RELEASE
        val sdkInt = Build.VERSION.SDK_INT

        val report = """
            • Device: $manufacturer $model
            • Android Version: Android $androidVersion (API $sdkInt)
            • Battery: $batteryPct% ${if (isCharging) "(Charging ⚡)" else "(On battery)"}
            • Assistant Architecture: Standalone On-Device Mobile Core
        """.trimIndent()

        return ToolResult(true, report)
    }
}

class CreateNotificationTool(private val context: Context) : AndroidTool {
    override val name = "create_notification"
    override val description = "Creates a local Android notification for reminders, alerts, or task completions."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("title", JSONObject().put("type", "string").put("description", "Notification title"))
            put("message", JSONObject().put("type", "string").put("description", "Notification message body"))
        })
        put("required", org.json.JSONArray().put("title").put("message"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val title = args.optString("title", "V.E.D.A. Assistant")
        val message = args.optString("message", "")

        val channelId = "veda_assistant_alerts"
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
            ?: return ToolResult(false, "NotificationManager unavailable")

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "V.E.D.A. Alerts",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Task alerts and notifications from V.E.D.A."
            }
            nm.createNotificationChannel(channel)
        }

        val notif = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .build()

        val notifId = (System.currentTimeMillis() % 10000).toInt()
        nm.notify(notifId, notif)

        return ToolResult(true, "Created notification: \"$title - $message\"")
    }
}
