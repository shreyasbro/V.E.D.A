"""
V.E.D.A. Hardware Subsystem: Real Microphone & Camera
Features:
- Dynamic physical audio device discovery & smart selection (Realtek / USB / Headset / Bluetooth).
- Dynamic hot-swap resilience: auto-recovery if selected device changes or disconnects.
- Real-time persistent sounddevice InputStream for Always-On mode (zero latency / no open-close loop).
- Live real-time audio amplitude metering & Voice Activity Detection (VAD).
- Exact Pipeline States:
  MIC_OFF, MIC_INITIALIZING, MIC_READY, HEARING, SPEECH_DETECTED, PROCESSING, SPEAKING, MIC_ERROR.
- High-accuracy multilingual speech recognition: Hindi (hi-IN), Hinglish (en-IN/hi-IN), English (en-IN/en-US).
- Integrated language metadata: passes raw_transcript, clean_text, and language_mode.
- Instant barge-in speech interruption support.
- In-memory WAV buffering directly into speech_recognition.AudioData (strictly 0 disk writes).
- Detailed diagnostic telemetry.
- Temporary Camera frame acquisition in RAM via OpenCV.
"""

import io
import time
import wave
import queue
import threading
from typing import Any, Callable, Dict, List, Optional
import numpy as np
from PIL import Image

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from veda.permissions import PermissionGuard
from veda.language import detect_language, normalize_hinglish, process_voice_transcript


class MicrophoneDiagnostics:
    """Diagnostic logger tracking the exact state and points of audio operations."""
    def __init__(self):
        self.last_status = {
            "permission": "unknown",
            "device": "unknown",
            "device_id": None,
            "sample_rate": 16000,
            "channels": 1,
            "stream_opened": False,
            "frames_received": 0,
            "peak_rms": 0.0,
            "speech_detected": False,
            "stt_attempted": False,
            "stt_success": False,
            "transcript": "",
            "language_mode": "ENGLISH",
            "error": None
        }

    def update(self, **kwargs):
        self.last_status.update(kwargs)

    def get_summary(self) -> str:
        s = self.last_status
        return (
            f"Permission: {s['permission']} | Device: {s['device']} (ID {s['device_id']}) | "
            f"Stream: {'OK' if s['stream_opened'] else 'FAILED'} | Frames: {s['frames_received']} | "
            f"Peak RMS: {s['peak_rms']:.4f} | Speech: {'YES' if s['speech_detected'] else 'NO'} | "
            f"Lang: {s['language_mode']} | "
            f"STT: {'OK' if s['stt_success'] else ('FAILED' if s['stt_attempted'] else 'N/A')}"
        )


class MicrophoneSubsystem:
    """
    High-reliability microphone input engine with persistent streaming,
    dynamic device selection, adaptive VAD, and dual-pass multilingual STT.
    """

    def __init__(self):
        self.diagnostics = MicrophoneDiagnostics()
        self.selected_device_id: Optional[int] = None
        self._recognizer = sr.Recognizer() if HAS_SR else None
        if self._recognizer:
            self._recognizer.energy_threshold = 280
            self._recognizer.dynamic_energy_threshold = False

        self.is_listening = False
        self.is_always_on = False

        # Persistent stream management
        self._stream: Optional[Any] = None
        self._audio_queue: queue.Queue = queue.Queue(maxsize=160)
        self._always_on_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._always_on_stop_event = threading.Event()
        self._lock = threading.Lock()

        # VAD & Capture Tuning parameters
        self.sample_rate = 16000
        self.block_size = 1024
        self.hearing_threshold = 0.005  # RMS threshold for environmental sound / mic hearing
        self.speech_threshold = 0.015   # RMS threshold for clear speech start
        self.silence_timeout = 1.3      # Seconds of silence after speech before utterance completion
        self.max_phrase_time = 12.0     # Maximum utterance length
        self.min_phrase_time = 0.35     # Minimum speech duration to discard clicks/pops

        # Callbacks
        # States: "MIC_OFF", "MIC_INITIALIZING", "MIC_READY", "HEARING", "SPEECH_DETECTED", "PROCESSING", "SPEAKING", "MIC_ERROR"
        self.on_state_change: Optional[Callable[[str], None]] = None
        self.on_level_change: Optional[Callable[[float], None]] = None
        self.on_speech_started: Optional[Callable[[], None]] = None
        self.on_speech_recognized: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_interim_transcript: Optional[Callable[[str], None]] = None

        self._last_level_emit_time = 0.0
        self._last_interim_emit_time = 0.0

        # Auto-detect best physical device
        self._auto_select_best_device()

    def _auto_select_best_device(self) -> Optional[int]:
        """
        Discovers input devices dynamically and chooses the primary physical microphone
        (Realtek, headset, USB, or Windows default) over virtual/streaming mappers.
        """
        if not HAS_SOUNDDEVICE:
            return None
        try:
            devices = sd.query_devices()
            best_id = None

            # Priority 1: Physical Realtek Audio or Microphone Array
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", "").lower()
                    host = dev.get("hostapi", 0)
                    if ("realtek" in name or "microphone array" in name) and "steam" not in name and host in [0, 1, 2]:
                        best_id = idx
                        break

            # Priority 2: Any external USB, Headset, or Bluetooth microphone
            if best_id is None:
                for idx, dev in enumerate(devices):
                    if dev.get("max_input_channels", 0) > 0:
                        name = dev.get("name", "").lower()
                        if any(k in name for k in ["usb", "headset", "headphone", "hands-free"]) and "steam" not in name:
                            best_id = idx
                            break

            # Priority 3: Fallback to any physical microphone not mapped to Steam
            if best_id is None:
                for idx, dev in enumerate(devices):
                    if dev.get("max_input_channels", 0) > 0:
                        name = dev.get("name", "").lower()
                        if "microphone" in name and "steam" not in name:
                            best_id = idx
                            break

            # Priority 4: Windows Default input device
            if best_id is None:
                default_in = sd.default.device[0]
                if default_in is not None and default_in >= 0:
                    best_id = default_in

            self.selected_device_id = best_id
            return best_id
        except Exception:
            self.selected_device_id = None
            return None

    def get_input_devices(self) -> List[Dict[str, Any]]:
        """Lists available audio input devices with readable metadata."""
        if not HAS_SOUNDDEVICE:
            return [{"id": 0, "name": "Default Microphone", "channels": 1}]
        try:
            devices = sd.query_devices()
            input_devs = []
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    input_devs.append({
                        "id": idx,
                        "name": dev.get("name", f"Microphone {idx}"),
                        "channels": dev.get("max_input_channels"),
                        "default_samplerate": dev.get("default_samplerate"),
                        "is_selected": idx == self.selected_device_id
                    })
            return input_devs
        except Exception:
            return [{"id": 0, "name": "System Default Microphone", "channels": 1}]

    def set_device(self, device_id: int):
        self.selected_device_id = device_id

    def _audio_callback(self, indata, frames, time_info, status):
        """Sounddevice stream callback running in high-priority audio thread."""
        chunk = indata.copy()
        rms = float(np.sqrt(np.mean(chunk**2)))

        now = time.time()
        if now - self._last_level_emit_time >= 0.035:
            self._last_level_emit_time = now
            if self.on_level_change:
                norm_level = min(1.0, rms * 18.0)
                try:
                    self.on_level_change(norm_level)
                except Exception:
                    pass

        try:
            self._audio_queue.put_nowait((chunk, rms))
        except queue.Full:
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait((chunk, rms))
            except Exception:
                pass

    def _recognize_speech_data(self, audio_bytes: bytes) -> Optional[Dict[str, Any]]:
        """
        Multilingual STT supporting Hindi, Hinglish, and English with candidate selection.
        Evaluates recognition across en-IN and hi-IN for maximum bilingual accuracy.
        """
        if not HAS_SR or not self._recognizer:
            return None

        wav_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(wav_io) as source:
            audio_data = self._recognizer.record(source)

        # 1. Primary: Indian English (en-IN) - captures English & Hinglish transliterated words cleanly
        text_en_in = ""
        try:
            text_en_in = self._recognizer.recognize_google(audio_data, language="en-IN").strip()
        except Exception:
            text_en_in = ""

        # 2. Secondary: Hindi (hi-IN)
        text_hi = ""
        try:
            text_hi = self._recognizer.recognize_google(audio_data, language="hi-IN").strip()
        except Exception:
            text_hi = ""

        # 3. Fallback: en-US
        text_en_us = ""
        if not text_en_in and not text_hi:
            try:
                text_en_us = self._recognizer.recognize_google(audio_data, language="en-US").strip()
            except Exception:
                text_en_us = ""

        # Candidate selection
        chosen_raw = ""
        has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in text_hi)
        if text_hi and has_devanagari and (not text_en_in or len(text_en_in) < 3):
            chosen_raw = text_hi
        elif text_en_in:
            chosen_raw = text_en_in
        elif text_hi:
            chosen_raw = text_hi
        elif text_en_us:
            chosen_raw = text_en_us

        if not chosen_raw:
            return None

        # Run language classification and light Hinglish normalization
        payload = process_voice_transcript(chosen_raw)
        return payload

    def _run_interim_stt(self, frames: List[Any]):
        """Runs fast in-memory partial STT and yields interim transcript to UI."""
        if not HAS_SR or not self._recognizer or not self.on_interim_transcript:
            return
        try:
            audio_array = np.concatenate(frames, axis=0)
            int_data = (audio_array * 32767).astype(np.int16)
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(int_data.tobytes())
            wav_io.seek(0)
            with sr.AudioFile(wav_io) as src:
                aud = self._recognizer.record(src)
            text = self._recognizer.recognize_google(aud, language="en-IN").strip()
            if text and self.on_interim_transcript:
                self.on_interim_transcript(text)
        except Exception:
            pass

    def listen_once_vad(self, timeout: float = 6.0, phrase_time_limit: float = 12.0) -> Dict[str, Any]:
        """
        Listens for a single complete utterance in Mic Toggle mode.
        Starts stream, gathers audio via VAD in RAM, processes STT, and returns.
        """
        if not PermissionGuard.check_permission("microphone"):
            self.diagnostics.update(permission="DENIED", error="Microphone permission disabled in V.E.D.A.")
            if self.on_state_change:
                self.on_state_change("MIC_OFF")
            return {
                "success": False,
                "permission_denied": True,
                "error": "Permission Denied: Microphone Access is currently disabled in V.E.D.A. Permissions."
            }

        self.diagnostics.update(permission="GRANTED", error=None, stt_attempted=False, stt_success=False)

        if not HAS_SOUNDDEVICE or not HAS_SR:
            err = "sounddevice or speech_recognition module is missing."
            self.diagnostics.update(error=err)
            if self.on_state_change:
                self.on_state_change("MIC_ERROR")
            return {"success": False, "error": err}

        if self.on_state_change:
            self.on_state_change("MIC_INITIALIZING")

        self._auto_select_best_device()

        device_name = "Default"
        try:
            if self.selected_device_id is not None:
                dev_info = sd.query_devices(self.selected_device_id)
                device_name = dev_info.get("name", str(self.selected_device_id))
        except Exception:
            pass

        self.diagnostics.update(device=device_name, device_id=self.selected_device_id)

        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except Exception:
                break

        self._stop_event.clear()
        self.is_listening = True

        captured_frames = []
        speech_started = False
        silence_start_time: Optional[float] = None
        start_time = time.time()
        peak_rms = 0.0
        frame_count = 0

        if self.on_state_change:
            self.on_state_change("MIC_READY")

        try:
            with sd.InputStream(
                device=self.selected_device_id,
                channels=1,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                callback=self._audio_callback
            ):
                self.diagnostics.update(stream_opened=True)

                while not self._stop_event.is_set():
                    try:
                        chunk, rms = self._audio_queue.get(timeout=0.08)
                    except queue.Empty:
                        continue

                    frame_count += 1
                    if rms > peak_rms:
                        peak_rms = rms

                    elapsed = time.time() - start_time

                    if not speech_started:
                        if rms >= self.speech_threshold:
                            speech_started = True
                            if self.on_state_change:
                                self.on_state_change("SPEECH_DETECTED")
                            if self.on_speech_started:
                                try:
                                    self.on_speech_started()
                                except Exception:
                                    pass
                            captured_frames.append(chunk)
                        elif rms >= self.hearing_threshold:
                            if self.on_state_change:
                                self.on_state_change("HEARING")
                            captured_frames.append(chunk)
                            if len(captured_frames) > 8:
                                captured_frames.pop(0)
                        else:
                            if self.on_state_change:
                                self.on_state_change("MIC_READY")

                        if elapsed > timeout:
                            break
                    else:
                        captured_frames.append(chunk)
                        if self.on_state_change:
                            self.on_state_change("SPEECH_DETECTED")

                        if rms < self.speech_threshold * 0.75:
                            if silence_start_time is None:
                                silence_start_time = time.time()
                            elif (time.time() - silence_start_time) >= self.silence_timeout:
                                break
                        else:
                            silence_start_time = None

                        if elapsed > phrase_time_limit:
                            break

        except Exception as e:
            self.diagnostics.update(stream_opened=False, error=str(e))
            self.is_listening = False
            if self.on_state_change:
                self.on_state_change("MIC_ERROR")
            return {"success": False, "error": f"Audio stream error: {str(e)}", "diagnostics": self.diagnostics.get_summary()}
        finally:
            self.is_listening = False

        self.diagnostics.update(
            frames_received=frame_count,
            peak_rms=peak_rms,
            speech_detected=speech_started
        )

        if not speech_started or len(captured_frames) == 0:
            if self.on_state_change:
                self.on_state_change("MIC_READY")
            return {
                "success": False,
                "error": "No speech detected.",
                "diagnostics": self.diagnostics.get_summary()
            }

        # Processing Speech -> STT
        if self.on_state_change:
            self.on_state_change("PROCESSING")

        self.diagnostics.update(stt_attempted=True)

        try:
            audio_array = np.concatenate(captured_frames, axis=0)
            int_data = (audio_array * 32767).astype(np.int16)

            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(int_data.tobytes())
            wav_bytes = wav_io.getvalue()

            payload = self._recognize_speech_data(wav_bytes)
            if not payload or not payload.get("clean_text"):
                self.diagnostics.update(stt_success=False, error="Speech recognition could not understand audio.")
                if self.on_state_change:
                    self.on_state_change("MIC_READY")
                return {
                    "success": False,
                    "error": "Speech recognition could not understand audio.",
                    "diagnostics": self.diagnostics.get_summary()
                }

            clean_text = payload["clean_text"]
            lang_mode = payload.get("language_mode", "ENGLISH")
            self.diagnostics.update(stt_success=True, transcript=clean_text, language_mode=lang_mode)
            if self.on_state_change:
                self.on_state_change("MIC_READY")

            if self.on_speech_recognized:
                self.on_speech_recognized(payload)

            return {
                "success": True,
                "text": clean_text,
                "raw_text": payload.get("raw_transcript", clean_text),
                "language_mode": lang_mode,
                "diagnostics": self.diagnostics.get_summary()
            }

        except Exception as e:
            self.diagnostics.update(stt_success=False, error=str(e))
            if self.on_state_change:
                self.on_state_change("MIC_ERROR")
            return {
                "success": False,
                "error": f"Speech processing error: {str(e)}",
                "diagnostics": self.diagnostics.get_summary()
            }

    def start_always_on(self, on_utterance: Callable[[Dict[str, Any]], None], is_busy_fn: Optional[Callable[[], bool]] = None):
        """
        Starts the continuous Always-On conversation loop with a single persistent stream.
        No repeated open/close cycles; captures utterances as soon as user speaks.
        """
        self.stop_always_on()

        if not PermissionGuard.check_permission("microphone"):
            if self.on_state_change:
                self.on_state_change("MIC_OFF")
            return

        self.is_always_on = True
        self._always_on_stop_event.clear()

        def _persistent_worker():
            if not HAS_SOUNDDEVICE:
                if self.on_state_change:
                    self.on_state_change("MIC_ERROR")
                return

            if self.on_state_change:
                self.on_state_change("MIC_INITIALIZING")

            self._auto_select_best_device()

            if self.on_state_change:
                self.on_state_change("MIC_READY")

            try:
                stream = sd.InputStream(
                    device=self.selected_device_id,
                    channels=1,
                    samplerate=self.sample_rate,
                    blocksize=self.block_size,
                    callback=self._audio_callback
                )
            except Exception as err:
                self.diagnostics.update(stream_opened=False, error=str(err))
                if self.on_state_change:
                    self.on_state_change("MIC_ERROR")
                return

            self._stream = stream
            stream.start()
            self.diagnostics.update(stream_opened=True)

            captured_frames = []
            pre_speech_buffer = []
            speech_started = False
            speech_start_time = 0.0
            silence_start_time: Optional[float] = None

            try:
                while not self._always_on_stop_event.is_set():
                    # If assistant is speaking or thinking, discard audio to avoid self-hearing
                    if is_busy_fn and is_busy_fn():
                        while not self._audio_queue.empty():
                            try:
                                self._audio_queue.get_nowait()
                            except Exception:
                                break
                        captured_frames.clear()
                        pre_speech_buffer.clear()
                        speech_started = False
                        silence_start_time = None
                        time.sleep(0.04)
                        continue

                    try:
                        chunk, rms = self._audio_queue.get(timeout=0.08)
                    except queue.Empty:
                        continue

                    now = time.time()

                    if not speech_started:
                        pre_speech_buffer.append(chunk)
                        if len(pre_speech_buffer) > 6:
                            pre_speech_buffer.pop(0)

                        if rms >= self.speech_threshold:
                            speech_started = True
                            speech_start_time = now
                            silence_start_time = None
                            if self.on_state_change:
                                self.on_state_change("SPEECH_DETECTED")
                            if self.on_speech_started:
                                try:
                                    self.on_speech_started()
                                except Exception:
                                    pass
                            captured_frames = list(pre_speech_buffer)
                            captured_frames.append(chunk)
                        elif rms >= self.hearing_threshold:
                            if self.on_state_change:
                                self.on_state_change("HEARING")
                        else:
                            if self.on_state_change:
                                self.on_state_change("MIC_READY")
                    else:
                        captured_frames.append(chunk)
                        if self.on_state_change:
                            self.on_state_change("SPEECH_DETECTED")

                        # Emit real-time interim transcript every 0.7s of speech
                        if self.on_interim_transcript and (now - self._last_interim_emit_time) >= 0.75 and len(captured_frames) > 12:
                            self._last_interim_emit_time = now
                            threading.Thread(
                                target=self._run_interim_stt,
                                args=(list(captured_frames),),
                                daemon=True
                            ).start()

                        if rms < self.speech_threshold * 0.75:
                            if silence_start_time is None:
                                silence_start_time = now
                            elif (now - silence_start_time) >= self.silence_timeout:
                                # Utterance completed
                                duration = now - speech_start_time
                                if duration >= self.min_phrase_time and len(captured_frames) > 0:
                                    if self.on_state_change:
                                        self.on_state_change("PROCESSING")

                                    try:
                                        audio_array = np.concatenate(captured_frames, axis=0)
                                        int_data = (audio_array * 32767).astype(np.int16)
                                        wav_io = io.BytesIO()
                                        with wave.open(wav_io, "wb") as wf:
                                            wf.setnchannels(1)
                                            wf.setsampwidth(2)
                                            wf.setframerate(self.sample_rate)
                                            wf.writeframes(int_data.tobytes())
                                        payload = self._recognize_speech_data(wav_io.getvalue())
                                        if payload and payload.get("clean_text"):
                                            on_utterance(payload)
                                    except Exception as stt_e:
                                        print(f"[Always-On STT Error] {stt_e}")

                                # Reset for next utterance
                                captured_frames.clear()
                                pre_speech_buffer.clear()
                                speech_started = False
                                silence_start_time = None
                                if self.on_state_change:
                                    self.on_state_change("MIC_READY")
                        else:
                            silence_start_time = None

                        if (now - speech_start_time) > self.max_phrase_time:
                            # Phrase exceeded max limit, finalize
                            try:
                                audio_array = np.concatenate(captured_frames, axis=0)
                                int_data = (audio_array * 32767).astype(np.int16)
                                wav_io = io.BytesIO()
                                with wave.open(wav_io, "wb") as wf:
                                    wf.setnchannels(1)
                                    wf.setsampwidth(2)
                                    wf.setframerate(self.sample_rate)
                                    wf.writeframes(int_data.tobytes())
                                payload = self._recognize_speech_data(wav_io.getvalue())
                                if payload and payload.get("clean_text"):
                                    on_utterance(payload)
                            except Exception:
                                pass
                            captured_frames.clear()
                            pre_speech_buffer.clear()
                            speech_started = False
                            silence_start_time = None
                            if self.on_state_change:
                                self.on_state_change("MIC_READY")

            finally:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                self._stream = None
                self.is_always_on = False
                if self.on_state_change:
                    self.on_state_change("MIC_OFF")

        self._always_on_thread = threading.Thread(target=_persistent_worker, daemon=True)
        self._always_on_thread.start()

    def stop_always_on(self):
        """Stops the continuous Always-On loop and releases the audio stream."""
        self.is_always_on = False
        self._always_on_stop_event.set()
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self.on_state_change:
            self.on_state_change("MIC_OFF")

    def stop_listening(self):
        """Aborts active listening session."""
        self._stop_event.set()
        self.is_listening = False
        if self.on_state_change:
            self.on_state_change("MIC_OFF")


class CameraSubsystem:
    """
    Controls camera frame acquisition, streaming preview, and device state directly in RAM.
    Strictly zero disk writes for temporary camera perception.
    Managed camera states:
    - CAMERA_OFF
    - CAMERA_STARTING
    - CAMERA_READY
    - CAMERA_ACTIVE
    - CAMERA_ERROR
    - CAMERA_NOT_DETECTED
    - CAMERA_IN_USE
    """

    def __init__(self):
        self.state: str = "CAMERA_OFF"
        self.is_streaming: bool = False
        self.active_camera_index: int = 0
        self.on_state_change: Optional[Callable[[str], None]] = None
        self.on_frame_received: Optional[Callable[[Image.Image], None]] = None
        
        # Orientation & Distortion Controls (Normal by default: no mirror, no vertical flip, rotation 0)
        from veda.config import VedaConfig
        _settings = VedaConfig.get_settings()
        self.mirror: bool = bool(_settings.get("camera_mirror", False))
        self.vertical_flip: bool = False
        self.rotation: int = int(_settings.get("camera_rotation", 0))

        # Runtime Diagnostics
        self.diagnostics: Dict[str, Any] = {
            "resolution": "Unknown",
            "fps": 0.0,
            "mirror": self.mirror,
            "rotation": self.rotation,
            "frames_captured": 0,
            "last_capture_time": None,
            "last_error": None
        }

        self._cap: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._latest_frame: Optional[Image.Image] = None
        self._lock = threading.Lock()
        self._fps_counter = 0
        self._fps_start_time = time.time()

    def set_orientation(self, mirror: Optional[bool] = None, rotation: Optional[int] = None):
        """Configures preview and capture orientation dynamically."""
        from veda.config import VedaConfig
        if mirror is not None:
            self.mirror = mirror
            self.diagnostics["mirror"] = mirror
            VedaConfig.update_setting("camera_mirror", mirror)
        if rotation is not None:
            if rotation in [0, 90, 180, 270]:
                self.rotation = rotation
                self.diagnostics["rotation"] = rotation
                VedaConfig.update_setting("camera_rotation", rotation)
        
        mode_str = "Normal"
        if self.mirror:
            mode_str = f"Mirrored ({self.rotation}°)" if self.rotation else "Mirrored"
        elif self.rotation:
            mode_str = f"Rotated {self.rotation}°"
        VedaConfig.update_setting("camera_orientation", mode_str)

    def transform_frame(self, pil_img: Image.Image) -> Image.Image:
        """
        Applies configured rotation and mirror transformations identically to preview and vision capture.
        Strictly preserves true orientation without accidental mirroring or flipping.
        """
        img = pil_img
        if self.rotation == 90:
            img = img.transpose(Image.Transpose.ROTATE_270)
        elif self.rotation == 180:
            img = img.transpose(Image.Transpose.ROTATE_180)
        elif self.rotation == 270:
            img = img.transpose(Image.Transpose.ROTATE_90)

        if self.mirror:
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        if self.vertical_flip:
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        return img

    def get_diagnostics(self) -> Dict[str, Any]:
        """Returns live hardware & capture telemetry for UI and debugging."""
        with self._lock:
            return dict(self.diagnostics)

    def _set_state(self, new_state: str):
        self.state = new_state
        if self.on_state_change:
            try:
                self.on_state_change(new_state)
            except Exception as e:
                print(f"[CameraSubsystem] State callback error: {e}")

    @staticmethod
    def get_cameras() -> List[Dict[str, Any]]:
        """Discovers available video cameras without locking devices."""
        if not HAS_CV2:
            return []
        cameras = []
        for idx in range(4):
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap.isOpened():
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
                    cameras.append({
                        "id": idx,
                        "name": f"Integrated / USB Camera ({idx})",
                        "resolution": f"{w}x{h}"
                    })
                    cap.release()
            except Exception:
                pass
        return cameras

    def get_default_camera_index(self) -> int:
        """Auto-selects the first functioning camera index (handles missing index 0)."""
        cams = self.get_cameras()
        if cams:
            return cams[0]["id"]
        return 0

    def get_latest_frame(self) -> Optional[Image.Image]:
        """Returns the latest captured frame in RAM."""
        with self._lock:
            return self._latest_frame

    def capture_frame(self, camera_index: Optional[int] = None) -> Dict[str, Any]:
        """
        Captures a fresh camera frame directly into a PIL Image in RAM.
        Strictly zero disk writes. Applies configured orientation transforms.
        Guarded by camera permission.
        """
        PermissionGuard.require("camera", action_name="Camera Frame Capture")

        if not HAS_CV2:
            self._set_state("CAMERA_ERROR")
            self.diagnostics["last_error"] = "OpenCV (cv2) is not available."
            return {"success": False, "error": "OpenCV (cv2) is not available."}

        target_idx = camera_index if camera_index is not None else self.get_default_camera_index()
        self._set_state("CAMERA_STARTING")

        cap = None
        try:
            # If already streaming, flush buffer to obtain freshest real-time frame
            if self.is_streaming and self._cap and self._cap.isOpened():
                for _ in range(2):
                    self._cap.grab()
                ret, frame = self._cap.read()
                if ret and frame is not None:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    raw_pil = Image.fromarray(rgb)
                    transformed_pil = self.transform_frame(raw_pil)
                    width, height = transformed_pil.size
                    with self._lock:
                        self._latest_frame = transformed_pil
                        self.diagnostics["resolution"] = f"{width}x{height}"
                        self.diagnostics["frames_captured"] += 1
                        self.diagnostics["last_capture_time"] = time.time()
                    return {
                        "success": True,
                        "image": transformed_pil,
                        "dimensions": [width, height],
                        "action": "camera_capture"
                    }

            cap = cv2.VideoCapture(target_idx, cv2.CAP_DSHOW)
            if not cap.isOpened():
                self._set_state("CAMERA_NOT_DETECTED")
                self.diagnostics["last_error"] = f"Could not open camera {target_idx}."
                return {"success": False, "error": f"Could not open camera {target_idx}."}

            # Flush 3 initial auto-exposure/buffer frames to ensure clear, fresh capture
            for _ in range(3):
                ret, frame = cap.read()
                if not ret:
                    break

            ret, frame = cap.read()
            if not ret or frame is None:
                self._set_state("CAMERA_ERROR")
                self.diagnostics["last_error"] = "Failed to grab camera frame."
                return {"success": False, "error": "Failed to grab camera frame."}

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            raw_pil = Image.fromarray(rgb)
            transformed_pil = self.transform_frame(raw_pil)
            width, height = transformed_pil.size

            with self._lock:
                self._latest_frame = transformed_pil
                self.diagnostics["resolution"] = f"{width}x{height}"
                self.diagnostics["frames_captured"] += 1
                self.diagnostics["last_capture_time"] = time.time()

            self._set_state("CAMERA_READY")
            return {
                "success": True,
                "image": transformed_pil,
                "dimensions": [width, height],
                "action": "camera_capture"
            }
        except Exception as e:
            self._set_state("CAMERA_ERROR")
            self.diagnostics["last_error"] = str(e)
            return {"success": False, "error": str(e)}
        finally:
            if cap and cap.isOpened():
                cap.release()

    def start_preview(self, camera_index: Optional[int] = None) -> bool:
        """Starts live camera video stream in dedicated background thread."""
        PermissionGuard.require("camera", action_name="Camera Live Stream")

        if not HAS_CV2:
            self._set_state("CAMERA_ERROR")
            return False

        if self.is_streaming:
            return True

        self.active_camera_index = camera_index if camera_index is not None else self.get_default_camera_index()
        self._stop_event.clear()
        self._set_state("CAMERA_STARTING")

        try:
            self._cap = cv2.VideoCapture(self.active_camera_index, cv2.CAP_DSHOW)
            if not self._cap.isOpened():
                self._set_state("CAMERA_NOT_DETECTED")
                return False

            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
            self.diagnostics["resolution"] = f"{w}x{h}"
            self._fps_counter = 0
            self._fps_start_time = time.time()

            self.is_streaming = True
            self._set_state("CAMERA_ACTIVE")

            self._thread = threading.Thread(target=self._stream_worker, daemon=True)
            self._thread.start()
            return True
        except Exception as e:
            print(f"[CameraSubsystem] Start preview error: {e}")
            self._set_state("CAMERA_ERROR")
            self.stop_preview()
            return False

    def _stream_worker(self):
        """Dedicated thread continuously pulling frames into RAM for preview."""
        while not self._stop_event.is_set() and self._cap and self._cap.isOpened():
            try:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    time.sleep(0.03)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                raw_pil = Image.fromarray(rgb)
                # Apply orientation transform (normal by default, user-configurable mirror/rotation)
                transformed_pil = self.transform_frame(raw_pil)

                with self._lock:
                    self._latest_frame = transformed_pil
                    self._fps_counter += 1
                    elapsed = time.time() - self._fps_start_time
                    if elapsed >= 1.0:
                        self.diagnostics["fps"] = round(self._fps_counter / elapsed, 1)
                        self._fps_counter = 0
                        self._fps_start_time = time.time()

                if self.on_frame_received:
                    try:
                        self.on_frame_received(transformed_pil)
                    except Exception:
                        pass

                time.sleep(0.033)  # ~30 FPS
            except Exception as e:
                print(f"[CameraSubsystem] Stream read loop error: {e}")
                break

        self.is_streaming = False
        self._set_state("CAMERA_OFF")

    def stop_preview(self):
        """Safely stops active preview and releases camera hardware."""
        self._stop_event.set()
        self.is_streaming = False
        
        if self._cap:
            try:
                if self._cap.isOpened():
                    self._cap.release()
            except Exception:
                pass
            self._cap = None

        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=0.5)
            except Exception:
                pass
            self._thread = None

        self._set_state("CAMERA_OFF")


# Global singletons
microphone_subsystem = MicrophoneSubsystem()
camera_subsystem = CameraSubsystem()
