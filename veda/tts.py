"""
V.E.D.A. Text-To-Speech (TTS) Engine — Powered by Local Kokoro TTS
Primary, Default, and Offline-Capable Speech Engine.
Zero external API calls. Zero API keys. Zero cloud dependencies.
"""

import os
import io
import re
import time
import queue
import threading
from typing import Optional, Callable, List, Dict, Any
from abc import ABC, abstractmethod

from veda.config import VedaConfig
from veda.language import prepare_text_for_tts
from veda.kokoro_provider import KokoroLocalTTSProvider


class TTSProvider(ABC):
    """Abstract interface for speech synthesis engines."""

    @abstractmethod
    def speak_sync(self, text: str, language_mode: str = "ENGLISH") -> bool:
        """Synthesizes and plays audio. Returns True on success, False on failure."""
        pass

    @abstractmethod
    def stop(self):
        """Immediately interrupts any active playback."""
        pass

    @abstractmethod
    def set_volume(self, volume: float):
        pass


class TTSEngine:
    """
    Thread-safe V.E.D.A. Local Speech Synthesizer:
    - Primary & Sole TTS Provider: Kokoro ONNX Local Engine
    - Offline-capable: Operates completely offline without requiring internet.
    - Low-latency sentence/phrase streaming.
    - Instant barge-in speech interruption support.
    - Memory-efficient in-RAM playback (zero persistent disk writes).
    """

    def __init__(self):
        self.kokoro_provider: KokoroLocalTTSProvider = KokoroLocalTTSProvider()
        self.last_provider_used: str = "Kokoro TTS"
        self.last_voice_used: str = "af_heart"
        self.last_language_detected: str = "None"
        self.last_tts_error: str = "None"

        self._is_speaking = False
        self._lock = threading.Lock()
        self._speech_thread = None
        self._abort_requested = False

        self.on_speech_started = None
        self.on_speech_finished = None

        self.reload_config()

    def reload_config(self):
        """Refreshes voice and configuration for Kokoro TTS."""
        if self.kokoro_provider:
            self.kokoro_provider.reload_config()
            self.last_voice_used = self.kokoro_provider.selected_voice

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    @property
    def active_engine_name(self) -> str:
        if self.kokoro_provider and self.kokoro_provider.is_available():
            return "Kokoro TTS (Local / Offline)"
        return "Kokoro TTS (Not Installed)"

    @property
    def volume(self) -> float:
        try:
            import pygame
            if pygame.mixer.get_init():
                return float(pygame.mixer.music.get_volume())
        except Exception:
            pass
        return 0.85

    def get_diagnostics(self) -> dict:
        k_diag = self.kokoro_provider.get_diagnostics() if self.kokoro_provider else {}
        return {
            "tts_engine": "Kokoro",
            "tts_provider": "Kokoro Local TTS",
            "model": "kokoro-v1.0.onnx",
            "voice": k_diag.get("selected_voice", "af_heart"),
            "language": self.last_language_detected if self.last_language_detected != "None" else "English / Hindi / Hinglish",
            "device": k_diag.get("device", "CPU"),
            "model_path": k_diag.get("model_path", ""),
            "status": k_diag.get("status", "NOT INITIALIZED"),
            "last_error": k_diag.get("last_error", "None"),
            "last_latency_ms": k_diag.get("last_latency_ms"),
            "last_audio_duration_sec": k_diag.get("last_audio_duration_sec"),
            "output_device": k_diag.get("output_device", "Default Windows Device"),
            "is_installed": k_diag.get("is_installed", False),
            "available_voices": k_diag.get("available_voices", []),
            "speed": k_diag.get("speed", 1.0)
        }

    def get_detailed_diagnostics(self) -> dict:
        return self.get_diagnostics()

    def test_voice(self, phrase_type: str = "english") -> tuple[bool, str]:
        """Runs authentic Kokoro voice test across English, Hindi, or Hinglish."""
        if not self.kokoro_provider:
            return False, "Kokoro TTS provider not initialized."
        return self.kokoro_provider.test_voice(phrase_type)

    def clean_text_for_speech(self, text: str) -> str:
        """Strips markdown code blocks, backticks, URLs, table lines, and raw action tags."""
        if not text:
            return ""
        t = re.sub(r"```[\s\S]*?```", " ", text)
        t = re.sub(r"`([^`]+)`", r" ", t)
        t = re.sub(r"https?://\S+", "link", t)
        t = re.sub(r"[#*_~]", "", t)
        t = re.sub(r"^[ \t]*[-+*]\s+", "", t, flags=re.MULTILINE)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def segment_response(self, text: str) -> List[str]:
        """
        Splits responses into natural conversational chunks by sentence boundaries
        so Kokoro synthesis begins immediately with low latency.
        """
        if len(text) < 100:
            return [text]

        raw_parts = re.split(r"([.!?\n]+)", text)
        chunks = []
        current = ""
        for i in range(0, len(raw_parts), 2):
            part = raw_parts[i].strip()
            punct = raw_parts[i+1].strip() if i+1 < len(raw_parts) else ""
            sentence = f"{part} {punct}".strip()
            if not sentence:
                continue

            if len(current) + len(sentence) < 130:
                current = f"{current} {sentence}".strip()
            else:
                if current:
                    chunks.append(current)
                current = sentence

        if current:
            chunks.append(current)

        return chunks if chunks else [text]

    def speak(self, text: str, language_mode: str = "ENGLISH", callback_when_done: Optional[Callable[[], None]] = None):
        self.stop()
        clean_text = self.clean_text_for_speech(text)
        if not clean_text:
            if callback_when_done:
                callback_when_done()
            return

        self.last_language_detected = language_mode or "ENGLISH"
        chunks = self.segment_response(clean_text)

        def _worker():
            self._abort_requested = False
            self._is_speaking = True
            if self.on_speech_started:
                try:
                    self.on_speech_started()
                except Exception:
                    pass

            self.reload_config()

            try:
                for chunk in chunks:
                    if self._abort_requested:
                        break

                    if not self.kokoro_provider.is_available():
                        self.last_tts_error = "Kokoro voice engine is not installed yet."
                        print(f"[TTS] {self.last_tts_error}")
                        break

                    success = self.kokoro_provider.speak_sync(chunk, language_mode=language_mode)
                    if success:
                        self.last_provider_used = "Kokoro TTS"
                        self.last_voice_used = self.kokoro_provider.selected_voice
                        self.last_tts_error = "None"
                    else:
                        self.last_tts_error = self.kokoro_provider.last_error
                        print(f"[TTS] Kokoro speech chunk failed: {self.last_tts_error}")
                        break

            except Exception as e:
                self.last_tts_error = str(e)
                print(f"[TTSEngine] Playback error: {e}")
            finally:
                self._is_speaking = False
                if self.on_speech_finished:
                    try:
                        self.on_speech_finished()
                    except Exception:
                        pass
                if callback_when_done and not self._abort_requested:
                    try:
                        callback_when_done()
                    except Exception:
                        pass

        self._speech_thread = threading.Thread(target=_worker, daemon=True)
        self._speech_thread.start()

    def stop(self):
        """Barge-in interruption: immediately halts playback and purges speech queue."""
        self._abort_requested = True
        if self.kokoro_provider:
            self.kokoro_provider.stop()
        self._is_speaking = False

    def set_volume(self, volume: float):
        if self.kokoro_provider:
            self.kokoro_provider.set_volume(volume)


# Global singleton instance
tts_engine = TTSEngine()
