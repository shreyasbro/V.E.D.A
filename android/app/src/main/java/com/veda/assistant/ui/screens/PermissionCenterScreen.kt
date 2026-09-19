package com.veda.assistant.ui.screens

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.veda.assistant.accessibility.VedaAccessibilityService
import com.veda.assistant.ui.theme.*

data class PermissionItem(
    val title: String,
    val description: String,
    val isGranted: Boolean,
    val actionType: String,
    val permissionManifest: String? = null
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PermissionCenterScreen(
    onBack: () -> Unit
) {
    val context = LocalContext.current
    var refreshTrigger by remember { mutableStateOf(0) }

    val micGranted = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    val cameraGranted = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
    val notifGranted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    } else true
    val accessibilityGranted = VedaAccessibilityService.isRunning

    val items = listOf(
        PermissionItem(
            title = "Microphone",
            description = "Required for real-time natural voice conversation, VAD, and speech recognition.",
            isGranted = micGranted,
            actionType = "APP_SETTINGS",
            permissionManifest = Manifest.permission.RECORD_AUDIO
        ),
        PermissionItem(
            title = "Camera",
            description = "Used only on demand for ephemeral scene understanding, text reading, and visual analysis.",
            isGranted = cameraGranted,
            actionType = "APP_SETTINGS",
            permissionManifest = Manifest.permission.CAMERA
        ),
        PermissionItem(
            title = "Notifications",
            description = "Enables V.E.D.A. to alert you when tasks, updates, or background automations finish.",
            isGranted = notifGranted,
            actionType = "APP_SETTINGS"
        ),
        PermissionItem(
            title = "Accessibility Service",
            description = "Allows automated UI actions (clicking buttons, reading visible screens) on demand.",
            isGranted = accessibilityGranted,
            actionType = "ACCESSIBILITY_SETTINGS"
        ),
        PermissionItem(
            title = "Storage & Files (SAF)",
            description = "Uses modern Android Storage Access Framework for document browsing and file search.",
            isGranted = true,
            actionType = "NONE"
        )
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Permission Center", fontWeight = FontWeight.Bold, color = TextPrimary) },
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
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                Text(
                    text = "V.E.D.A. Mobile strictly adheres to the Android security model. Features activate only when you grant genuine permissions.",
                    fontSize = 12.sp,
                    color = TextSecondary,
                    lineHeight = 18.sp
                )
            }

            items(items) { item ->
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
                            Text(item.title, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = TextPrimary)
                            
                            val statusBg = if (item.isGranted) Color(0xFF064e3b) else Color(0xFF451a03)
                            val statusFg = if (item.isGranted) Color(0xFF34d399) else Color(0xFFfbbf24)
                            val statusText = if (item.isGranted) "GRANTED" else "DENIED"

                            Box(
                                modifier = Modifier
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(statusBg)
                                    .padding(horizontal = 8.dp, vertical = 4.dp)
                            ) {
                                Text(statusText, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = statusFg)
                            }
                        }

                        Spacer(modifier = Modifier.height(6.dp))
                        Text(item.description, fontSize = 12.sp, color = TextSecondary)

                        if (!item.isGranted && item.actionType != "NONE") {
                            Spacer(modifier = Modifier.height(10.dp))
                            Button(
                                onClick = {
                                    when (item.actionType) {
                                        "ACCESSIBILITY_SETTINGS" -> {
                                            context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
                                                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                            })
                                        }
                                        else -> {
                                            val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                                                data = Uri.fromParts("package", context.packageName, null)
                                                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                            }
                                            context.startActivity(intent)
                                        }
                                    }
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = VedaCyan),
                                shape = RoundedCornerShape(8.dp),
                                modifier = Modifier.height(34.dp)
                            ) {
                                Text("Grant in Android Settings", fontSize = 11.sp, color = DarkBackground, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }
        }
    }
}
