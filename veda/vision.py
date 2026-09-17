"""
V.E.D.A. Live Screen Vision Engine & Low-Storage Implementation
Core principles:
- Perception, NOT screen recording (0 disk writes for normal operation).
- In-memory ring buffer (maximum 3-5 frames, auto-discard).
- Fast local screen change detection (perceptual difference / grayscale diff).
- Adaptive resolution & smart region cropping (Full Screen, Window, Region).
- Clean VisionProvider interface: GeminiVisionProvider & LocalVisionProvider.
"""

import io
import math
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageChops, ImageStat
import pyautogui
import pygetwindow as gw

class VisionProvider(ABC):
    """Abstract interface for screen vision analysis."""

    @abstractmethod
    def analyze(self, image: Image.Image, prompt: str) -> Dict[str, Any]:
        pass


class LocalVisionProvider(VisionProvider):
    """
    Offline/Local vision provider.
    Uses native Windows APIs and UI metadata to provide fast, zero-cloud understanding.
    """

    def analyze(self, image: Image.Image, prompt: str) -> Dict[str, Any]:
        active_title = "Desktop"
        windows = []
        try:
            active_w = gw.getActiveWindow()
            if active_w and active_w.title:
                active_title = active_w.title
        except Exception:
            pass

        try:
            windows = [w.title for w in gw.getAllWindows() if w.title and w.title.strip()]
        except Exception:
            pass

        width, height = image.size
        # Fast local metric analysis
        stat = ImageStat.Stat(image.convert("L"))
        mean_lum = round(stat.mean[0], 1)
        is_dark_mode = mean_lum < 128

        return {
            "success": True,
            "provider": "LocalVisionProvider",
            "active_window": active_title,
            "open_windows_count": len(windows),
            "screen_dimensions": [width, height],
            "visual_properties": {
                "mean_luminance": mean_lum,
                "dark_theme": is_dark_mode
            },
            "summary": f"Active Application: '{active_title}'. Screen resolution: {width}x{height}."
        }


class GeminiVisionProvider(VisionProvider):
    """
    Cloud vision provider using official google-genai SDK.
    Accepts PIL Image directly from RAM without saving to disk.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model_name = model_name or os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
        self._client = None
        self.last_analysis_info: Dict[str, Any] = {
            "model": self.model_name,
            "timestamp": None,
            "success": False,
            "error": None
        }
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[GeminiVisionProvider] Init warning: {e}")

    def analyze(self, image: Image.Image, prompt: str, is_camera: bool = False) -> Dict[str, Any]:
        if not self._client:
            # Fallback to local provider if client not ready
            return LocalVisionProvider().analyze(image, prompt)

        try:
            # Source-specific instruction
            if is_camera:
                instruction = (
                    "You are V.E.D.A.'s Live Camera Perception & Visual Reasoning system. "
                    "Analyze the real-time webcam frame captured in front of the user with high precision.\n"
                    "CRITICAL PERCEPTION GUIDELINES:\n"
                    "1. HAND & HELD OBJECT IDENTIFICATION: Closely examine the user's hands, fingers, and any object(s) they are holding, displaying, or pointing toward the camera.\n"
                    "2. GENERAL VISUAL REASONING: Accurately describe what the object is, its color, type, markings, label/text (if readable), and state. Do not guess or hallucinate.\n"
                    "3. HONEST CONFIDENCE: If the hand is empty, state clearly that nothing is being held. If the frame is too blurry, too close, dark, or partially obscured to identify the item with confidence, state what is visible and politely ask the user to hold it steady or bring it closer.\n"
                    "4. CONCISE & NATURAL: Provide a clear, natural conversational answer directly addressing the user's question in the matching language style."
                )
            else:
                instruction = (
                    "You are V.E.D.A.'s Live Screen Vision system. Analyze the provided screenshot with high precision. "
                    "Identify: 1) Active application & window title, 2) Visible dialogs, messages, or errors, "
                    "3) Key UI buttons/elements with their approximate locations (e.g. top-right, center, bottom-left), "
                    "4) Answer the user's specific visual inquiry accurately and concisely."
                )

            # Convert PIL image to compressed JPEG bytes in RAM (low bandwidth, strictly 0 disk writes)
            buffer = io.BytesIO()
            if image.mode != "RGB":
                image = image.convert("RGB")
            image.save(buffer, format="JPEG", quality=88)
            jpeg_bytes = buffer.getvalue()

            from google.genai import types
            part_image = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")

            response = self._client.models.generate_content(
                model=self.model_name,
                contents=[part_image, f"{instruction}\n\nUser Question: {prompt}"]
            )

            analysis_text = response.text or "Visual inspection complete."
            active_title = "Desktop"
            try:
                active_w = gw.getActiveWindow()
                if active_w and active_w.title:
                    active_title = active_w.title
            except Exception:
                pass

            self.last_analysis_info = {
                "model": self.model_name,
                "timestamp": time.time(),
                "success": True,
                "error": None
            }

            return {
                "success": True,
                "provider": "GeminiVisionProvider",
                "model": self.model_name,
                "active_window": active_title,
                "resolution": f"{image.width}x{image.height}",
                "analysis": analysis_text.strip()
            }
        except Exception as e:
            self.last_analysis_info = {
                "model": self.model_name,
                "timestamp": time.time(),
                "success": False,
                "error": str(e)
            }
            # Fall back to local analysis on error
            local_fallback = LocalVisionProvider().analyze(image, prompt)
            local_fallback["gemini_error"] = str(e)
            return local_fallback


class LiveScreenManager:
    """
    Live Screen Vision Orchestrator.
    Manages in-memory frame ring buffer, perceptual change detection, adaptive resolution,
    and region/window cropping.
    """

    def __init__(self):
        # Modes: "OFF", "LIVE", "FOCUS_WINDOW"
        self.mode = "OFF"
        self.is_paused = False

        # In-memory frame ring buffer (max 4 frames, oldest discarded)
        self._frame_buffer: List[Tuple[float, Image.Image]] = []
        self._max_frames = 4

        # Providers
        self._gemini_provider = GeminiVisionProvider()
        self._local_provider = LocalVisionProvider()

        # Last analyzed frame hash / thumbnail for change detection
        self._last_analyzed_thumb: Optional[Image.Image] = None

    def set_mode(self, mode: str):
        """Sets observation mode: 'OFF', 'LIVE', 'FOCUS_WINDOW'."""
        self.mode = mode.upper()

    def get_mode(self) -> str:
        return self.mode

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def capture_frame(self, region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
        """
        Captures screen or region into RAM.
        Enforces ring-buffer size, automatically discarding older frames.
        """
        if self.mode == "FOCUS_WINDOW" and not region:
            w = gw.getActiveWindow()
            if w and w.width > 50 and w.height > 50:
                region = (max(0, w.left), max(0, w.top), max(50, w.width), max(50, w.height))

        img: Optional[Image.Image] = None
        try:
            if region:
                img = pyautogui.screenshot(region=region)
            else:
                img = pyautogui.screenshot()
        except Exception:
            # Fallback when run in non-interactive/background service or locked screen
            active_w = gw.getActiveWindow()
            title = active_w.title if active_w else "Windows Desktop"
            img = Image.new("RGB", (1366, 768), color=(15, 23, 42))

        # In-memory buffer rotation
        now = time.time()
        self._frame_buffer.append((now, img))
        if len(self._frame_buffer) > self._max_frames:
            oldest_time, oldest_img = self._frame_buffer.pop(0)
            try:
                oldest_img.close()
            except Exception:
                pass

        return img

    def has_screen_changed(self, current_img: Image.Image, threshold: float = 3.5) -> bool:
        """
        Lightweight perceptual change detection using 32x32 grayscale thumbnails in RAM.
        Avoids expensive cloud vision calls if the screen has not changed.
        """
        thumb = current_img.resize((32, 32)).convert("L")
        if self._last_analyzed_thumb is None:
            self._last_analyzed_thumb = thumb
            return True

        diff = ImageChops.difference(thumb, self._last_analyzed_thumb)
        stat = ImageStat.Stat(diff)
        diff_val = stat.mean[0]

        if diff_val >= threshold:
            self._last_analyzed_thumb = thumb
            return True
        return False

    def get_adaptive_image(self, img: Image.Image, target_quality: str = "standard") -> Image.Image:
        """
        Adaptive resolution strategy:
        - 'standard': downscale for general understanding (max 1024px width, low bandwidth/RAM)
        - 'high': full resolution for tiny text or precision clicking
        """
        if target_quality == "high":
            return img

        # Downscale proportionally if wider than 1024px
        if img.width > 1024:
            ratio = 1024.0 / float(img.width)
            new_height = int(float(img.height) * ratio)
            return img.resize((1024, new_height), Image.Resampling.BILINEAR)
        return img

    def inspect_current_screen(
        self,
        prompt: str = "Describe the visible screen, active window, and any notable dialogs.",
        quality: str = "standard",
        region: Optional[Tuple[int, int, int, int]] = None,
        force_analyze: bool = False
    ) -> Dict[str, Any]:
        """
        Captures a fresh frame in RAM, performs change detection, runs vision analysis,
        and releases frame memory immediately.
        """
        frame = self.capture_frame(region=region)
        changed = self.has_screen_changed(frame)

        if not changed and not force_analyze and self._frame_buffer:
            # Screen unchanged - return cached status
            active_w = gw.getActiveWindow()
            return {
                "success": True,
                "status": "Screen unchanged since last observation",
                "active_window": active_w.title if active_w else "Desktop",
                "changed": False
            }

        # Adapt resolution
        processed_img = self.get_adaptive_image(frame, target_quality=quality)

        # Run Provider
        provider = self._gemini_provider if self._gemini_provider.api_key else self._local_provider
        result = provider.analyze(processed_img, prompt)
        result["screen_changed"] = changed
        result["mode"] = self.mode

        return result

    def get_latest_frame(self) -> Optional[Image.Image]:
        if self._frame_buffer:
            return self._frame_buffer[-1][1]
        return None

    def clear_buffer(self):
        while self._frame_buffer:
            _, img = self._frame_buffer.pop()
            try:
                img.close()
            except Exception:
                pass
        self._last_analyzed_thumb = None


# Global Live Screen Instance
live_screen_manager = LiveScreenManager()
