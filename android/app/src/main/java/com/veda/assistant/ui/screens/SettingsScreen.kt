package com.veda.assistant.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.veda.assistant.agent.AgentCore
import com.veda.assistant.provider.ProviderSlot
import com.veda.assistant.ui.theme.*
import com.veda.assistant.updater.DownloadProgress
import com.veda.assistant.updater.GitHubReleaseUpdater
import com.veda.assistant.updater.MobileReleaseInfo
import kotlinx.coroutines.launch
import java.io.File

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

    // Updater states
    var updateStatusMsg by remember { mutableStateOf("Tap 'Check for Updates' to query official GitHub Releases.") }
    var isCheckingUpdates by remember { mutableStateOf(false) }
    var isDownloading by remember { mutableStateOf(false) }
    var availableUpdate by remember { mutableStateOf<MobileReleaseInfo?>(null) }
    var downloadProgress by remember { mutableStateOf<DownloadProgress?>(null) }
    var downloadedApkFile by remember { mutableStateOf<File?>(null) }

    // Updater toggle states
    var autoCheck by remember { mutableStateOf(updater.autoCheckEnabled) }
    var autoDownload by remember { mutableStateOf(updater.autoDownloadEnabled) }

    val sections = listOf(
        "AI Providers", "Permissions", "Updates", "Voice & Kokoro", "About"
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
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = VedaCyan)
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

            Spacer(modifier = Modifier.height(8.dp))

            when (selectedSection) {
                "AI Providers" -> {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp)
                    ) {
                        item {
                            Surface(
                                shape = RoundedCornerShape(8.dp),
                                color = DarkSurface,
                                border = BorderStroke(1.dp, BorderDark),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Column(modifier = Modifier.padding(12.dp)) {
                                    Text("⚡ AI Provider Architecture", fontWeight = FontWeight.Bold, color = VedaCyan, fontSize = 14.sp)
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text(
                                        "Configure up to 6 AI engines (Gemini, Groq, OpenAI, Anthropic, Ollama, etc.). Credentials are encrypted with Android Keystore. The designated Primary provider executes agent commands and reasoning.",
                                        fontSize = 11.sp,
                                        color = TextSecondary,
                                        lineHeight = 16.sp
                                    )
                                }
                            }
                        }

                        items(providers) { slot ->
                            ProviderSlotCard(
                                slot = slot,
                                onSave = { updated ->
                                    providerManager.updateProvider(updated)
                                    refreshProviderList()
                                },
                                onSetPrimary = {
                                    providerManager.setPrimaryProvider(slot.id)
                                    refreshProviderList()
                                },
                                onFetchModels = {
                                    providerManager.fetchModels(slot.id)
                                },
                                onTestConnection = {
                                    providerManager.testConnection(slot.id)
                                },
                                onTestChat = { prompt ->
                                    providerManager.testChat(slot.id, prompt)
                                },
                                onReset = {
                                    providerManager.removeProvider(slot.id)
                                    refreshProviderList()
                                }
                            )
                        }
                    }
                }

                "Permissions" -> {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(16.dp)
                    ) {
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = DarkCard,
                            border = BorderStroke(1.dp, BorderDark),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                Text("🛡️ System Permissions & Access", fontWeight = FontWeight.Bold, color = VedaCyan)
                                Spacer(modifier = Modifier.height(6.dp))
                                Text(
                                    "V.E.D.A. operates autonomously on-device. Review and grant Android permissions for voice input, device automation, camera analysis, and unknown app installation for updates.",
                                    color = TextSecondary,
                                    fontSize = 12.sp,
                                    lineHeight = 17.sp
                                )
                                Spacer(modifier = Modifier.height(14.dp))
                                Button(
                                    onClick = onOpenPermissionCenter,
                                    colors = ButtonDefaults.buttonColors(containerColor = VedaCyan),
                                    shape = RoundedCornerShape(6.dp)
                                ) {
                                    Text("Open Permission Center Dashboard", color = DarkBackground, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                                }
                            }
                        }
                    }
                }

                "Updates" -> {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp)
                    ) {
                        item {
                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = DarkCard,
                                border = BorderStroke(1.dp, BorderDark),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text("📦 GitHub OTA Updater", fontWeight = FontWeight.Bold, color = VedaCyan, fontSize = 15.sp)
                                        Surface(
                                            color = DarkSurface,
                                            shape = RoundedCornerShape(4.dp),
                                            border = BorderStroke(1.dp, BorderDark)
                                        ) {
                                            Text(
                                                "Installed: v${updater.currentVersion}",
                                                fontSize = 11.sp,
                                                color = VedaEmerald,
                                                fontWeight = FontWeight.SemiBold,
                                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                                            )
                                        }
                                    }

                                    Spacer(modifier = Modifier.height(8.dp))
                                    Text("Source: github.com/shreyasbro/V.E.D.A (Releases)", fontSize = 11.sp, color = TextMuted)
                                    Spacer(modifier = Modifier.height(6.dp))
                                    Text(updateStatusMsg, fontSize = 12.sp, color = TextSecondary)

                                    Spacer(modifier = Modifier.height(14.dp))

                                    // Check button
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Button(
                                            onClick = {
                                                isCheckingUpdates = true
                                                downloadedApkFile = null
                                                downloadProgress = null
                                                updateStatusMsg = "Connecting to GitHub Releases API..."
                                                coroutineScope.launch {
                                                    val res = updater.checkForUpdates()
                                                    isCheckingUpdates = false
                                                    res.onSuccess { (hasUpd, rel) ->
                                                        if (hasUpd && rel != null) {
                                                            availableUpdate = rel
                                                            updateStatusMsg = "✓ New update v${rel.cleanVersion} found on GitHub!"
                                                        } else {
                                                            availableUpdate = null
                                                            updateStatusMsg = "✓ V.E.D.A. is up to date (v${updater.currentVersion})."
                                                        }
                                                    }.onFailure {
                                                        updateStatusMsg = "✕ Update check failed: ${it.message}"
                                                    }
                                                }
                                            },
                                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0284c7)),
                                            shape = RoundedCornerShape(6.dp),
                                            enabled = !isCheckingUpdates && !isDownloading
                                        ) {
                                            Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(16.dp))
                                            Spacer(modifier = Modifier.width(6.dp))
                                            Text(if (isCheckingUpdates) "Checking..." else "Check for Updates", fontSize = 12.sp)
                                        }

                                        availableUpdate?.let { rel ->
                                            OutlinedButton(
                                                onClick = {
                                                    val browserIntent = Intent(Intent.ACTION_VIEW, Uri.parse(rel.htmlUrl)).apply {
                                                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                                    }
                                                    context.startActivity(browserIntent)
                                                },
                                                shape = RoundedCornerShape(6.dp),
                                                border = BorderStroke(1.dp, BorderDark)
                                            ) {
                                                Text("View Release", fontSize = 12.sp, color = TextPrimary)
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Preferences Section
                        item {
                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = DarkCard,
                                border = BorderStroke(1.dp, BorderDark),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Text("⚙️ Update Preferences", fontWeight = FontWeight.Bold, color = TextPrimary, fontSize = 13.sp)
                                    Spacer(modifier = Modifier.height(10.dp))

                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text("Automatically check for updates", fontSize = 12.sp, color = TextPrimary)
                                            Text("Query GitHub Releases on application start", fontSize = 10.sp, color = TextMuted)
                                        }
                                        Switch(
                                            checked = autoCheck,
                                            onCheckedChange = {
                                                autoCheck = it
                                                updater.autoCheckEnabled = it
                                            }
                                        )
                                    }

                                    Spacer(modifier = Modifier.height(8.dp))

                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text("Automatically download updates", fontSize = 12.sp, color = TextPrimary)
                                            Text("Download verified APKs in background", fontSize = 10.sp, color = TextMuted)
                                        }
                                        Switch(
                                            checked = autoDownload,
                                            onCheckedChange = {
                                                autoDownload = it
                                                updater.autoDownloadEnabled = it
                                            }
                                        )
                                    }
                                }
                            }
                        }

                        // Available Update Info & Actions
                        availableUpdate?.let { rel ->
                            item {
                                Surface(
                                    shape = RoundedCornerShape(10.dp),
                                    color = DarkCard,
                                    border = BorderStroke(1.dp, Color(0xFF0284c7)),
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Column(modifier = Modifier.padding(14.dp)) {
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text("🚀 New Version: ${rel.tagName}", fontWeight = FontWeight.Bold, color = VedaCyan, fontSize = 14.sp)
                                            Text(rel.publishedAt.take(10), fontSize = 11.sp, color = TextMuted)
                                        }

                                        Spacer(modifier = Modifier.height(8.dp))

                                        if (rel.releaseNotes.isNotBlank()) {
                                            Text("Release Notes:", fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = TextPrimary)
                                            Spacer(modifier = Modifier.height(4.dp))
                                            Surface(
                                                color = DarkSurface,
                                                shape = RoundedCornerShape(6.dp),
                                                border = BorderStroke(1.dp, BorderDark),
                                                modifier = Modifier.fillMaxWidth()
                                            ) {
                                                Text(
                                                    rel.releaseNotes,
                                                    fontSize = 11.sp,
                                                    color = TextSecondary,
                                                    fontFamily = FontFamily.Monospace,
                                                    modifier = Modifier.padding(10.dp)
                                                )
                                            }
                                        }

                                        Spacer(modifier = Modifier.height(12.dp))

                                        // Progress bar if downloading
                                        downloadProgress?.let { prog ->
                                            Column(modifier = Modifier.fillMaxWidth()) {
                                                Row(
                                                    modifier = Modifier.fillMaxWidth(),
                                                    horizontalArrangement = Arrangement.SpaceBetween
                                                ) {
                                                    Text("Downloading APK: ${prog.percent}%", fontSize = 11.sp, color = TextPrimary)
                                                    Text(
                                                        "${String.format("%.1f", prog.bytesDownloaded / (1024.0 * 1024.0))} MB / ${String.format("%.1f", prog.totalBytes / (1024.0 * 1024.0))} MB (${String.format("%.2f", prog.speedMbPerSec)} MB/s)",
                                                        fontSize = 10.sp,
                                                        color = TextMuted
                                                    )
                                                }
                                                Spacer(modifier = Modifier.height(4.dp))
                                                LinearProgressIndicator(
                                                    progress = { prog.percent / 100f },
                                                    modifier = Modifier.fillMaxWidth().height(6.dp),
                                                    color = VedaCyan,
                                                    trackColor = DarkSurface,
                                                )
                                            }
                                            Spacer(modifier = Modifier.height(12.dp))
                                        }

                                        // Download & Install Buttons
                                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                            if (downloadedApkFile == null) {
                                                Button(
                                                    onClick = {
                                                        isDownloading = true
                                                        updateStatusMsg = "Downloading update from GitHub..."
                                                        coroutineScope.launch {
                                                            val dlResult = updater.downloadAndVerifyApk(rel) { p ->
                                                                downloadProgress = p
                                                            }
                                                            isDownloading = false
                                                            dlResult.onSuccess { file ->
                                                                downloadedApkFile = file
                                                                updateStatusMsg = "✓ Downloaded and SHA-256 verified! Tap Install Update."
                                                            }.onFailure {
                                                                updateStatusMsg = "✕ Download failed: ${it.message}"
                                                            }
                                                        }
                                                    },
                                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF059669)),
                                                    shape = RoundedCornerShape(6.dp),
                                                    enabled = !isDownloading
                                                ) {
                                                    Text(if (isDownloading) "Downloading..." else "Download Update", fontSize = 12.sp)
                                                }
                                            } else {
                                                Button(
                                                    onClick = {
                                                        downloadedApkFile?.let { file ->
                                                            val instResult = updater.launchPackageInstaller(file)
                                                            instResult.onFailure {
                                                                updateStatusMsg = it.message ?: "Installer error"
                                                            }
                                                        }
                                                    },
                                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF10b981)),
                                                    shape = RoundedCornerShape(6.dp)
                                                ) {
                                                    Text("Install Update Now", fontSize = 12.sp, color = DarkBackground, fontWeight = FontWeight.Bold)
                                                }
                                            }
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
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            color = DarkCard,
                            shape = RoundedCornerShape(10.dp),
                            border = BorderStroke(1.dp, BorderDark)
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
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            color = DarkCard,
                            shape = RoundedCornerShape(10.dp),
                            border = BorderStroke(1.dp, BorderDark)
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text("V.E.D.A. Standalone Android Edition", fontWeight = FontWeight.Bold, color = VedaCyan, fontSize = 16.sp)
                                Spacer(modifier = Modifier.height(4.dp))
                                Text("Version ${updater.currentVersion} • Autonomous On-Device Assistant", fontSize = 12.sp, color = TextMuted)
                                Spacer(modifier = Modifier.height(12.dp))
                                Text(
                                    "V.E.D.A. (Virtual Executive Desktop Assistant) for Android runs fully native on your device. It requires no Windows PC, no Vercel servers, and no companion bridges.",
                                    fontSize = 12.sp,
                                    color = TextSecondary,
                                    lineHeight = 18.sp
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProviderSlotCard(
    slot: ProviderSlot,
    onSave: (ProviderSlot) -> Unit,
    onSetPrimary: () -> Unit,
    onFetchModels: suspend () -> Result<List<String>>,
    onTestConnection: suspend () -> Triple<String, Int?, String?>,
    onTestChat: suspend (String) -> Result<Triple<String, Int, String>>,
    onReset: () -> Unit
) {
    val coroutineScope = rememberCoroutineScope()

    var nameInput by remember { mutableStateOf(slot.name) }
    var baseUrlInput by remember { mutableStateOf(slot.baseUrl) }
    var keyInput by remember { mutableStateOf(slot.apiKey) }
    var selectedModel by remember { mutableStateOf(slot.model) }
    var isEnabled by remember { mutableStateOf(slot.enabled) }

    var availableModels by remember { mutableStateOf(slot.availableModels) }
    var statusText by remember { mutableStateOf(slot.status) }
    var latencyMs by remember { mutableStateOf(slot.lastLatencyMs) }
    var statusMessage by remember { mutableStateOf<String?>(null) }

    var isFetchingModels by remember { mutableStateOf(false) }
    var isTestingConnection by remember { mutableStateOf(false) }
    var isTestingChat by remember { mutableStateOf(false) }

    var modelDropdownExpanded by remember { mutableStateOf(false) }

    // Test Chat Panel states
    var showTestChat by remember { mutableStateOf(false) }
    var testPromptInput by remember { mutableStateOf("Who are you?") }
    var testChatReply by remember { mutableStateOf<String?>(null) }
    var testChatLatency by remember { mutableStateOf<Int?>(null) }

    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = DarkCard,
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, if (slot.isPrimary) VedaCyan else BorderDark)
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            // Header: Name, Primary badge, Enabled switch
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(slot.name, fontWeight = FontWeight.Bold, color = if (slot.isPrimary) VedaCyan else TextPrimary, fontSize = 15.sp)
                    if (slot.isPrimary) {
                        Spacer(modifier = Modifier.width(6.dp))
                        Surface(
                            color = VedaCyan.copy(alpha = 0.2f),
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Text(
                                "PRIMARY",
                                fontSize = 9.sp,
                                fontWeight = FontWeight.Bold,
                                color = VedaCyan,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(if (isEnabled) "Active" else "Disabled", fontSize = 11.sp, color = if (isEnabled) VedaEmerald else TextMuted)
                    Spacer(modifier = Modifier.width(6.dp))
                    Switch(
                        checked = isEnabled,
                        onCheckedChange = { checked ->
                            isEnabled = checked
                            onSave(slot.copy(enabled = checked, name = nameInput, baseUrl = baseUrlInput, apiKey = keyInput, model = selectedModel))
                        }
                    )
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Inputs: Base URL (if custom/openai/etc.)
            if (slot.providerPreset != "gemini") {
                OutlinedTextField(
                    value = baseUrlInput,
                    onValueChange = { baseUrlInput = it },
                    label = { Text("Base URL", fontSize = 11.sp) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    textStyle = LocalTextStyle.current.copy(fontSize = 12.sp, color = TextPrimary)
                )
                Spacer(modifier = Modifier.height(6.dp))
            }

            // API Key
            OutlinedTextField(
                value = keyInput,
                onValueChange = { keyInput = it },
                label = { Text("API Key (Encrypted in Keystore)", fontSize = 11.sp) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                textStyle = LocalTextStyle.current.copy(fontSize = 12.sp, color = TextPrimary)
            )

            Spacer(modifier = Modifier.height(6.dp))

            // Model Selection (Dropdown or TextField)
            Box(modifier = Modifier.fillMaxWidth()) {
                OutlinedTextField(
                    value = selectedModel,
                    onValueChange = { selectedModel = it },
                    label = { Text("Model Name", fontSize = 11.sp) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    textStyle = LocalTextStyle.current.copy(fontSize = 12.sp, color = TextPrimary),
                    trailingIcon = {
                        if (availableModels.isNotEmpty()) {
                            IconButton(onClick = { modelDropdownExpanded = true }) {
                                Icon(Icons.Default.Refresh, contentDescription = "Select Model", tint = VedaCyan)
                            }
                        }
                    }
                )

                DropdownMenu(
                    expanded = modelDropdownExpanded,
                    onDismissRequest = { modelDropdownExpanded = false },
                    modifier = Modifier.background(DarkSurface)
                ) {
                    availableModels.forEach { modelName ->
                        DropdownMenuItem(
                            text = { Text(modelName, fontSize = 12.sp, color = TextPrimary) },
                            onClick = {
                                selectedModel = modelName
                                modelDropdownExpanded = false
                            }
                        )
                    }
                }
            }

            // Status message / diagnostics
            statusMessage?.let { msg ->
                Spacer(modifier = Modifier.height(6.dp))
                Text(msg, fontSize = 11.sp, color = if (statusText == "Connected") VedaEmerald else Color(0xFFEF4444))
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Action Buttons Row: Fetch Models & Test Connection
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Fetch Models button
                Button(
                    onClick = {
                        isFetchingModels = true
                        statusMessage = "Fetching models from API..."
                        coroutineScope.launch {
                            // save current key first
                            onSave(slot.copy(apiKey = keyInput.trim(), baseUrl = baseUrlInput.trim(), model = selectedModel.trim()))
                            val res = onFetchModels()
                            isFetchingModels = false
                            res.onSuccess { models ->
                                availableModels = models
                                if (models.isNotEmpty() && (selectedModel.isBlank() || selectedModel !in models)) {
                                    selectedModel = models.first()
                                }
                                statusMessage = "✓ ${models.size} models retrieved from API"
                                modelDropdownExpanded = true
                            }.onFailure { err ->
                                statusMessage = "✕ Failed to fetch models: ${err.message}"
                            }
                        }
                    },
                    shape = RoundedCornerShape(6.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = DarkSurface),
                    border = BorderStroke(1.dp, BorderDark),
                    modifier = Modifier.height(34.dp),
                    enabled = !isFetchingModels
                ) {
                    Text(if (isFetchingModels) "Fetching..." else "Fetch Models", fontSize = 11.sp, color = VedaCyan)
                }

                // Test Connection button
                Button(
                    onClick = {
                        isTestingConnection = true
                        statusMessage = "Testing authentication & latency..."
                        coroutineScope.launch {
                            onSave(slot.copy(apiKey = keyInput.trim(), baseUrl = baseUrlInput.trim(), model = selectedModel.trim()))
                            val (st, lat, err) = onTestConnection()
                            isTestingConnection = false
                            statusText = st
                            latencyMs = lat
                            if (st == "Connected") {
                                statusMessage = "✓ Connection verified (${lat}ms)"
                            } else {
                                statusMessage = "✕ ${err ?: "Connection failed"}"
                            }
                        }
                    },
                    shape = RoundedCornerShape(6.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0284c7)),
                    modifier = Modifier.height(34.dp),
                    enabled = !isTestingConnection
                ) {
                    Text(if (isTestingConnection) "Testing..." else "Test Connection", fontSize = 11.sp, color = Color.White)
                }

                // Status Badge
                val statColor = when (statusText) {
                    "Connected" -> VedaEmerald
                    "Connection Failed" -> Color(0xFFEF4444)
                    else -> TextMuted
                }
                Text(
                    text = if (latencyMs != null && statusText == "Connected") "$statusText (${latencyMs}ms)" else statusText,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = statColor
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Secondary Action Row: Save, Set Primary, Test Chat toggle
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = {
                            val updated = slot.copy(
                                name = nameInput.trim(),
                                baseUrl = baseUrlInput.trim(),
                                apiKey = keyInput.trim(),
                                model = selectedModel.trim(),
                                enabled = isEnabled,
                                availableModels = availableModels
                            )
                            onSave(updated)
                            statusMessage = "✓ Saved securely to Keystore"
                        },
                        shape = RoundedCornerShape(6.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = DarkSurface),
                        border = BorderStroke(1.dp, BorderDark),
                        modifier = Modifier.height(32.dp)
                    ) {
                        Text("Save", fontSize = 11.sp, color = TextPrimary)
                    }

                    if (!slot.isPrimary) {
                        Button(
                            onClick = onSetPrimary,
                            shape = RoundedCornerShape(6.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = DarkSurface),
                            border = BorderStroke(1.dp, BorderDark),
                            modifier = Modifier.height(32.dp)
                        ) {
                            Text("Make Primary", fontSize = 11.sp, color = VedaCyan)
                        }
                    }
                }

                TextButton(
                    onClick = { showTestChat = !showTestChat },
                    modifier = Modifier.height(32.dp)
                ) {
                    Text(if (showTestChat) "Hide Chat Test" else "Test Chat 💬", fontSize = 11.sp, color = VedaCyan)
                }
            }

            // Expandable Test Chat Panel
            if (showTestChat) {
                Spacer(modifier = Modifier.height(10.dp))
                Surface(
                    color = DarkSurface,
                    shape = RoundedCornerShape(8.dp),
                    border = BorderStroke(1.dp, BorderDark),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Text("💬 Direct Test Chat (Model: ${selectedModel.ifBlank { "default" }})", fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = VedaCyan)
                        Spacer(modifier = Modifier.height(6.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            OutlinedTextField(
                                value = testPromptInput,
                                onValueChange = { testPromptInput = it },
                                placeholder = { Text("Prompt...", fontSize = 11.sp) },
                                singleLine = true,
                                modifier = Modifier.weight(1f),
                                textStyle = LocalTextStyle.current.copy(fontSize = 11.sp, color = TextPrimary)
                            )

                            Button(
                                onClick = {
                                    isTestingChat = true
                                    testChatReply = "Waiting for response..."
                                    coroutineScope.launch {
                                        onSave(slot.copy(apiKey = keyInput.trim(), baseUrl = baseUrlInput.trim(), model = selectedModel.trim()))
                                        val res = onTestChat(testPromptInput)
                                        isTestingChat = false
                                        res.onSuccess { (reply, lat, _) ->
                                            testChatReply = reply
                                            testChatLatency = lat
                                        }.onFailure { err ->
                                            testChatReply = "Error: ${err.message}"
                                            testChatLatency = null
                                        }
                                    }
                                },
                                shape = RoundedCornerShape(6.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0284c7)),
                                modifier = Modifier.height(36.dp),
                                enabled = !isTestingChat && testPromptInput.isNotBlank()
                            ) {
                                Text(if (isTestingChat) "..." else "Send", fontSize = 11.sp)
                            }
                        }

                        testChatReply?.let { reply ->
                            Spacer(modifier = Modifier.height(8.dp))
                            Surface(
                                color = DarkCard,
                                shape = RoundedCornerShape(6.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Column(modifier = Modifier.padding(8.dp)) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween
                                    ) {
                                        Text("Response:", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = TextMuted)
                                        testChatLatency?.let { lat ->
                                            Text("${lat}ms", fontSize = 10.sp, color = VedaEmerald)
                                        }
                                    }
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text(reply, fontSize = 11.sp, color = TextPrimary, lineHeight = 15.sp)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
