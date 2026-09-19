package com.veda.assistant.ui.screens

import android.view.ViewGroup
import androidx.camera.view.PreviewView
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.veda.assistant.agent.AgentCore
import com.veda.assistant.camera.CameraManager
import com.veda.assistant.data.model.ChatMessage
import com.veda.assistant.ui.theme.*
import com.veda.assistant.voice.KokoroTTSEngine
import com.veda.assistant.voice.MicState
import com.veda.assistant.voice.VoiceController
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

@Composable
fun HomeScreen(
    agentCore: AgentCore,
    voiceController: VoiceController,
    ttsEngine: KokoroTTSEngine,
    cameraManager: CameraManager,
    micAllowed: Boolean,
    cameraAllowed: Boolean,
    onRequestMicPermission: () -> Unit,
    onRequestCameraPermission: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenPermissions: () -> Unit
) {
    val coroutineScope = rememberCoroutineScope()
    val listState = rememberLazyListState()
    val clipboardManager = LocalClipboardManager.current
    val lifecycleOwner = LocalLifecycleOwner.current

    val messages = remember { mutableStateListOf<ChatMessage>() }
    var inputText by remember { mutableStateOf("") }
    var isStreaming by remember { mutableStateOf(false) }
    var streamJob by remember { mutableStateOf<Job?>(null) }
    var interimTranscript by remember { mutableStateOf("") }

    val micState by voiceController.micState.collectAsState()
    val micRms by voiceController.micRms.collectAsState()
    var isCameraActive by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        messages.add(
            ChatMessage(
                sender = "assistant",
                content = "Hello! Main V.E.D.A. hoon — Standalone Native Mobile Assistant.\n" +
                        "Running entirely on this Android phone with genuine tool execution, Kokoro TTS, and Keystore encryption.\n\n" +
                        "Try asking me in Hindi, Hinglish, or English:\n" +
                        "• \"Open WhatsApp\"\n" +
                        "• \"Check battery status\"\n" +
                        "• \"Copy 'Hello VEDA' to clipboard\"\n" +
                        "• \"Find files in downloads\"",
                provider = "V.E.D.A. Mobile"
            )
        )

        voiceController.onFinalSpeech = { speech ->
            inputText = speech
            interimTranscript = ""
            // Auto send speech
            if (speech.isNotBlank()) {
                coroutineScope.launch {
                    val userMsg = ChatMessage(sender = "user", content = speech)
                    messages.add(userMsg)
                    inputText = ""
                    listState.animateScrollToItem(messages.size - 1)

                    isStreaming = true
                    val assistantMsg = ChatMessage(
                        sender = "assistant",
                        content = "",
                        provider = agentCore.providerManager.getActiveProvider()?.name ?: "V.E.D.A.",
                        isStreaming = true
                    )
                    messages.add(assistantMsg)
                    val assistantIndex = messages.size - 1

                    streamJob = launch {
                        agentCore.processUserMessageStream(
                            userText = speech,
                            onToolActionStart = {},
                            onToolActionComplete = { _, _ -> }
                        ).collectLatest { chunk ->
                            val current = messages[assistantIndex]
                            messages[assistantIndex] = current.copy(content = current.content + chunk)
                            listState.animateScrollToItem(messages.size - 1)
                        }
                        messages[assistantIndex] = messages[assistantIndex].copy(isStreaming = false)
                        isStreaming = false
                        ttsEngine.speak(messages[assistantIndex].content)
                    }
                }
            }
        }

        voiceController.onInterimSpeech = { interim ->
            interimTranscript = interim
        }
    }

    fun handleSend(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty() || isStreaming) return

        ttsEngine.stop()
        inputText = ""
        messages.add(ChatMessage(sender = "user", content = trimmed))

        coroutineScope.launch {
            listState.animateScrollToItem(messages.size - 1)
            isStreaming = true

            val assistantMsg = ChatMessage(
                sender = "assistant",
                content = "",
                provider = agentCore.providerManager.getActiveProvider()?.name ?: "V.E.D.A.",
                isStreaming = true
            )
            messages.add(assistantMsg)
            val assistantIndex = messages.size - 1

            streamJob = launch {
                agentCore.processUserMessageStream(trimmed).collectLatest { chunk ->
                    val current = messages[assistantIndex]
                    messages[assistantIndex] = current.copy(content = current.content + chunk)
                    listState.animateScrollToItem(messages.size - 1)
                }
                messages[assistantIndex] = messages[assistantIndex].copy(isStreaming = false)
                isStreaming = false
                ttsEngine.speak(messages[assistantIndex].content)
            }
        }
    }

    Scaffold(
        topBar = {
            Surface(color = DarkSurface, shadowElevation = 4.dp) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .statusBarsPadding()
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = "◈",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            color = VedaCyan
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = "V.E.D.A.",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            color = VedaCyan,
                            fontFamily = FontFamily.Monospace
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = "Mobile",
                            fontSize = 11.sp,
                            color = TextSecondary,
                            fontFamily = FontFamily.Monospace
                        )
                    }

                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Provider Pill
                        val activeProv = agentCore.providerManager.getActiveProvider()
                        Surface(
                            shape = CircleShape,
                            color = if (activeProv != null) Color(0xFF065f46) else Color(0xFF1e293b),
                            modifier = Modifier.clickable { onOpenSettings() }
                        ) {
                            Text(
                                text = "◆ " + (activeProv?.name ?: "No Provider"),
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (activeProv != null) Color(0xFF34d399) else Color(0xFF94a3b8),
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                            )
                        }

                        // Camera Toggle
                        IconButton(
                            onClick = {
                                if (!cameraAllowed) {
                                    onRequestCameraPermission()
                                } else {
                                    isCameraActive = !isCameraActive
                                }
                            },
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(
                                Icons.Default.CameraAlt,
                                contentDescription = "Camera",
                                tint = if (isCameraActive) VedaCyan else TextMuted
                            )
                        }

                        // Settings Icon
                        IconButton(
                            onClick = onOpenSettings,
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(Icons.Default.Settings, contentDescription = "Settings", tint = TextSecondary)
                        }
                    }
                }
            }
        },
        containerColor = DarkBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            // Camera Preview Box if active
            AnimatedVisibility(visible = isCameraActive && cameraAllowed) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(180.dp)
                        .background(Color.Black)
                ) {
                    AndroidView(
                        factory = { ctx ->
                            PreviewView(ctx).apply {
                                layoutParams = ViewGroup.LayoutParams(
                                    ViewGroup.LayoutParams.MATCH_PARENT,
                                    ViewGroup.LayoutParams.MATCH_PARENT
                                )
                                cameraManager.startCamera(
                                    lifecycleOwner = lifecycleOwner,
                                    surfaceProvider = surfaceProvider
                                )
                            }
                        },
                        modifier = Modifier.fillMaxSize()
                    )
                }
            }

            // Message List
            LazyColumn(
                state = listState,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 6.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(messages, key = { it.id }) { msg ->
                    val isUser = msg.sender == "user"
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
                    ) {
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = if (isUser) Color(0xFF0369a1) else DarkCard,
                            border = if (!isUser) androidx.compose.foundation.BorderStroke(1.dp, DarkBorder) else null,
                            modifier = Modifier.widthIn(max = 320.dp)
                        ) {
                            Column(modifier = Modifier.padding(10.dp)) {
                                if (!isUser) {
                                    Row(
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        modifier = Modifier.fillMaxWidth()
                                    ) {
                                        Text(
                                            "◈ " + msg.provider,
                                            fontSize = 9.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = VedaCyan
                                        )
                                        Icon(
                                            Icons.Default.ContentCopy,
                                            contentDescription = "Copy",
                                            tint = TextMuted,
                                            modifier = Modifier
                                                .size(14.dp)
                                                .clickable {
                                                    clipboardManager.setText(AnnotatedString(msg.content))
                                                }
                                        )
                                    }
                                    Spacer(modifier = Modifier.height(4.dp))
                                }
                                Text(
                                    text = msg.content,
                                    color = TextPrimary,
                                    fontSize = 13.sp,
                                    lineHeight = 18.sp
                                )
                            }
                        }
                    }
                }
            }

            // Waveform & Mic State Indicator Bar
            Surface(color = DarkSurface, modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 14.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        val stateColor = Color(android.graphics.Color.parseColor(micState.colorHex))
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(CircleShape)
                                .background(stateColor)
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = micState.label,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold,
                            color = stateColor,
                            fontFamily = FontFamily.Monospace
                        )
                        if (interimTranscript.isNotEmpty()) {
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = "\"$interimTranscript\"",
                                fontSize = 10.sp,
                                color = TextSecondary,
                                maxLines = 1
                            )
                        }
                    }

                    // Genuine Hardware RMS level bar
                    LinearProgressIndicator(
                        progress = { micRms },
                        modifier = Modifier
                            .width(80.dp)
                            .height(6.dp)
                            .clip(RoundedCornerShape(3.dp)),
                        color = VedaCyan,
                        trackColor = Color(0xFF1e293b)
                    )
                }
            }

            // Bottom Input Dock
            Surface(
                color = DarkCard,
                modifier = Modifier
                    .fillMaxWidth()
                    .imePadding()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 10.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Voice Mic Button
                    IconButton(
                        onClick = {
                            if (!micAllowed) {
                                onRequestMicPermission()
                            } else {
                                voiceController.toggleListening()
                            }
                        },
                        modifier = Modifier
                            .size(42.dp)
                            .clip(CircleShape)
                            .background(if (micState == MicState.HEARING) VedaCyan else Color(0xFF1e293b))
                    ) {
                        Icon(
                            Icons.Default.Mic,
                            contentDescription = "Microphone",
                            tint = if (micState == MicState.HEARING) DarkBackground else Color.White
                        )
                    }

                    Spacer(modifier = Modifier.width(8.dp))

                    OutlinedTextField(
                        value = inputText,
                        onValueChange = { inputText = it },
                        placeholder = { Text("Ask V.E.D.A. on Android...", fontSize = 13.sp, color = TextMuted) },
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = 44.dp),
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = VedaCyan,
                            unfocusedBorderColor = DarkBorder,
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary
                        ),
                        textStyle = LocalTextStyle.current.copy(fontSize = 13.sp)
                    )

                    Spacer(modifier = Modifier.width(8.dp))

                    if (isStreaming) {
                        IconButton(
                            onClick = {
                                streamJob?.cancel()
                                ttsEngine.stop()
                                isStreaming = false
                            },
                            modifier = Modifier
                                .size(42.dp)
                                .clip(CircleShape)
                                .background(Color(0xFF991b1b))
                        ) {
                            Icon(Icons.Default.Stop, contentDescription = "Stop", tint = Color.White)
                        }
                    } else {
                        IconButton(
                            onClick = { handleSend(inputText) },
                            modifier = Modifier
                                .size(42.dp)
                                .clip(CircleShape)
                                .background(Color(0xFF0284c7))
                        ) {
                            Icon(Icons.Default.Send, contentDescription = "Send", tint = Color.White)
                        }
                    }
                }
            }
        }
    }
}
