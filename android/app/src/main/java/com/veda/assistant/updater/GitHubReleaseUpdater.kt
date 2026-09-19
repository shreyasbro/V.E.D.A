package com.veda.assistant.updater

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.net.Uri
import android.os.Build
import android.os.Environment
import androidx.core.app.NotificationCompat
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
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

data class DownloadProgress(
    val percent: Int,
    val bytesDownloaded: Long,
    val totalBytes: Long,
    val speedMbPerSec: Double
)

class GitHubReleaseUpdater(private val context: Context) {

    val currentVersion: String by lazy {
        try {
            val pInfo = context.packageManager.getPackageInfo(context.packageName, 0)
            pInfo.versionName ?: "1.0.0"
        } catch (e: Exception) {
            "1.0.0"
        }
    }

    val currentVersionCode: Long by lazy {
        try {
            val pInfo = context.packageManager.getPackageInfo(context.packageName, 0)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                pInfo.longVersionCode
            } else {
                @Suppress("DEPRECATION")
                pInfo.versionCode.toLong()
            }
        } catch (e: Exception) {
            100L
        }
    }

    private val prefs: SharedPreferences = context.getSharedPreferences("veda_updater_prefs", Context.MODE_PRIVATE)

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    var autoCheckEnabled: Boolean
        get() = prefs.getBoolean("auto_check_updates", true)
        set(value) = prefs.edit().putBoolean("auto_check_updates", value).apply()

    var autoDownloadEnabled: Boolean
        get() = prefs.getBoolean("auto_download_updates", false)
        set(value) = prefs.edit().putBoolean("auto_download_updates", value).apply()

    private var lastNotifiedVersion: String?
        get() = prefs.getString("last_notified_version", null)
        set(value) = prefs.edit().putString("last_notified_version", value).apply()

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
                    return@withContext Result.failure(Exception("GitHub API returned HTTP ${resp.code}"))
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
                    // Pass 1: Look specifically for the single consistent asset name VEDA-Mobile.apk
                    for (i in 0 until assets.length()) {
                        val a = assets.getJSONObject(i)
                        val name = a.getString("name")
                        val dl = a.getString("browser_download_url")
                        if (name.equals("VEDA-Mobile.apk", ignoreCase = true)) {
                            apkUrl = dl
                            apkName = name
                        } else if (name.equals("VEDA-Mobile.apk.sha256", ignoreCase = true)) {
                            shaUrl = dl
                        }
                    }

                    // Pass 2: Fallback to any other .apk if VEDA-Mobile.apk was not found (backward compatibility)
                    if (apkUrl == null) {
                        for (i in 0 until assets.length()) {
                            val a = assets.getJSONObject(i)
                            val name = a.getString("name")
                            val dl = a.getString("browser_download_url")
                            if (name.endsWith(".apk", ignoreCase = true)) {
                                apkUrl = dl
                                apkName = name
                            } else if (name.contains("apk.sha256", ignoreCase = true) || 
                                       (name.endsWith(".sha256", ignoreCase = true) && name.contains("mobile", ignoreCase = true))) {
                                if (shaUrl == null) shaUrl = dl
                            }
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
                    apkName = apkName ?: "VEDA-Mobile.apk",
                    sha256DownloadUrl = shaUrl
                )

                if (hasUpdate && lastNotifiedVersion != clean) {
                    showUpdateNotification(releaseInfo)
                    lastNotifiedVersion = clean
                }

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

    suspend fun downloadAndVerifyApk(
        release: MobileReleaseInfo,
        onProgress: (DownloadProgress) -> Unit
    ): Result<File> = withContext(Dispatchers.IO) {
        val apkUrl = release.apkDownloadUrl
            ?: return@withContext Result.failure(Exception("No APK asset found in this GitHub Release"))

        val targetDir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: context.filesDir
        val apkFile = File(targetDir, "VEDA-Mobile.apk")
        if (apkFile.exists()) apkFile.delete()

        try {
            // 1. Download APK with real streaming progress
            val apkReq = Request.Builder().url(apkUrl).get().build()
            client.newCall(apkReq).execute().use { resp ->
                if (!resp.isSuccessful) throw Exception("Failed downloading APK (HTTP ${resp.code})")
                val body = resp.body ?: throw Exception("Empty APK response body")
                val totalBytes = body.contentLength()
                val inStream = body.byteStream()
                val outStream = FileOutputStream(apkFile)

                val buffer = ByteArray(8192)
                var bytesDownloaded = 0L
                var read: Int
                var startTime = System.currentTimeMillis()

                while (inStream.read(buffer).also { read = it } != -1) {
                    outStream.write(buffer, 0, read)
                    bytesDownloaded += read

                    val elapsedSec = (System.currentTimeMillis() - startTime) / 1000.0
                    val speed = if (elapsedSec > 0.1) (bytesDownloaded / (1024.0 * 1024.0)) / elapsedSec else 0.0
                    val pct = if (totalBytes > 0) ((bytesDownloaded * 100) / totalBytes).toInt() else 0

                    onProgress(
                        DownloadProgress(
                            percent = pct,
                            bytesDownloaded = bytesDownloaded,
                            totalBytes = totalBytes,
                            speedMbPerSec = speed
                        )
                    )
                }
                outStream.flush()
                outStream.close()
                inStream.close()
            }

            // 2. Fetch expected SHA-256 if available
            var expectedSha: String? = null
            if (!release.sha256DownloadUrl.isNullOrBlank()) {
                val shaReq = Request.Builder().url(release.sha256DownloadUrl).get().build()
                client.newCall(shaReq).execute().use { resp ->
                    if (resp.isSuccessful) {
                        val rawSha = resp.body?.string()?.trim() ?: ""
                        expectedSha = rawSha.split("\\s+".toRegex()).firstOrNull()?.lowercase()
                    }
                }
            }

            // 3. Compute SHA-256
            val actualSha = calculateFileSha256(apkFile).lowercase()

            // 4. Verify match if expectedSha is present
            if (expectedSha != null && expectedSha != actualSha) {
                apkFile.delete()
                return@withContext Result.failure(Exception("SHA-256 verification failed! Expected $expectedSha, got $actualSha"))
            }

            Result.success(apkFile)
        } catch (e: Exception) {
            if (apkFile.exists()) apkFile.delete()
            Result.failure(e)
        }
    }

    private fun calculateFileSha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { isStream ->
            val buffer = ByteArray(8192)
            var bytesRead: Int
            while (isStream.read(buffer).also { bytesRead = it } != -1) {
                digest.update(buffer, 0, bytesRead)
            }
        }
        val bytes = digest.digest()
        return bytes.joinToString("") { "%02x".format(it) }
    }

    fun launchPackageInstaller(apkFile: File): Result<Unit> {
        if (!apkFile.exists()) return Result.failure(Exception("APK file does not exist"))

        // Check Unknown Apps permission on Android 8.0+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (!context.packageManager.canRequestPackageInstalls()) {
                val settingsIntent = Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).apply {
                    data = Uri.parse("package:${context.packageName}")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(settingsIntent)
                return Result.failure(Exception("Please grant 'Install unknown apps' permission for V.E.D.A. in Android Settings, then tap Install again."))
            }
        }

        return try {
            val uri = FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                apkFile
            )

            val installIntent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/vnd.android.package-archive")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(installIntent)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun showUpdateNotification(release: MobileReleaseInfo) {
        val channelId = "veda_updates_channel"
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager ?: return

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "V.E.D.A. Updates",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifications for new V.E.D.A. releases"
            }
            nm.createNotificationChannel(channel)
        }

        val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)?.apply {
            putExtra("navigate_to", "updates")
            addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            1001,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notif = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle("V.E.D.A. Update Available")
            .setContentText("Version v${release.cleanVersion} is available on GitHub.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        nm.notify(2001, notif)
    }
}
