package com.veda.assistant

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.core.content.ContextCompat
import com.veda.assistant.agent.AgentCore
import com.veda.assistant.camera.CameraManager
import com.veda.assistant.ui.screens.HomeScreen
import com.veda.assistant.ui.screens.PermissionCenterScreen
import com.veda.assistant.ui.screens.SettingsScreen
import com.veda.assistant.ui.theme.VedaTheme
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

        // Background OTA check if enabled
        val updater = com.veda.assistant.updater.GitHubReleaseUpdater(this)
        if (updater.autoCheckEnabled) {
            kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
                try {
                    val result = updater.checkForUpdates()
                    result.getOrNull()?.let { (hasUpdate, rel) ->
                        if (hasUpdate && rel != null && updater.autoDownloadEnabled) {
                            updater.downloadAndVerifyApk(rel) { /* background download */ }
                        }
                    }
                } catch (ignored: Exception) {}
            }
        }

        setContent {
            VedaTheme {
                var currentScreen by remember { mutableStateOf("home") }

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
