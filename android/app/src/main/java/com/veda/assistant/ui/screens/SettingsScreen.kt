package com.veda.assistant.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.veda.assistant.data.api.VedaApiClient
import com.veda.assistant.data.model.ProviderSlot
import com.veda.assistant.ui.theme.*
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    apiClient: VedaApiClient,
    micAllowed: Boolean,
    cameraAllowed: Boolean,
    onBack: () -> Unit
) {
    val coroutineScope = rememberCoroutineScope()
    var serverUrl by remember { mutableStateOf(apiClient.getBaseUrl()) }
    var slots by remember { mutableStateOf<List<ProviderSlot>>(emptyList()) }
    var isLoadingProviders by remember { mutableStateOf(false) }
    var selectedSection by remember { mutableStateOf("AI Providers") }

    val sections = listOf(
        "General", "AI Providers", "Voice & Mic", "Camera", "Permissions",
        "Appearance", "Notifications", "Privacy & Data", "About"
    )

    fun refreshProviders() {
        coroutineScope.launch {
            isLoadingProviders = true
            val res = apiClient.fetchProviders()
            slots = res.getOrDefault(emptyList())
            isLoadingProviders = false
        }
    }

    LaunchedEffect(Unit) {
        refreshProviders()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text("V.E.D.A. Settings", fontWeight = FontWeight.Bold, color = TextPrimary)
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = VedaCyan)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = DarkSurface)
            )
        },
        containerColor = DarkBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            ScrollableTabRow(
                selectedTabIndex = sections.indexOf(selectedSection).coerceAtLeast(0),
                containerColor = DarkSurface,
                contentColor = VedaCyan,
                edgePadding = 12.dp
            ) {
                sections.forEach { section ->
                    Tab(
                        selected = selectedSection == section,
                        onClick = { selectedSection = section },
                        text = {
                            Text(
                                section,
                                fontSize = 13.sp,
                                color = if (selectedSection == section) VedaCyan else TextSecondary
                            )
                        }
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 16.dp)
            ) {
                when (selectedSection) {
                    "General" -> {
                        Column {
                            Text("V.E.D.A. Backend Connection", fontWeight = FontWeight.Bold, color = TextPrimary)
                            Spacer(modifier = Modifier.height(8.dp))
                            OutlinedTextField(
                                value = serverUrl,
                                onValueChange = {
                                    serverUrl = it
                                    apiClient.updateBaseUrl(it)
                                },
                                label = { Text("Server API URL", color = TextSecondary) },
                                modifier = Modifier.fillMaxWidth(),
                                colors = OutlinedTextFieldDefaults.colors(
                                    focusedBorderColor = VedaCyan,
                                    unfocusedBorderColor = BorderDark,
                                    focusedTextColor = TextPrimary,
                                    unfocusedTextColor = TextPrimary
                                )
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                "Default emulator loopback: http://10.0.2.2:8765\nLocal Wi-Fi PC IP: e.g. http://192.168.1.100:8765",
                                color = TextMuted,
                                fontSize = 12.sp
                            )
                        }
                    }

                    "AI Providers" -> {
                        Column {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text("Multi-Slot AI Providers", fontWeight = FontWeight.Bold, color = TextPrimary)
                                IconButton(onClick = { refreshProviders() }) {
                                    Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = VedaCyan)
                                }
                            }

                            if (isLoadingProviders) {
                                LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = VedaCyan)
                            }

                            LazyColumn(modifier = Modifier.fillMaxSize()) {
                                items(slots) { slot ->
                                    Card(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(vertical = 4.dp),
                                        colors = CardDefaults.cardColors(containerColor = DarkCard),
                                        shape = RoundedCornerShape(8.dp)
                                    ) {
                                        Column(modifier = Modifier.padding(12.dp)) {
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.SpaceBetween
                                            ) {
                                                Text("Slot " + slot.id + ": " + slot.name, fontWeight = FontWeight.Bold, color = VedaCyan)
                                                Text(
                                                    slot.status,
                                                    fontWeight = FontWeight.SemiBold,
                                                    fontSize = 12.sp,
                                                    color = if (slot.status == "READY") VedaEmerald else VedaAmber
                                                )
                                            }
                                            Spacer(modifier = Modifier.height(4.dp))
                                            Text("Model: " + slot.model, color = TextSecondary, fontSize = 12.sp)
                                            val latText = if (slot.lastLatencyMs != null) "" + slot.lastLatencyMs + " ms" else "--"
                                            Text("Latency: " + latText, color = TextMuted, fontSize = 11.sp)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    "Permissions" -> {
                        Column {
                            Text("System Permissions Status", fontWeight = FontWeight.Bold, color = TextPrimary)
                            Spacer(modifier = Modifier.height(16.dp))

                            PermissionStatusRow("Microphone Access", micAllowed)
                            PermissionStatusRow("Camera Access", cameraAllowed)
                            PermissionStatusRow("Internet & Network", true)
                        }
                    }

                    "Voice & Mic" -> {
                        Column {
                            Text("Voice & Audio Settings", fontWeight = FontWeight.Bold, color = TextPrimary)
                            Spacer(modifier = Modifier.height(12.dp))
                            Text("• Multilingual STT: Hindi (hi-IN), Hinglish (en-IN), English (en-US)", color = TextSecondary, fontSize = 14.sp)
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("• TTS Engine: Native Indian-accented speech with instant barge-in interruption", color = TextSecondary, fontSize = 14.sp)
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("• Microphone Metering: Real PCM amplitude RMS analyzer", color = TextSecondary, fontSize = 14.sp)
                        }
                    }

                    "Camera" -> {
                        Column {
                            Text("Camera Perception Settings", fontWeight = FontWeight.Bold, color = TextPrimary)
                            Spacer(modifier = Modifier.height(12.dp))
                            Text("• CameraX Hardware Pipeline: Direct frame acquisition in RAM", color = TextSecondary, fontSize = 14.sp)
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("• Privacy Guarantee: Strictly zero continuous disk storage", color = TextSecondary, fontSize = 14.sp)
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("• Vision AI: Multimodal frame analysis via Gemini & local vision fallback", color = TextSecondary, fontSize = 14.sp)
                        }
                    }

                    "Appearance" -> {
                        Column {
                            Text("Theme & Visual Style", fontWeight = FontWeight.Bold, color = TextPrimary)
                            Spacer(modifier = Modifier.height(12.dp))
                            Text("• Appearance: Dark Cybernetic OLED Palette", color = TextSecondary, fontSize = 14.sp)
                            Text("• Background: #090B10", color = TextMuted, fontSize = 12.sp)
                            Text("• Accent: #38BDF8 (V.E.D.A. Cyan)", color = TextMuted, fontSize = 12.sp)
                        }
                    }

                    "About" -> {
                        Column {
                            Text("V.E.D.A. Android Edition", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = VedaCyan)
                            Text("Virtual Executive Desktop Assistant — Mobile Client", color = TextSecondary, fontSize = 13.sp)
                            Spacer(modifier = Modifier.height(12.dp))
                            Text("Author & Creator: Shreyas", color = TextPrimary, fontWeight = FontWeight.SemiBold)
                            Text("Version: 2.4.0 (Native Android Compose)", color = TextMuted, fontSize = 12.sp)
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("Reuses existing V.E.D.A. AI Provider Architecture & Windows Bridge.", color = TextSecondary, fontSize = 12.sp)
                        }
                    }

                    else -> {
                        Column {
                            Text(selectedSection, fontWeight = FontWeight.Bold, color = TextPrimary)
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("Configured and active for V.E.D.A. Android client.", color = TextSecondary)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun PermissionStatusRow(name: String, isAllowed: Boolean) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp)
            .background(DarkCard, RoundedCornerShape(8.dp))
            .padding(14.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(name, color = TextPrimary, fontSize = 14.sp)
        Text(
            if (isAllowed) "[Allowed]" else "[Denied / Required]",
            fontWeight = FontWeight.Bold,
            color = if (isAllowed) VedaEmerald else VedaRed,
            fontSize = 13.sp
        )
    }
}
