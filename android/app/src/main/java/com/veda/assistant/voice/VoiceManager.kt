package com.veda.assistant.voice

import android.content.Context
import android.content.Intent
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.util.Locale
import kotlin.math.sqrt

class VoiceManager(private val context: Context) {

    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false
    private var audioRecord: AudioRecord? = null
    private var meterJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    // Live genuine microphone amplitude level (0.0 to 1.0)
    private val _micLevel = MutableStateFlow(0.0f)
    val micLevel: StateFlow<Float> = _micLevel

    // Transcription callback: (interim, isFinal)
    var onTranscriptReceived: ((String, Boolean) -> Unit)? = null
    var onError: ((String) -> Unit)? = null
    var onSpeechStart: (() -> Unit)? = null

    fun startListening(languageCode: String = "hi-IN") {
        if (isListening) return

        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            onError?.invoke("Speech recognition service not available on device")
            return
        }

        CoroutineScope(Dispatchers.Main).launch {
            try {
                speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
                    setRecognitionListener(object : RecognitionListener {
                        override fun onReadyForSpeech(params: Bundle?) {
                            isListening = true
                            startAmplitudeMeter()
                        }
                        override fun onBeginningOfSpeech() {
                            onSpeechStart?.invoke()
                        }
                        override fun onRmsChanged(rmsdB: Float) {
                            val normalized = ((rmsdB + 2.0f) / 12.0f).coerceIn(0.0f, 1.0f)
                            _micLevel.value = normalized
                        }
                        override fun onBufferReceived(buffer: ByteArray?) {}
                        override fun onEndOfSpeech() {}
                        override fun onError(error: Int) {
                            stopListening()
                            val msg = when (error) {
                                SpeechRecognizer.ERROR_NO_MATCH -> "No speech recognized"
                                SpeechRecognizer.ERROR_NETWORK -> "Network error during recognition"
                                SpeechRecognizer.ERROR_AUDIO -> "Audio recording error"
                                else -> "Speech recognition error ()"
                            }
                            onError?.invoke(msg)
                        }
                        override fun onResults(results: Bundle?) {
                            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                            val finalSpeech = matches?.firstOrNull() ?: ""
                            stopListening()
                            if (finalSpeech.isNotBlank()) {
                                onTranscriptReceived?.invoke(finalSpeech, true)
                            }
                        }
                        override fun onPartialResults(partialResults: Bundle?) {
                            val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                            val interim = matches?.firstOrNull() ?: ""
                            if (interim.isNotBlank()) {
                                onTranscriptReceived?.invoke(interim, false)
                            }
                        }
                        override fun onEvent(eventType: Int, params: Bundle?) {}
                    })
                }

                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, languageCode)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, languageCode)
                    putExtra(RecognizerIntent.EXTRA_SUPPORTED_LANGUAGES, arrayListOf("en-IN", "hi-IN", "en-US"))
                }

                speechRecognizer?.startListening(intent)
            } catch (e: Exception) {
                onError?.invoke("Failed to start speech recognizer: ")
            }
        }
    }

    private fun startAmplitudeMeter() {
        meterJob?.cancel()
        meterJob = scope.launch {
            val sampleRate = 16000
            val channelConfig = AudioFormat.CHANNEL_IN_MONO
            val audioFormat = AudioFormat.ENCODING_PCM_16BIT
            val minBuf = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
            if (minBuf <= 0) return@launch

            try {
                audioRecord = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    sampleRate,
                    channelConfig,
                    audioFormat,
                    minBuf
                )
                audioRecord?.startRecording()
                val buffer = ShortArray(minBuf)

                while (isActive && isListening) {
                    val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                    if (read > 0) {
                        var sum = 0.0
                        for (i in 0 until read) {
                            sum += buffer[i] * buffer[i]
                        }
                        val rms = sqrt(sum / read).toFloat()
                        val level = (rms / 32768.0f * 5.0f).coerceIn(0.0f, 1.0f)
                        _micLevel.value = level
                    }
                    delay(50)
                }
            } catch (e: SecurityException) {
                // Handled if permission not yet granted
            } finally {
                try {
                    audioRecord?.stop()
                    audioRecord?.release()
                } catch (ignored: Exception) {}
                audioRecord = null
            }
        }
    }

    fun stopListening() {
        isListening = false
        meterJob?.cancel()
        _micLevel.value = 0.0f
        CoroutineScope(Dispatchers.Main).launch {
            try {
                speechRecognizer?.stopListening()
                speechRecognizer?.destroy()
            } catch (ignored: Exception) {}
            speechRecognizer = null
        }
    }

    fun isListening(): Boolean = isListening
}
