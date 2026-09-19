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
import kotlin.math.sqrt

class VoiceController(
    private val context: Context,
    private val ttsEngine: KokoroTTSEngine
) {
    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false
    private var audioRecord: AudioRecord? = null
    private var meterJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    private val _micState = MutableStateFlow(MicState.MIC_OFF)
    val micState: StateFlow<MicState> = _micState

    private val _micRms = MutableStateFlow(0.0f)
    val micRms: StateFlow<Float> = _micRms

    var onFinalSpeech: ((String) -> Unit)? = null
    var onInterimSpeech: ((String) -> Unit)? = null
    var onErrorOccurred: ((String) -> Unit)? = null

    init {
        ttsEngine.onSpeakingStarted = {
            _micState.value = MicState.SPEAKING
        }
        ttsEngine.onSpeakingFinished = {
            if (_micState.value == MicState.SPEAKING) {
                _micState.value = MicState.MIC_OFF
            }
        }
    }

    fun toggleListening(languageCode: String = "en-IN") {
        if (isListening) {
            stopListening()
        } else {
            startListening(languageCode)
        }
    }

    fun startListening(languageCode: String = "en-IN") {
        // Barge-in: If TTS is speaking when user taps or speaks, stop TTS immediately
        if (ttsEngine.isSpeaking()) {
            ttsEngine.stop()
        }

        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            _micState.value = MicState.MIC_ERROR
            onErrorOccurred?.invoke("Speech recognition service not available on device")
            return
        }

        _micState.value = MicState.MIC_INITIALIZING

        CoroutineScope(Dispatchers.Main).launch {
            try {
                speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
                    setRecognitionListener(object : RecognitionListener {
                        override fun onReadyForSpeech(params: Bundle?) {
                            isListening = true
                            _micState.value = MicState.HEARING
                            startHardwareMeter()
                        }
                        override fun onBeginningOfSpeech() {
                            _micState.value = MicState.SPEECH_DETECTED
                        }
                        override fun onRmsChanged(rmsdB: Float) {
                            val norm = ((rmsdB + 2.0f) / 12.0f).coerceIn(0.0f, 1.0f)
                            _micRms.value = norm
                        }
                        override fun onBufferReceived(buffer: ByteArray?) {}
                        override fun onEndOfSpeech() {
                            _micState.value = MicState.PROCESSING
                        }
                        override fun onError(error: Int) {
                            stopListening()
                            _micState.value = MicState.MIC_ERROR
                            val msg = when (error) {
                                SpeechRecognizer.ERROR_NO_MATCH -> "No speech recognized"
                                SpeechRecognizer.ERROR_NETWORK -> "Network error during recognition"
                                SpeechRecognizer.ERROR_AUDIO -> "Audio recording error"
                                else -> "Speech recognition error ($error)"
                            }
                            onErrorOccurred?.invoke(msg)
                        }
                        override fun onResults(results: Bundle?) {
                            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                            val speech = matches?.firstOrNull() ?: ""
                            stopListening()
                            if (speech.isNotBlank()) {
                                onFinalSpeech?.invoke(speech)
                            }
                        }
                        override fun onPartialResults(partialResults: Bundle?) {
                            val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                            val partial = matches?.firstOrNull() ?: ""
                            if (partial.isNotBlank()) {
                                onInterimSpeech?.invoke(partial)
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
                _micState.value = MicState.MIC_ERROR
                onErrorOccurred?.invoke("Failed to start speech: ${e.message}")
            }
        }
    }

    private fun startHardwareMeter() {
        meterJob?.cancel()
        meterJob = scope.launch {
            val sampleRate = 16000
            val minBuf = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            if (minBuf <= 0) return@launch

            try {
                audioRecord = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    sampleRate,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
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
                        _micRms.value = level
                    }
                    delay(50)
                }
            } catch (e: SecurityException) {
                // Permission not granted
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
        _micRms.value = 0.0f
        _micState.value = MicState.MIC_OFF
        CoroutineScope(Dispatchers.Main).launch {
            try {
                speechRecognizer?.stopListening()
                speechRecognizer?.destroy()
            } catch (ignored: Exception) {}
            speechRecognizer = null
        }
    }
}
