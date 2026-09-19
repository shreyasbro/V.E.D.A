package com.veda.assistant.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.veda.assistant.agent.AgentCore
import com.veda.assistant.provider.ProviderSlot
import com.veda.assistant.ui.theme.*
import com.veda.assistant.updater.GitHubReleaseUpdater
import com.veda.assistant.updater.MobileReleaseInfo
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    agentCore: AgentCore,
    onBack: () -> Unit,
    onOpenPermissionCenter: () -> Unit
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val providerManager = agentCore.providerManager
    val updater = remember { GitHubReleaseUpdater(context) }

    var providers by remember { mutableStateOf(providerManager.getProviders()) }
    var selectedSection by remember { mutableStateOf("AI Providers") }

    var updateStatusMsg by remember { mutableStateOf("Tap 'Check for Updates' to query GitHub Releases.") }
    var isCheckingUpdates by remember { mutableStateOf(false) }
    var availableUpdate by remember { mutableStateOf<MobileReleaseInfo?>(null) }

    val sections = listOf(
        "AI Providers", "Permissions", "Updates", "Voice & Kokoro", "Automations", "About"
    )

    fun refreshProviderList() {
        providers = providerManager.getProviders()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("V.E.D.A. Settings", fontWeight = FontWeight.Bold, color = TextPrimary) },
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

            Spacer(modifier = Modifier.height(10.dp))

            when (selectedSection) {
                "AI Providers" -> {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp)
                    ) {
                        item {
                            Text(
                                "Configure up to 6 AI providers. Credentials are encrypted securely using Android Keystore.",
                                fontSize = 12.sp,
                                color = TextSecondary
                            )
                        }

                        items(providers) { slot ->
                            var keyInput by remember { mutableStateOf(slot.apiKey) }
                            var modelInput by remember { mutableStateOf(slot.model) }
                            var testResult by remember { mutableStateOf(slot.status) }
                            var testLatency by remember { mutableStateOf(slot.lastLatencyMs) }
                            var isTesting by remember { mutableStateOf(false) }

                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                colors = CardDefaults.cardColors(containerColor = DarkCard),
                                shape = RoundedCornerShape(10.dp)
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column {
                                            Text(slot.name, fontWeight = FontWeight.Bold, color = VedaCyan, fontSize = 15.sp)
                                            Text(slot.maskedApiKey(), fontSize = 11.sp, color = TextMuted)
                                        }
                                        
                                        Switch(
                                            checked = slot.enabled,
                                            onCheckedChange = { checked ->
                                                val updated = slot.copy(enabled = checked)
                                                providerManager.updateProvider(updated)
                                                refreshProviderList()
                                            }
                                        )
                                    }

                                    Spacer(modifier = Modifier.height(8.dp))

                                    OutlinedTextField(
                                        value = keyInput,
                                        onValueChange = { keyInput = it },
                                        label = { Text("API Key", fontSize = 11.sp) },
                                        singleLine = true,
                                        modifier = Modifier.fillMaxWidth(),
                                        textStyle = LocalTextStyle.current.copy(fontSize = 12.sp, color = TextPrimary)
                                    )

                                    Spacer(modifier = Modifier.height(6.dp))

                                    OutlinedTextField(
                                        value = modelInput,
                                        onValueChange = { modelInput = it },
                                        label = { Text("Model Name", fontSize = 11.sp) },
                                        singleLine = true,
                                        modifier = Modifier.fillMaxWidth(),
                                        textStyle = LocalTextStyle.current.copy(fontSize = 12.sp, color = TextPrimary)
                                    )

                                    Spacer(modifier = Modifier.height(10.dp))

                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Button(
                                            onClick = {
                                                val updated = slot.copy(apiKey = keyInput.trim(), model = modelInput.trim())
                                                providerManager.updateProvider(updated)
                                                refreshProviderList()
                                            },
                                            shape = RoundedCornerShape(6.dp),
                                            colors = ButtonDefaults.buttonColors(containerColor = DarkSurface),
                                            modifier = Modifier.height(32.dp)
                                        ) {
                                            Text("Save", fontSize = 11.sp, color = VedaCyan)
                                        }

                                        Button(
                                            onClick = {
                                                isTesting = true
                                                coroutineScope.launch {
                                                    val (st, lat, err) = providerManager.testConnection(slot.id)
                                                    testResult = st
                                                    testLatency = lat
                                                    isTesting = false
                                                    refreshProviderList()
                                                }
                                            },
                                            shape = RoundedCornerShape(6.dp),
                                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0284c7)),
                                            modifier = Modifier.height(32.dp)
                                        ) {
                                            Text(if (isTesting) "Testing..." else "Test Connection", fontSize = 11.sp, color = Color.White)
                                        }

                                        val statColor = when (testResult) {
                                            "CONNECTED" -> Color(0xFF10b981)
                                            "ERROR" -> Color(0xFFef4444)
                                            else -> TextMuted
                                        }
                                        Text(
                                            text = if (testLatency != null) "$testResult (${testLatency}ms)" else testResult,
                                            fontSize = 11.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = statColor
                                        )
                                    }
                                }
                            }
                        }
                    }
                }

                "Permissions" -> {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(16.dp)
                    ) {
                        Text(
                            "View and grant device permissions required by V.E.D.A. (Microphone, Camera, Accessibility, Storage).",
                            color = TextSecondary,
                            fontSize = 13.sp
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Button(
                            onClick = onOpenPermissionCenter,
                            colors = ButtonDefaults.buttonColors(containerColor = VedaCyan),
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Text("Open Permission Center Dashboard", color = DarkBackground, fontWeight = FontWeight.Bold)
                        }
                    }
                }

                "Updates" -> {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(16.dp)
                    ) {
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(containerColor = DarkCard),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                Text("📦 Official GitHub Releases OTA Updater", fontWeight = FontWeight.Bold, color = VedaCyan)
                                Spacer(modifier = Modifier.height(6.dp))
                                Text("• Installed Version: v1.0.0", fontSize = 12.sp, color = TextPrimary)
                                Text("• Authoritative Source: github.com/shreyasbro/V.E.D.A", fontSize = 12.sp, color = TextMuted)
                                Spacer(modifier = Modifier.height(8.dp))
                                Text(updateStatusMsg, fontSize = 12.sp, color = TextSecondary)

                                Spacer(modifier = Modifier.height(14.dp))

                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Button(
                                        onClick = {
                                            isCheckingUpdates = true
                                            updateStatusMsg = "Checking GitHub Releases API..."
                                            coroutineScope.launch {
                                                val res = updater.checkForUpdates()
                                                isCheckingUpdates = false
                                                res.onSuccess { (hasUpd, rel) ->
                                                    if (hasUpd && rel != null) {
                                                        availableUpdate = rel
                                                        updateStatusMsg = "✓ Update v${rel.cleanVersion} found on GitHub!"
                                                    } else {
                                                        availableUpdate = null
                                                        updateStatusMsg = "✓ V.E.D.A. is up to date."
                                                    }
                                                }.onFailure {
                                                    updateStatusMsg = "✕ ${it.message}"
                                                }
                                            }
                                        },
                                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0284c7)),
                                        shape = RoundedCornerShape(6.dp)
                                    ) {
                                        Text(if (isCheckingUpdates) "Checking..." else "Check for Updates", fontSize = 12.sp)
                                    }

                                    if (availableUpdate != null) {
                                        Button(
                                            onClick = {
                                                availableUpdate?.let { updater.triggerApkDownloadAndInstall(it) }
                                            },
                                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF059669)),
                                            shape = RoundedCornerShape(6.dp)
                                        ) {
                                            Text("Download & Install", fontSize = 12.sp)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                "Voice & Kokoro" -> {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(16.dp)
                    ) {
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(containerColor = DarkCard),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                Text("🎙️ Voice & Kokoro TTS Engine", fontWeight = FontWeight.Bold, color = VedaCyan)
                                Spacer(modifier = Modifier.height(6.dp))
                                Text("• Primary TTS: Kokoro Mobile On-Device Synthesizer", fontSize = 12.sp, color = TextPrimary)
                                Text("• Languages: Hindi, Hinglish, English", fontSize = 12.sp, color = TextSecondary)
                                Text("• Hardware Barge-In: Enabled", fontSize = 12.sp, color = TextSecondary)
                                Text("• Fish Audio: Completely Removed", fontSize = 12.sp, color = Color(0xFF10b981))
                            }
                        }
                    }
                }

                else -> {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(16.dp)
                    ) {
                        Text(
                            "V.E.D.A. (Virtual Executive Desktop Assistant) — Standalone Mobile Edition\n" +
                            "Created by Shreyas.\nVersion 1.0.0 (Native Android)",
                            color = TextSecondary,
                            fontSize = 13.sp,
                            lineHeight = 20.sp
                        )
                    }
                }
            }
        }
    }
}
