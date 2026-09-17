"""
V.E.D.A. Offline Camera Mouse Control Subsystem
Optimized for 2-Core CPU Windows Environments.
Features:
- 100% Offline Hand Landmark Tracking via MediaPipe Tasks & bundled hand_landmarker.task
- Strictly in-RAM frame processing (Zero disk writes, zero network requests)
- Real Windows Cursor Control via SendInput / win32api
- Gestures: Point (Cursor), Closed Fist (Left Click), Two-Finger (Right Click),
  Thumb+Middle Pinch (Drag), Open Palm (Pause)
- Cursor Smoothing, Deadzone, Jitter Suppression, and Multi-Monitor Virtual Desktop mapping
- Live Hand Skeleton Overlay & Gesture State HUD (Direct zero-overhead landmark rendering)
- Emergency Stop Hotkey and Fail-Safe Drag Release
"""

import math
import os
import sys
import time
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

try:
    import win32api
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False

from veda.permissions import PermissionGuard


# Standard MediaPipe Hand Landmark Connections (21 points)
HAND_CONNECTIONS = [
    # Thumb
    (0, 1), (1, 2), (2, 3), (3, 4),
    # Index
    (0, 5), (5, 6), (6, 7), (7, 8),
    # Middle
    (0, 9), (9, 10), (10, 11), (11, 12),
    # Ring
    (0, 13), (13, 14), (14, 15), (15, 16),
    # Pinky
    (0, 17), (17, 18), (18, 19), (19, 20),
    # Palm Base
    (5, 9), (9, 13), (13, 17)
]


def resolve_model_path() -> str:
    """
    Locates the bundled hand_landmarker.task model relative to current directory or PyInstaller bundle.
    Guarantees no developer-specific machine paths.
    """
    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    candidates = [
        os.path.join(base_dir, "veda", "models", "hand_landmarker.task"),
        os.path.join(base_dir, "models", "hand_landmarker.task"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "hand_landmarker.task"),
        os.path.join(os.path.expanduser("~"), ".veda", "models", "hand_landmarker.task")
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[0]


class VirtualDesktopGeometry:
    """Calculates Windows Virtual Desktop bounds across single and multiple monitors."""

    @staticmethod
    def get_bounds() -> Tuple[int, int, int, int]:
        """Returns (left, top, width, height) of the virtual screen."""
        if HAS_WIN32:
            try:
                vx = win32api.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
                vy = win32api.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
                vw = win32api.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
                vh = win32api.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
                if vw > 0 and vh > 0:
                    return vx, vy, vw, vh
            except Exception:
                pass
        return 0, 0, 1920, 1080


class WindowsMouseInjector:
    """Native Windows Mouse Input generator with button-hold safety guarantees."""

    _is_dragging = False

    @classmethod
    def move_to(cls, screen_x: int, screen_y: int):
        if HAS_WIN32:
            try:
                vx, vy, vw, vh = VirtualDesktopGeometry.get_bounds()
                norm_x = int(((screen_x - vx) / vw) * 65535.0)
                norm_y = int(((screen_y - vy) / vh) * 65535.0)
                flags = win32con.MOUSEEVENTF_MOVE | win32con.MOUSEEVENTF_ABSOLUTE | win32con.MOUSEEVENTF_VIRTUALDESK
                win32api.mouse_event(flags, norm_x, norm_y, 0, 0)
                return
            except Exception:
                pass
        try:
            import pyautogui
            pyautogui.moveTo(screen_x, screen_y, _pause=False)
        except Exception:
            pass

    @classmethod
    def click(cls, button: str = "left"):
        if HAS_WIN32:
            try:
                if button == "left":
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    time.sleep(0.015)
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                elif button == "right":
                    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                    time.sleep(0.015)
                    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                return
            except Exception:
                pass
        try:
            import pyautogui
            pyautogui.click(button=button)
        except Exception:
            pass

    @classmethod
    def mouse_down(cls, button: str = "left"):
        cls._is_dragging = True
        if HAS_WIN32:
            try:
                flag = win32con.MOUSEEVENTF_LEFTDOWN if button == "left" else win32con.MOUSEEVENTF_RIGHTDOWN
                win32api.mouse_event(flag, 0, 0, 0, 0)
                return
            except Exception:
                pass
        try:
            import pyautogui
            pyautogui.mouseDown(button=button)
        except Exception:
            pass

    @classmethod
    def mouse_up(cls, button: str = "left"):
        cls._is_dragging = False
        if HAS_WIN32:
            try:
                flag = win32con.MOUSEEVENTF_LEFTUP if button == "left" else win32con.MOUSEEVENTF_RIGHTUP
                win32api.mouse_event(flag, 0, 0, 0, 0)
                return
            except Exception:
                pass
        try:
            import pyautogui
            pyautogui.mouseUp(button=button)
        except Exception:
            pass

    @classmethod
    def release_all(cls):
        """Emergency safe release of all mouse buttons."""
        cls._is_dragging = False
        if HAS_WIN32:
            try:
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            except Exception:
                pass
        try:
            import pyautogui
            pyautogui.mouseUp(button="left")
            pyautogui.mouseUp(button="right")
        except Exception:
            pass


class GestureClassifier:
    """Deterministic, zero-overhead hand gesture classifier."""

    @staticmethod
    def dist_sq(p1, p2) -> float:
        return (p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2

    @classmethod
    def classify(cls, landmarks) -> Tuple[str, Dict[str, Any]]:
        """
        Classifies the 21 hand landmarks into:
        - 'POINT' (Index finger cursor control)
        - 'CLICK' (Closed fist left click)
        - 'RIGHT_CLICK' (Two fingers extended)
        - 'DRAG' (Thumb + Middle finger pinch)
        - 'PAUSED' (Open palm)
        - 'NEUTRAL' (Transition / other)
        """
        if not landmarks or len(landmarks) < 21:
            return "NO_HAND", {}

        wrist = landmarks[0]
        thumb_tip = landmarks[4]
        index_mcp = landmarks[5]
        index_tip = landmarks[8]
        middle_mcp = landmarks[9]
        middle_tip = landmarks[12]
        ring_mcp = landmarks[13]
        ring_tip = landmarks[16]
        pinky_mcp = landmarks[17]
        pinky_tip = landmarks[20]

        # Finger extended if tip is significantly further from wrist than its MCP joint
        def is_extended(tip, mcp):
            return cls.dist_sq(tip, wrist) > cls.dist_sq(mcp, wrist) * 1.3

        index_ext = is_extended(index_tip, index_mcp)
        middle_ext = is_extended(middle_tip, middle_mcp)
        ring_ext = is_extended(ring_tip, ring_mcp)
        pinky_ext = is_extended(pinky_tip, pinky_mcp)

        # Thumb extension relative to index MCP
        thumb_ext = cls.dist_sq(thumb_tip, wrist) > cls.dist_sq(index_mcp, wrist) * 0.9

        # Distances for pinches and fist
        thumb_middle_dist = math.sqrt(cls.dist_sq(thumb_tip, middle_tip))

        extended_count = sum([index_ext, middle_ext, ring_ext, pinky_ext])

        # 1. Open Palm = Pause (all 4-5 fingers extended)
        if extended_count >= 4 and thumb_ext:
            return "PAUSED", {"extended": extended_count}

        # 2. Closed Fist = Left Click (zero fingers extended, fingertips close to wrist/mcp)
        if extended_count == 0 and not thumb_ext:
            return "CLICK", {"extended": 0}

        # 3. Thumb + Middle Finger Pinch = Drag (Thumb and middle tip close together while pointing or dragging)
        if thumb_middle_dist < 0.08 and extended_count >= 1:
            return "DRAG", {"pinch_dist": thumb_middle_dist}

        # 4. Two Fingers = Right Click (Index and Middle clearly extended and NOT pinched to thumb)
        if index_ext and middle_ext and not ring_ext and not pinky_ext and thumb_middle_dist >= 0.08:
            return "RIGHT_CLICK", {"extended": 2}

        # 5. Pointing = Cursor Move (Index extended, others mostly folded)
        if index_ext and not ring_ext and not pinky_ext:
            return "POINT", {"extended": 1}

        return "NEUTRAL", {"extended": extended_count}


class CameraMouseController:
    """
    Lightweight, fully offline Camera Mouse engine designed for 2-core CPUs.
    Runs video capture and hand tracking asynchronously in a low-priority thread.
    Process frames in RAM only. Zero network requests, zero disk writes.
    """

    def __init__(self):
        self.is_active = False
        self.is_paused = False
        self.camera_index = 0
        self.target_fps = 15
        self.resolution = (320, 240)

        # Configurable settings
        self.sensitivity = 1.8
        self.smoothing = 0.45
        self.deadzone = 0.015
        self.click_debounce = 0.35

        # Runtime smoothing state
        self._curr_cursor_x: Optional[float] = None
        self._curr_cursor_y: Optional[float] = None
        self._prev_raw_x: Optional[float] = None
        self._prev_raw_y: Optional[float] = None

        # Gesture Debounce & Hysteresis State
        self._last_gesture = "NO_HAND"
        self._last_click_time = 0.0
        self._last_right_click_time = 0.0
        self._fist_held_latched = False
        self._two_finger_latched = False
        self._is_dragging = False

        # Metrics
        self._fps_count = 0
        self._fps_start_time = time.time()
        self.current_fps = 0.0
        self.cpu_mode = "LOW PERFORMANCE (2-CORE)"

        # Threads and Synchronization
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._cap = None
        self._landmarker = None

        # Preview callback for UI skeleton overlay
        self.on_preview_frame: Optional[Callable[[Image.Image, str, bool, float], None]] = None
        self.on_state_change: Optional[Callable[[str], None]] = None

    def _init_landmarker(self) -> bool:
        """Initializes local MediaPipe HandLandmarker with bundled model."""
        if not HAS_MEDIAPIPE:
            print("[CameraMouse] MediaPipe is not installed.")
            return False

        model_path = resolve_model_path()
        if not os.path.isfile(model_path):
            print(f"[CameraMouse] Model asset not found at {model_path}")
            return False

        try:
            base_options = BaseOptions(model_asset_path=model_path)
            options = vision.HandLandmarkerOptions(
                base_options=base_options,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5
            )
            self._landmarker = vision.HandLandmarker.create_from_options(options)
            return True
        except Exception as e:
            print(f"[CameraMouse] Failed initializing landmarker: {e}")
            return False

    def start(self, camera_index: Optional[int] = None) -> bool:
        """Starts camera mouse processing in dedicated background thread."""
        PermissionGuard.require("camera", action_name="Camera Mouse Control")

        if self.is_active:
            return True

        if camera_index is not None:
            self.camera_index = camera_index

        if not self._init_landmarker():
            return False

        self._stop_event.clear()
        self.is_active = True
        self.is_paused = False
        self._curr_cursor_x = None
        self._curr_cursor_y = None

        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

        if self.on_state_change:
            self.on_state_change("ON")

        return True

    def stop(self):
        """Immediately stops camera tracking, releases camera and releases mouse buttons."""
        if not self.is_active:
            return

        self.is_active = False
        self._stop_event.set()

        # Guarantee safe mouse release
        WindowsMouseInjector.release_all()
        self._is_dragging = False

        if self._cap:
            try:
                if self._cap.isOpened():
                    self._cap.release()
            except Exception:
                pass
            self._cap = None

        if self._landmarker:
            try:
                self._landmarker.close()
            except Exception:
                pass
            self._landmarker = None

        if self._worker_thread and self._worker_thread.is_alive():
            try:
                self._worker_thread.join(timeout=0.8)
            except Exception:
                pass
            self._worker_thread = None

        if self.on_state_change:
            self.on_state_change("OFF")

    def emergency_stop(self):
        """Global Emergency Stop called on ESC key or panic trigger."""
        print("[CameraMouse] EMERGENCY STOP TRIGGERED.")
        self.stop()

    def _worker_loop(self):
        """
        Lightweight capture and inference loop.
        Drops stale frames and processes only latest frame.
        """
        try:
            self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not self._cap.isOpened():
                print(f"[CameraMouse] Cannot open camera index {self.camera_index}")
                self.stop()
                return

            # Set hardware resolution to low-bandwidth 320x240 for 2-core CPU
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self._cap.set(cv2.CAP_PROP_FPS, self.target_fps)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            vx, vy, vw, vh = VirtualDesktopGeometry.get_bounds()
            frame_delay = 1.0 / float(self.target_fps)

            while not self._stop_event.is_set():
                t_start = time.time()

                # Read only latest frame
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    time.sleep(0.04)
                    continue

                # Mirror frame horizontally so hand movement matches screen movement
                frame = cv2.flip(frame, 1)
                h, w, _ = frame.shape

                # Convert to RGB in-memory for MediaPipe
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

                # Run offline landmark tracking
                result = None
                try:
                    result = self._landmarker.detect(mp_image)
                except Exception as e:
                    pass

                hand_detected = bool(result and result.hand_landmarks and len(result.hand_landmarks) > 0)
                landmarks = result.hand_landmarks[0] if hand_detected else None

                gesture = "NO_HAND"
                gesture_info = {}

                if hand_detected and landmarks:
                    gesture, gesture_info = GestureClassifier.classify(landmarks)

                    if gesture == "PAUSED":
                        self.is_paused = True
                        if self._is_dragging:
                            WindowsMouseInjector.mouse_up()
                            self._is_dragging = False
                    else:
                        self.is_paused = False
                        self._process_cursor_and_actions(landmarks, gesture, vx, vy, vw, vh)
                else:
                    # Lost hand handling: freeze cursor, release drag safely
                    if self._is_dragging:
                        WindowsMouseInjector.mouse_up()
                        self._is_dragging = False
                    self._fist_held_latched = False
                    self._two_finger_latched = False

                self._last_gesture = gesture

                # Calculate real FPS
                self._fps_count += 1
                fps_elapsed = time.time() - self._fps_start_time
                if fps_elapsed >= 1.0:
                    self.current_fps = round(self._fps_count / fps_elapsed, 1)
                    self._fps_count = 0
                    self._fps_start_time = time.time()

                # Render skeleton overlay directly onto frame in RAM
                if self.on_preview_frame:
                    annotated_frame = self._render_skeleton_overlay(frame, landmarks, gesture)
                    rgb_annotated = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
                    pil_annotated = Image.fromarray(rgb_annotated)
                    try:
                        self.on_preview_frame(pil_annotated, gesture, hand_detected, self.current_fps)
                    except Exception:
                        pass

                # Frame pacing to protect 2-core CPU
                t_used = time.time() - t_start
                t_sleep = max(0.005, frame_delay - t_used)
                time.sleep(t_sleep)

        except Exception as e:
            print(f"[CameraMouse] Loop exception: {e}")
        finally:
            WindowsMouseInjector.release_all()
            if self._cap:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None

    def _process_cursor_and_actions(self, landmarks, gesture: str, vx: int, vy: int, vw: int, vh: int):
        """Processes coordinates, smoothing, gestures, and dispatches real Windows mouse events."""
        now = time.time()

        # 1. Closed Fist = Left Click
        if gesture == "CLICK":
            if not self._fist_held_latched and (now - self._last_click_time > self.click_debounce):
                WindowsMouseInjector.click("left")
                self._last_click_time = now
                self._fist_held_latched = True
            return
        else:
            self._fist_held_latched = False

        # 2. Two Fingers = Right Click
        if gesture == "RIGHT_CLICK":
            if not self._two_finger_latched and (now - self._last_right_click_time > self.click_debounce):
                WindowsMouseInjector.click("right")
                self._last_right_click_time = now
                self._two_finger_latched = True
            return
        else:
            self._two_finger_latched = False

        # 3. Drag Action
        if gesture == "DRAG":
            if not self._is_dragging:
                WindowsMouseInjector.mouse_down("left")
                self._is_dragging = True
        else:
            if self._is_dragging:
                WindowsMouseInjector.mouse_up("left")
                self._is_dragging = False

        # 4. Cursor Movement (Active during POINT or DRAG)
        if gesture in ["POINT", "DRAG", "NEUTRAL"]:
            index_tip = landmarks[8]
            raw_x = index_tip.x
            raw_y = index_tip.y

            # Deadzone check against previous raw position
            if self._prev_raw_x is not None and self._prev_raw_y is not None:
                d_sq = (raw_x - self._prev_raw_x) ** 2 + (raw_y - self._prev_raw_y) ** 2
                if d_sq < (self.deadzone ** 2):
                    return

            self._prev_raw_x = raw_x
            self._prev_raw_y = raw_y

            # Active tracking zone mapping (center 70% of frame mapped to 100% of desktop)
            # Avoids requiring full arm movement
            norm_x = (raw_x - 0.20) / 0.60
            norm_y = (raw_y - 0.20) / 0.60
            norm_x = max(0.0, min(1.0, norm_x))
            norm_y = max(0.0, min(1.0, norm_y))

            target_x = vx + norm_x * vw
            target_y = vy + norm_y * vh

            # Exponential Smoothing
            if self._curr_cursor_x is None or self._curr_cursor_y is None:
                self._curr_cursor_x = target_x
                self._curr_cursor_y = target_y
            else:
                alpha = self.smoothing
                self._curr_cursor_x = alpha * target_x + (1.0 - alpha) * self._curr_cursor_x
                self._curr_cursor_y = alpha * target_y + (1.0 - alpha) * self._curr_cursor_y

            WindowsMouseInjector.move_to(int(self._curr_cursor_x), int(self._curr_cursor_y))

    def _render_skeleton_overlay(self, frame: np.ndarray, landmarks, gesture: str) -> np.ndarray:
        """
        Draws real-time hand skeleton overlay directly from detected landmarks.
        Highlights index, thumb, and middle fingertips with color-coded status badges.
        """
        out = frame.copy()
        h, w, _ = out.shape

        if landmarks:
            pts = []
            for lm in landmarks:
                cx = int(lm.x * w)
                cy = int(lm.y * h)
                pts.append((cx, cy))

            # Draw bones / connections
            for p1_idx, p2_idx in HAND_CONNECTIONS:
                cv2.line(out, pts[p1_idx], pts[p2_idx], (56, 189, 248), 2)  # Cyan lines

            # Draw all joints
            for idx, pt in enumerate(pts):
                # Default joint circle
                cv2.circle(out, pt, 3, (16, 185, 129), -1)  # Emerald green

            # Highlight specific fingertips
            # Thumb Tip (4) - Amber
            cv2.circle(out, pts[4], 6, (0, 191, 255), -1)
            # Index Tip (8) - Bright Cyan (Cursor Controller)
            cv2.circle(out, pts[8], 7, (255, 191, 0), -1)
            # Middle Tip (12) - Purple
            cv2.circle(out, pts[12], 6, (226, 43, 138), -1)

            # Draw Index pointer ring
            cv2.circle(out, pts[8], 11, (255, 255, 255), 1)

            # Hand Status Banner
            cv2.putText(out, "HAND DETECTED", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (16, 185, 129), 2)
        else:
            cv2.putText(out, "NO HAND", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 116, 139), 2)

        # Gesture Badge HUD
        gesture_colors = {
            "POINT": (255, 191, 0),       # Cyan/Blue
            "CLICK": (0, 255, 127),       # Green
            "RIGHT_CLICK": (255, 105, 180), # Pink
            "DRAG": (0, 140, 255),        # Orange
            "PAUSED": (0, 215, 255),      # Gold
            "NO_HAND": (100, 116, 139),   # Gray
            "NEUTRAL": (148, 163, 184)    # Slate
        }
        badge_col = gesture_colors.get(gesture, (255, 255, 255))
        cv2.putText(out, f"GESTURE: {gesture}", (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, badge_col, 2)
        cv2.putText(out, f"FPS: {self.current_fps}", (w - 75, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        return out

    def get_diagnostics(self) -> Dict[str, Any]:
        """Provides diagnostic health and telemetry data."""
        return {
            "active": self.is_active,
            "paused": self.is_paused,
            "last_gesture": self._last_gesture,
            "fps": self.current_fps,
            "resolution": f"{self.resolution[0]}x{self.resolution[1]}",
            "sensitivity": self.sensitivity,
            "smoothing": self.smoothing,
            "deadzone": self.deadzone,
            "is_dragging": self._is_dragging,
            "cpu_mode": self.cpu_mode,
            "model_path": resolve_model_path(),
            "model_exists": os.path.isfile(resolve_model_path())
        }


# Global singleton controller
camera_mouse_controller = CameraMouseController()
