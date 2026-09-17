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
import com.veda.assistant.camera.CameraManager
import com.veda.assistant.data.api.VedaApiClient
import com.veda.assistant.data.model.ChatMessage
import com.veda.assistant.data.model.ServerStatus
import com.veda.assistant.ui.theme.*
import com.veda.assistant.voice.TtsManager
import com.veda.assistant.voice.VoiceManager
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

@Composable
fun HomeScreen(
    apiClient: VedaApiClient,
    voiceManager: VoiceManager,
    ttsManager: TtsManager,
    cameraManager: CameraManager,
    micAllowed: Boolean,
    cameraAllowed: Boolean,
    onRequestMicPermission: () -> Unit,
    onRequestCameraPermission: () -> Unit,
    onOpenSettings: () -> Unit
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

    var serverStatus by remember {
        mutableStateOf(
            ServerStatus(
                status = "offline",
                activeProvider = "Checking...",
                providerMode = "AUTO",
                selectedProvider = "GEMINI",
                desktopConnected = false,
                pairingPin = ""
            )
        )
    }

    var isCameraActive by remember { mutableStateOf(false) }
    val micLevel by voiceManager.micLevel.collectAsState()

    // Status poll loop
    LaunchedEffect(Unit) {
        // Welcome message
        messages.add(
            ChatMessage(
                sender = "assistant",
                content = "Hello! Main V.E.D.A. hoon (Virtual Executive Desktop Assistant).\nMobile edition ready. Ask me anything or speak naturally in Hindi, Hinglish, or English.",
                provider = "V.E.D.A. Mobile"
            )
        )

        while (true) {
            val res = apiClient.fetchStatus()
            res.onSuccess { serverStatus = it }
            kotlinx.coroutines.delay(5000)
        }
    }

    // Voice manager bindings
    DisposableEffect(Unit) {
        voiceManager.onTranscriptReceived = { text, isFinal ->
            if (isFinal) {
                interimTranscript = ""
                inputText = text
            } else {
                interimTranscript = text
            }
        }
        onDispose {
            voiceManager.stopListening()
        }
    }

    fun sendMessage(userText: String) {
        if (userText.isBlank() || isStreaming) return

        val trimmed = userText.trim()
        inputText = ""
        interimTranscript = ""

        messages.add(ChatMessage(sender = "user", content = trimmed))
        val assistantMsg = ChatMessage(
            sender = "assistant",
            content = "",
            isStreaming = true,
            provider = serverStatus.activeProvider
        )
        messages.add(assistantMsg)
        val assistantIdx = messages.lastIndex
        isStreaming = true

        streamJob?.cancel()
        streamJob = coroutineScope.launch {
            val historyPairs = messages.dropLast(2).map { Pair(it.sender, it.content) }
            val accumulated = StringBuilder()

            try {
                apiClient.streamChat(trimmed, historyPairs).collectLatest { (chunk, prov) ->
                    accumulated.append(chunk)
                    messages[assistantIdx] = messages[assistantIdx].copy(
                        content = accumulated.toString(),
                        provider = prov,
                        isStreaming = true
                    )
                    listState.animateScrollToItem(messages.lastIndex)
                }
            } catch (e: Exception) {
                accumulated.append("\n[Connection fallback: using offline response]")
            } finally {
                val finalContent = accumulated.toString().ifBlank { "Received response." }
                messages[assistantIdx] = messages[assistantIdx].copy(
                    content = finalContent,
                    isStreaming = false
                )
                isStreaming = false
                // Auto-speak response if mic was used
                val isHindi = finalContent.any { it in '\u0900'..'\u097F' }
                ttsManager.speak(finalContent, isHindi)
            }
        }
    }

    fun handleVisualQuery(promptText: String) {
        if (!isCameraActive) return
        cameraManager.captureFrameBase64(
            onCaptured = { base64 ->
                coroutineScope.launch {
                    messages.add(ChatMessage(sender = "user", content = "[Camera Query] " + promptText))
                    val assistantMsg = ChatMessage(sender = "assistant", content = "Analyzing camera frame...", isStreaming = true)
                    messages.add(assistantMsg)
                    val idx = messages.lastIndex

                    val res = apiClient.analyzeImage(base64, promptText)
                    res.onSuccess { ans ->
                        messages[idx] = messages[idx].copy(content = ans, isStreaming = false)
                        ttsManager.speak(ans)
                    }.onFailure { err ->
                        messages[idx] = messages[idx].copy(content = "Camera analysis error: " + err.message, isStreaming = false)
                    }
                }
            },
            onError = { err ->
                messages.add(ChatMessage(sender = "assistant", content = "Failed to capture camera frame: " + err.message))
            }
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(DarkBackground)
    ) {
        // 1. TOP HEADER & BRANDING
        Surface(
            color = DarkSurface,
            modifier = Modifier.fillMaxWidth(),
            shadowElevation = 4.dp
        ) {
            Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            "V.E.D.A.",
                            color = VedaCyan,
                            fontSize = 20.sp,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            "| " + serverStatus.activeProvider.uppercase(),
                            color = TextSecondary,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            fontFamily = FontFamily.Monospace
                        )
                    }

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        // Online / Offline Status Badge
                        val isOnline = serverStatus.status == "online"
                        Box(
                            modifier = Modifier
                                .background(
                                    if (isOnline) VedaEmerald.copy(alpha = 0.2f) else VedaAmber.copy(alpha = 0.2f),
                                    RoundedCornerShape(12.dp)
                                )
                                .border(
                                    1.dp,
                                    if (isOnline) VedaEmerald else VedaAmber,
                                    RoundedCornerShape(12.dp)
                                )
                                .padding(horizontal = 8.dp, vertical = 4.dp)
                        ) {
                            Text(
                                if (isOnline) "● ONLINE" else "○ LOCAL/OFFLINE",
                                color = if (isOnline) VedaEmerald else VedaAmber,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace
                            )
                        }

                        Spacer(modifier = Modifier.width(8.dp))

                        IconButton(onClick = onOpenSettings) {
                            Icon(Icons.Default.Settings, contentDescription = "Settings", tint = TextSecondary)
                        }
                    }
                }

                // Sub-header status pills: Mic & Camera
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    StatusChip(
                        label = "MIC",
                        isActive = voiceManager.isListening(),
                        activeColor = VedaRed
                    )
                    StatusChip(
                        label = "CAM",
                        isActive = isCameraActive,
                        activeColor = VedaCyan
                    )
                    if (serverStatus.desktopConnected) {
                        StatusChip(
                            label = "DESKTOP PAIRED",
                            isActive = true,
                            activeColor = VedaEmerald
                        )
                    }
                }
            }
        }

        // 2. OPTIONAL CAMERA PREVIEW OVERLAY
        AnimatedVisibility(visible = isCameraActive) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(200.dp)
                    .background(Color.Black)
            ) {
                AndroidView(
                    factory = { ctx ->
                        val previewView = PreviewView(ctx).apply {
                            layoutParams = ViewGroup.LayoutParams(
                                ViewGroup.LayoutParams.MATCH_PARENT,
                                ViewGroup.LayoutParams.MATCH_PARENT
                            )
                        }
                        cameraManager.startCamera(
                            lifecycleOwner = lifecycleOwner,
                            surfaceProvider = previewView.surfaceProvider
                        )
                        previewView
                    },
                    modifier = Modifier.fillMaxSize()
                )

                // Capture Frame button
                Button(
                    onClick = { handleVisualQuery(inputText.ifBlank { "Describe what is visible in front of the camera" }) },
                    colors = ButtonDefaults.buttonColors(containerColor = VedaCyan),
                    modifier = Modifier
                        .align(Alignment.BottomEnd)
                        .padding(12.dp),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Icon(Icons.Default.PhotoCamera, contentDescription = null, tint = Color.Black)
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Analyze Frame", color = Color.Black, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                }
            }
        }

        // 3. CHAT STREAM / MESSAGE LIST
        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(horizontal = 12.dp),
            contentPadding = PaddingValues(vertical = 8.dp)
        ) {
            items(messages) { msg ->
                val isUser = msg.sender == "user"
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp),
                    horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
                ) {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = if (isUser) VedaCyan.copy(alpha = 0.15f) else DarkCard
                        ),
                        border = if (isUser) androidx.compose.foundation.BorderStroke(1.dp, VedaCyan.copy(alpha = 0.4f)) else null,
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.widthIn(max = 320.dp)
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            if (!isUser) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        "V.E.D.A. • " + msg.provider,
                                        fontSize = 11.sp,
                                        color = VedaCyan,
                                        fontWeight = FontWeight.Bold,
                                        fontFamily = FontFamily.Monospace
                                    )
                                    Row {
                                        IconButton(
                                            onClick = { clipboardManager.setText(AnnotatedString(msg.content)) },
                                            modifier = Modifier.size(24.dp)
                                        ) {
                                            Icon(Icons.Default.ContentCopy, contentDescription = "Copy", tint = TextMuted, modifier = Modifier.size(14.dp))
                                        }
                                        IconButton(
                                            onClick = { ttsManager.speak(msg.content) },
                                            modifier = Modifier.size(24.dp)
                                        ) {
                                            Icon(Icons.Default.VolumeUp, contentDescription = "Speak", tint = TextMuted, modifier = Modifier.size(14.dp))
                                        }
                                    }
                                }
                                Spacer(modifier = Modifier.height(4.dp))
                            }
                            Text(
                                msg.content,
                                color = TextPrimary,
                                fontSize = 14.sp,
                                lineHeight = 20.sp
                            )
                        }
                    }
                }
            }
        }

        // Interim voice speech indicator
        if (interimTranscript.isNotBlank()) {
            Text(
                "Hearing: " + interimTranscript,
                color = VedaCyan,
                fontSize = 12.sp,
                modifier = Modifier
                    .fillMaxWidth()
                    .background(DarkCard)
                    .padding(horizontal = 16.dp, vertical = 6.dp)
            )
        }

        // Live Audio Amplitude RMS Meter Bar
        if (voiceManager.isListening()) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(DarkSurface)
                    .padding(horizontal = 16.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("MIC LEVEL", color = VedaRed, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.width(8.dp))
                LinearProgressIndicator(
                    progress = { micLevel },
                    modifier = Modifier
                        .weight(1f)
                        .height(4.dp)
                        .clip(RoundedCornerShape(2.dp)),
                    color = VedaRed,
                    trackColor = BorderDark
                )
            }
        }

        // 4. INPUT DOCK (TEXT + VOICE + CAMERA TOGGLES)
        Surface(
            color = DarkSurface,
            modifier = Modifier.fillMaxWidth(),
            shadowElevation = 8.dp
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Camera Toggle
                IconButton(
                    onClick = {
                        if (!cameraAllowed) {
                            onRequestCameraPermission()
                        } else {
                            isCameraActive = !isCameraActive
                            if (!isCameraActive) {
                                cameraManager.stopCamera(lifecycleOwner)
                            }
                        }
                    }
                ) {
                    Icon(
                        if (isCameraActive) Icons.Default.VideocamOff else Icons.Default.Videocam,
                        contentDescription = "Camera",
                        tint = if (isCameraActive) VedaCyan else TextSecondary
                    )
                }

                // Text Input Field
                OutlinedTextField(
                    value = inputText,
                    onValueChange = { inputText = it },
                    placeholder = { Text("Ask V.E.D.A. or command...", color = TextMuted, fontSize = 13.sp) },
                    modifier = Modifier
                        .weight(1f)
                        .padding(horizontal = 4.dp),
                    shape = RoundedCornerShape(24.dp),
                    maxLines = 3,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = VedaCyan,
                        unfocusedBorderColor = BorderDark,
                        focusedTextColor = TextPrimary,
                        unfocusedTextColor = TextPrimary,
                        focusedContainerColor = DarkCard,
                        unfocusedContainerColor = DarkCard
                    )
                )

                // Voice Recording Toggle
                IconButton(
                    onClick = {
                        if (!micAllowed) {
                            onRequestMicPermission()
                        } else {
                            if (voiceManager.isListening()) {
                                voiceManager.stopListening()
                            } else {
                                ttsManager.stop()
                                voiceManager.startListening()
                            }
                        }
                    }
                ) {
                    Icon(
                        if (voiceManager.isListening()) Icons.Default.MicOff else Icons.Default.Mic,
                        contentDescription = "Voice",
                        tint = if (voiceManager.isListening()) VedaRed else VedaCyan
                    )
                }

                // Send or Stop Button
                if (isStreaming) {
                    IconButton(
                        onClick = {
                            streamJob?.cancel()
                            isStreaming = false
                        }
                    ) {
                        Icon(Icons.Default.Stop, contentDescription = "Stop", tint = VedaAmber)
                    }
                } else {
                    IconButton(
                        onClick = { sendMessage(inputText) }
                    ) {
                        Icon(Icons.Default.Send, contentDescription = "Send", tint = VedaCyan)
                    }
                }
            }
        }
    }
}

@Composable
fun StatusChip(label: String, isActive: Boolean, activeColor: Color) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .background(DarkCard, RoundedCornerShape(8.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    ) {
        Box(
            modifier = Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(if (isActive) activeColor else TextMuted)
        )
        Spacer(modifier = Modifier.width(4.dp))
        Text(
            label,
            color = if (isActive) TextPrimary else TextMuted,
            fontSize = 9.sp,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace
        )
    }
}
