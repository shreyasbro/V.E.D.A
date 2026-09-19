package com.veda.assistant.ui.theme

import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color

val DarkBackground = Color(0xFF090B10)
val DarkSurface = Color(0xFF10141E)
val DarkCard = Color(0xFF161B28)
val VedaCyan = Color(0xFF38BDF8)
val VedaCyanGlow = Color(0x3338BDF8)
val VedaEmerald = Color(0xFF10B981)
val VedaAmber = Color(0xFFF59E0B)
val VedaRed = Color(0xFFEF4444)
val TextPrimary = Color(0xFFF1F5F9)
val TextSecondary = Color(0xFF94A3B8)
val TextMuted = Color(0xFF64748B)
val BorderDark = Color(0xFF1E293B)
val DarkBorder = BorderDark

val VedaColorScheme = darkColorScheme(
    primary = VedaCyan,
    onPrimary = Color(0xFF001E2B),
    primaryContainer = Color(0xFF00354A),
    onPrimaryContainer = Color(0xFFC2E8FF),
    secondary = VedaEmerald,
    background = DarkBackground,
    surface = DarkSurface,
    surfaceVariant = DarkCard,
    onBackground = TextPrimary,
    onSurface = TextPrimary,
    onSurfaceVariant = TextSecondary,
    outline = BorderDark
)
