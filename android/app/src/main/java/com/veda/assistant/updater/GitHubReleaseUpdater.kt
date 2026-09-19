package com.veda.assistant.updater

import android.app.DownloadManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Build
import android.os.Environment
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

data class MobileReleaseInfo(
    val tagName: String,
    val cleanVersion: String,
    val releaseNotes: String,
    val publishedAt: String,
    val htmlUrl: String,
    val apkDownloadUrl: String?,
    val apkName: String?,
    val sha256DownloadUrl: String?
)

class GitHubReleaseUpdater(private val context: Context) {

    private val currentVersion = "1.0.0"
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    suspend fun checkForUpdates(): Result<Pair<Boolean, MobileReleaseInfo?>> = withContext(Dispatchers.IO) {
        try {
            val url = "https://api.github.com/repos/shreyasbro/V.E.D.A/releases/latest"
            val req = Request.Builder()
                .url(url)
                .addHeader("User-Agent", "VEDA-Android-App/$currentVersion")
                .addHeader("Accept", "application/vnd.github.v3+json")
                .get()
                .build()

            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) {
                    return@withContext Result.failure(Exception("GitHub API error HTTP ${resp.code}"))
                }

                val json = JSONObject(resp.body?.string() ?: "{}")
                val tag = json.optString("tag_name", "")
                val clean = tag.trim().trimStart('v', 'V')
                val body = json.optString("body", "")
                val pubAt = json.optString("published_at", "")
                val htmlUrl = json.optString("html_url", "https://github.com/shreyasbro/V.E.D.A/releases")

                val assets = json.optJSONArray("assets")
                var apkUrl: String? = null
                var apkName: String? = null
                var shaUrl: String? = null

                if (assets != null) {
                    for (i in 0 until assets.length()) {
                        val a = assets.getJSONObject(i)
                        val name = a.getString("name")
                        val dl = a.getString("browser_download_url")
                        if (name.endsWith(".apk", ignoreCase = true)) {
                            apkUrl = dl
                            apkName = name
                        } else if (name.contains("sha256", ignoreCase = true)) {
                            shaUrl = dl
                        }
                    }
                }

                val hasUpdate = isNewerVersion(clean, currentVersion)
                val releaseInfo = MobileReleaseInfo(
                    tagName = tag,
                    cleanVersion = clean,
                    releaseNotes = body,
                    publishedAt = pubAt,
                    htmlUrl = htmlUrl,
                    apkDownloadUrl = apkUrl,
                    apkName = apkName,
                    sha256DownloadUrl = shaUrl
                )

                Result.success(Pair(hasUpdate, releaseInfo))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun isNewerVersion(remote: String, current: String): Boolean {
        try {
            val rParts = remote.split('.').map { it.toIntOrNull() ?: 0 }
            val cParts = current.split('.').map { it.toIntOrNull() ?: 0 }
            for (i in 0 until maxOf(rParts.size, cParts.size)) {
                val r = rParts.getOrElse(i) { 0 }
                val c = cParts.getOrElse(i) { 0 }
                if (r > c) return true
                if (r < c) return false
            }
        } catch (ignored: Exception) {}
        return false
    }

    fun triggerApkDownloadAndInstall(release: MobileReleaseInfo) {
        val apkUrl = release.apkDownloadUrl ?: return
        val filename = release.apkName ?: "VEDA-Android-Update.apk"

        val dm = context.getSystemService(Context.DOWNLOAD_SERVICE) as? DownloadManager ?: return
        val uri = Uri.parse(apkUrl)

        val request = DownloadManager.Request(uri).apply {
            setTitle("Downloading V.E.D.A. v${release.cleanVersion}")
            setDescription("Fetching update package from GitHub Releases")
            setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)
        }

        val downloadId = dm.enqueue(request)

        // Register receiver for install when download is complete
        val onComplete = object : BroadcastReceiver() {
            override fun onReceive(ctxt: Context, intent: Intent) {
                val id = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1)
                if (id == downloadId) {
                    try {
                        ctxt.unregisterReceiver(this)
                    } catch (ignored: Exception) {}
                    installApk(filename)
                }
            }
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            context.registerReceiver(
                onComplete,
                IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE),
                Context.RECEIVER_NOT_EXPORTED
            )
        } else {
            context.registerReceiver(onComplete, IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE))
        }
    }

    fun installApk(filename: String) {
        val file = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), filename)
        if (!file.exists()) return

        val uri = FileProvider.getUriForFile(context, context.packageName + ".fileprovider", file)
        val installIntent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(installIntent)
    }
}
