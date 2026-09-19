package com.veda.assistant.automation

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.veda.assistant.tools.CreateNotificationTool
import org.json.JSONObject

class VedaAutomationWorker(
    private val context: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(context, workerParams) {

    override suspend fun doWork(): Result {
        val taskName = inputData.getString("task_name") ?: "Routine Task"
        val message = inputData.getString("message") ?: "V.E.D.A. background check completed."

        val notifTool = CreateNotificationTool(context)
        notifTool.execute(
            JSONObject().apply {
                put("title", "V.E.D.A. Automation")
                put("message", "$taskName: $message")
            }
        )

        return Result.success()
    }
}
