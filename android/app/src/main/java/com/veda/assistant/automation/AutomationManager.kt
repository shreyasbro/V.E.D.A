package com.veda.assistant.automation

import android.content.Context
import androidx.work.Data
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class AutomationManager(private val context: Context) {

    private val workManager = WorkManager.getInstance(context)

    fun scheduleTask(taskName: String, message: String, delayMinutes: Long) {
        val input = Data.Builder()
            .putString("task_name", taskName)
            .putString("message", message)
            .build()

        val req = OneTimeWorkRequestBuilder<VedaAutomationWorker>()
            .setInitialDelay(delayMinutes, TimeUnit.MINUTES)
            .setInputData(input)
            .addTag("veda_automation")
            .build()

        workManager.enqueue(req)
    }

    fun cancelAllAutomations() {
        workManager.cancelAllWorkByTag("veda_automation")
    }
}
