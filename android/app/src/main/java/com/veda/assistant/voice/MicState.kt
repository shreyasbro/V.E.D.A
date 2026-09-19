package com.veda.assistant.voice

enum class MicState(val label: String, val colorHex: String) {
    MIC_OFF("MIC OFF", "#94a3b8"),
    MIC_INITIALIZING("INITIALIZING", "#38bdf8"),
    MIC_READY("READY", "#10b981"),
    HEARING("HEARING", "#38bdf8"),
    SPEECH_DETECTED("SPEECH DETECTED", "#38bdf8"),
    PROCESSING("PROCESSING", "#a855f7"),
    SPEAKING("SPEAKING", "#0284c7"),
    MIC_ERROR("MIC ERROR", "#ef4444")
}
