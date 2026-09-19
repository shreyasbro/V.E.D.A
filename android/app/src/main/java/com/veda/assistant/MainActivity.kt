package com.veda.assistant

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.veda.assistant.agent.AgentCore
import com.veda.assistant.camera.CameraManager
import com.veda.assistant.ui.screens.HomeScreen
import com.veda.assistant.ui.screens.PermissionCenterScreen
import com.veda.assistant.ui.screens.SettingsScreen
import com.veda.assistant.ui.theme.*
import com.veda.assistant.voice.KokoroTTSEngine
import com.veda.assistant.voice.VoiceController
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var agentCore: AgentCore
    private lateinit var ttsEngine: KokoroTTSEngine
    private lateinit var voiceController: VoiceController
    private lateinit var cameraManager: CameraManager

    private var micPermissionGranted by mutableStateOf(false)
    private var cameraPermissionGranted by mutableStateOf(false)

    private val micPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        micPermissionGranted = isGranted
    }

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        cameraPermissionGranted = isGranted
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        micPermissionGranted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED

        cameraPermissionGranted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED

        agentCore = AgentCore(this)
        ttsEngine = KokoroTTSEngine(this)
        voiceController = VoiceController(this, ttsEngine)
        cameraManager = CameraManager(this)

        val updater = com.veda.assistant.updater.GitHubReleaseUpdater(this)
        var detectedUpdate by mutableStateOf<com.veda.assistant.updater.MobileReleaseInfo?>(null)
        var isUpdatingNow by mutableStateOf(false)
        var updateDialogMsg by mutableStateOf<String?>(null)

        if (updater.autoCheckEnabled) {
            kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
                try {
                    val result = updater.checkForUpdates()
                    result.getOrNull()?.let { (hasUpdate, rel) ->
                        if (hasUpdate && rel != null) {
                            detectedUpdate = rel
                            if (updater.autoDownloadEnabled) {
                                updater.downloadAndVerifyApk(rel) { /* background download */ }
                            }
                        }
                    }
                } catch (ignored: Exception) {}
            }
        }

        setContent {
            VedaTheme {
                val coroutineScope = rememberCoroutineScope()
                var currentScreen by remember { mutableStateOf("home") }

                // In-app update alert dialog: [View Release] [Update Now] [Later]
                if (detectedUpdate != null) {
                    val rel = detectedUpdate!!
                    AlertDialog(
                        onDismissRequest = { detectedUpdate = null },
                        title = {
                            Text(
                                "V.E.D.A. Mobile update available",
                                fontWeight = FontWeight.Bold,
                                color = VedaCyan
                            )
                        },
                        text = {
                            Column {
                                Text(
                                    "Version v${rel.cleanVersion} is available on GitHub.",
                                    color = TextPrimary,
                                    fontSize = 13.sp
                                )
                                Spacer(modifier = Modifier.height(6.dp))
                                Text(
                                    "Current version: v${updater.currentVersion}",
                                    color = TextMuted,
                                    fontSize = 11.sp
                                )
                                if (updateDialogMsg != null) {
                                    Spacer(modifier = Modifier.height(8.dp))
                                    Text(
                                        updateDialogMsg!!,
                                        color = if (updateDialogMsg!!.startsWith("✕")) Color(0xFFEF4444) else VedaEmerald,
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                }
                            }
                        },
                        confirmButton = {
                            Button(
                                onClick = {
                                    isUpdatingNow = true
                                    updateDialogMsg = "Downloading VEDA-Mobile.apk & verifying SHA-256..."
                                    coroutineScope.launch {
                                        val dlResult = updater.downloadAndVerifyApk(rel) { prog ->
                                            updateDialogMsg = "Downloading: ${prog.percent}% (${String.format("%.1f", prog.speedMbPerSec)} MB/s)"
                                        }
                                        isUpdatingNow = false
                                        dlResult.onSuccess { apkFile ->
                                            updateDialogMsg = "✓ Verified SHA-256! Upgrading V.E.D.A...."
                                            val instResult = updater.launchPackageInstaller(apkFile)
                                            instResult.onFailure {
                                                updateDialogMsg = "✕ ${it.message}"
                                            }
                                        }.onFailure {
                                            updateDialogMsg = "✕ Verification error: ${it.message}"
                                        }
                                    }
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0284c7)),
                                enabled = !isUpdatingNow
                            ) {
                                Text(if (isUpdatingNow) "Updating..." else "Update Now")
                            }
                        },
                        dismissButton = {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                TextButton(
                                    onClick = {
                                        val browserIntent = android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(rel.htmlUrl)).apply {
                                            addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                                        }
                                        startActivity(browserIntent)
                                    }
                                ) {
                                    Text("View Release", color = TextSecondary)
                                }
                                TextButton(
                                    onClick = { detectedUpdate = null },
                                    enabled = !isUpdatingNow
                                ) {
                                    Text("Later", color = TextMuted)
                                }
                            }
                        },
                        containerColor = DarkCard,
                        shape = RoundedCornerShape(12.dp)
                    )
                }

                when (currentScreen) {
                    "home" -> {
                        HomeScreen(
                            agentCore = agentCore,
                            voiceController = voiceController,
                            ttsEngine = ttsEngine,
                            cameraManager = cameraManager,
                            micAllowed = micPermissionGranted,
                            cameraAllowed = cameraPermissionGranted,
                            onRequestMicPermission = {
                                micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                            },
                            onRequestCameraPermission = {
                                cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
                            },
                            onOpenSettings = {
                                currentScreen = "settings"
                            },
                            onOpenPermissions = {
                                currentScreen = "permissions"
                            }
                        )
                    }
                    "settings" -> {
                        SettingsScreen(
                            agentCore = agentCore,
                            onBack = { currentScreen = "home" },
                            onOpenPermissionCenter = { currentScreen = "permissions" }
                        )
                    }
                    "permissions" -> {
                        PermissionCenterScreen(
                            onBack = { currentScreen = "settings" }
                        )
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        voiceController.stopListening()
        ttsEngine.shutdown()
        cameraManager.shutdown()
    }
}
