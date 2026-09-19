package com.veda.assistant.voice

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.util.Locale

class KokoroTTSEngine(context: Context) {

    private var tts: TextToSpeech? = null
    private var isReady = false
    var onSpeakingStarted: (() -> Unit)? = null
    var onSpeakingFinished: (() -> Unit)? = null

    init {
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                tts?.language = Locale("en", "IN")
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {
                        onSpeakingStarted?.invoke()
                    }
                    override fun onDone(utteranceId: String?) {
                        onSpeakingFinished?.invoke()
                    }
                    override fun onError(utteranceId: String?) {
                        onSpeakingFinished?.invoke()
                    }
                })
                isReady = true
            }
        }
    }

    fun speak(text: String, languageCode: String = "en-IN") {
        if (!isReady || text.isBlank()) return
        stop()

        if (languageCode.startsWith("hi", ignoreCase = true)) {
            tts?.language = Locale("hi", "IN")
        } else {
            tts?.language = Locale("en", "IN")
        }

        val utteranceId = "veda_kokoro_" + System.currentTimeMillis()
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, utteranceId)
    }

    fun stop() {
        if (isReady) {
            tts?.stop()
            onSpeakingFinished?.invoke()
        }
    }

    fun shutdown() {
        stop()
        tts?.shutdown()
        tts = null
    }

    fun isSpeaking(): Boolean {
        return tts?.isSpeaking ?: false
    }
}
