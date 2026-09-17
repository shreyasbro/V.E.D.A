package com.veda.assistant

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.core.content.ContextCompat
import com.veda.assistant.camera.CameraManager
import com.veda.assistant.data.api.VedaApiClient
import com.veda.assistant.ui.screens.HomeScreen
import com.veda.assistant.ui.screens.SettingsScreen
import com.veda.assistant.ui.theme.VedaTheme
import com.veda.assistant.voice.TtsManager
import com.veda.assistant.voice.VoiceManager

class MainActivity : ComponentActivity() {

    private lateinit var apiClient: VedaApiClient
    private lateinit var voiceManager: VoiceManager
    private lateinit var ttsManager: TtsManager
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

        apiClient = VedaApiClient()
        voiceManager = VoiceManager(this)
        ttsManager = TtsManager(this)
        cameraManager = CameraManager(this)

        setContent {
            VedaTheme {
                var currentScreen by remember { mutableStateOf("home") }

                if (currentScreen == "home") {
                    HomeScreen(
                        apiClient = apiClient,
                        voiceManager = voiceManager,
                        ttsManager = ttsManager,
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
                        }
                    )
                } else {
                    SettingsScreen(
                        apiClient = apiClient,
                        micAllowed = micPermissionGranted,
                        cameraAllowed = cameraPermissionGranted,
                        onBack = {
                            currentScreen = "home"
                        }
                    )
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        voiceManager.stopListening()
        ttsManager.shutdown()
        cameraManager.shutdown()
    }
}
