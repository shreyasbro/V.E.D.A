"""
V.E.D.A. Core Windows Capabilities
Exposes high-level, reliable Windows primitives to the AI Agent.
Follows:
- Windows API First
- Dedicated, safe Input Engine (text typing vs. single keys vs. keyboard shortcuts)
- Headless, invisible process execution
- Smart Application Resolution (generic resolver)
- Generic Window Management (focus, minimize, maximize, close)
- Single-cache screenshot engine
"""

import os
import time
import shutil
from typing import Any, Dict, List, Optional
import pyautogui
import pygetwindow as gw
from PIL import Image

from veda.config import SCREENSHOT_FILE, CACHE_DIR
from veda.input_engine import KeyboardEngine, MouseEngine, ClipboardEngine
from veda.process_runner import ControlledProcessRunner
from veda.permissions import guard, PermissionGuard
from veda.ui_automation import UIAutomationEngine, MultiMonitorEngine
from veda.windows_control import WindowsControlEngine
from veda.camera_mouse import camera_mouse_controller
from veda.system_settings import SystemSettingsEngine
from veda.elevation import ElevationManager
from veda.hardware import camera_subsystem, microphone_subsystem

_latest_screen_image: Optional[Image.Image] = None

class WindowsCapabilities:
    """
    Real Windows Execution Capabilities for V.E.D.A.
    Directly exposed to the AI Agent.
    """

    # ==========================================
    # 1. SMART APPLICATION LAUNCHING
    # ==========================================
    @staticmethod
    def open_application(application: str, arguments: Optional[str] = None) -> Dict[str, Any]:
        """
        Smart generic application launcher with action verification.
        Finds application dynamically across Start Menu shortcuts, Registry App Paths, and PATH.
        Examples: 'notepad', 'chrome', 'edge', 'calculator', 'vscode', 'explorer', 'cmd', 'paint'
        """
        return WindowsControlEngine.launch_application(app_name_or_path=application, arguments=arguments)

    @staticmethod
    def find_application(query: str) -> Dict[str, Any]:
        """
        Dynamically finds an application path on the system.
        """
        target = WindowsControlEngine.find_application(query)
        if target:
            return {"success": True, "application": query, "target_path": target}
        return {"success": False, "error": f"Application '{query}' not found on system."}

    @staticmethod
    @guard("file_access")
    def open_path(path: str) -> Dict[str, Any]:
        """
        Opens any file or folder path directly with its default associated Windows application.
        Supports known folder names ('downloads', 'documents', 'desktop', etc.), spaces, and Unicode.
        """
        resolved = WindowsControlEngine.resolve_path(path)
        if not os.path.exists(resolved):
            return {"success": False, "error": f"Path '{path}' (resolved: '{resolved}') does not exist."}
        try:
            os.startfile(resolved)
            return {
                "success": True,
                "action": "open_path",
                "path": path,
                "resolved_path": resolved,
                "status": "Opened via Windows default shell association"
            }
        except Exception as e:
            return {"success": False, "error": f"Failed opening path '{path}': {e}"}

    @staticmethod
    @guard("file_access")
    def navigate_file_explorer(path: str) -> Dict[str, Any]:
        """
        Navigates File Explorer directly to a specific folder or selects a file.
        Works dynamically for 'downloads', 'documents', 'desktop', or any directory path.
        Guarantees opening the actual target location, avoiding default Quick Access.
        """
        return WindowsControlEngine.navigate_file_explorer(target_path=path)

    # Alias for backwards compatibility
    @classmethod
    def open_app(cls, app_name: str) -> Dict[str, Any]:
        return cls.open_application(app_name)

    # ==========================================
    # 2. WINDOW MANAGEMENT
    # ==========================================
    @staticmethod
    def get_active_window() -> Dict[str, Any]:
        """
        Returns currently active and focused window title and state.
        """
        try:
            w = gw.getActiveWindow()
            if w and w.title and w.title.strip():
                return {
                    "success": True,
                    "title": w.title,
                    "is_active": True
                }
            return {
                "success": True,
                "title": "Desktop / None",
                "is_active": False
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_open_windows() -> Dict[str, Any]:
        """
        Scans all running and visible desktop windows on the PC.
        """
        try:
            titles = [w.title for w in gw.getAllWindows() if w.title and w.title.strip()]
            unique_titles = sorted(list(set(titles)))
            return {
                "success": True,
                "open_windows": unique_titles,
                "count": len(unique_titles)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def focus_window(window_name: str) -> Dict[str, Any]:
        """
        Brings an already open window matching window_name to foreground and focuses it.
        Restores the window if it was minimized.
        """
        return WindowsControlEngine.focus_window(window_title=window_name)

    @staticmethod
    def find_window(query: str) -> Dict[str, Any]:
        """
        Searches all open desktop windows matching a title query.
        """
        matches = WindowsControlEngine.find_windows(query=query)
        return {
            "success": True,
            "query": query,
            "match_count": len(matches),
            "windows": matches
        }

    @staticmethod
    def get_window_state(window_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns detailed window state (position, dimensions, minimized, maximized, active).
        """
        return WindowsControlEngine.get_window_state(window_title=window_title)

    @staticmethod
    def move_window(window_title: str, x: int, y: int) -> Dict[str, Any]:
        """
        Moves the window matching window_title to coordinates (x, y).
        """
        return WindowsControlEngine.move_window(window_title=window_title, x=x, y=y)

    @staticmethod
    def resize_window(window_title: str, width: int, height: int) -> Dict[str, Any]:
        """
        Resizes the window matching window_title to (width, height).
        """
        return WindowsControlEngine.resize_window(window_title=window_title, width=width, height=height)

    @staticmethod
    def wait_for_window(window_title: str, timeout_seconds: float = 5.0) -> Dict[str, Any]:
        """
        Waits until a window matching window_title appears.
        """
        return WindowsControlEngine.wait_for_window(window_title=window_title, timeout_seconds=timeout_seconds)

    @staticmethod
    def verify_action(action_type: str, target: str) -> Dict[str, Any]:
        """
        Verifies whether an action succeeded (e.g. app launched, folder opened).
        Follows PLAN -> ACT -> OBSERVE -> VERIFY loop.
        """
        return WindowsControlEngine.verify_action(action_type=action_type, target=target)

    @staticmethod
    def minimize_window(window_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Minimizes a window matching window_name, or active window if not provided.
        """
        try:
            if window_name:
                windows = gw.getWindowsWithTitle(window_name)
                if windows:
                    windows[0].minimize()
                    return {"success": True, "minimized_window": windows[0].title}
                return {"success": False, "error": f"No window matching '{window_name}' found."}
            else:
                w = gw.getActiveWindow()
                if w:
                    w.minimize()
                    return {"success": True, "minimized_window": w.title}
                return {"success": False, "error": "No active window found to minimize."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def maximize_window(window_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Maximizes a window matching window_name, or active window if not provided.
        """
        try:
            if window_name:
                windows = gw.getWindowsWithTitle(window_name)
                if windows:
                    windows[0].maximize()
                    return {"success": True, "maximized_window": windows[0].title}
                return {"success": False, "error": f"No window matching '{window_name}' found."}
            else:
                w = gw.getActiveWindow()
                if w:
                    w.maximize()
                    return {"success": True, "maximized_window": w.title}
                return {"success": False, "error": "No active window found to maximize."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def close_window(window_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Closes a window matching window_name, or active window if not provided.
        """
        try:
            if window_name:
                windows = gw.getWindowsWithTitle(window_name)
                if windows:
                    windows[0].close()
                    return {"success": True, "closed_window": windows[0].title}
                return {"success": False, "error": f"No window matching '{window_name}' found to close."}
            else:
                pyautogui.hotkey("alt", "f4")
                return {"success": True, "closed_active": True}
        except pyautogui.FailSafeException:
            return {"success": False, "error": "PyAutoGUI fail-safe triggered."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Alias for backwards compatibility
    @classmethod
    def close_app(cls, app_name: Optional[str] = None) -> Dict[str, Any]:
        return cls.close_window(app_name)

    # ==========================================
    # 3. SEPARATED RELIABLE INPUT ENGINE
    # ==========================================
    @staticmethod
    def type_text(text: str) -> Dict[str, Any]:
        """
        Types pure text strings into the currently focused application.
        Do NOT use this to execute shortcuts like Ctrl+C or Alt+F4.
        """
        return KeyboardEngine.type_text(text)

    @staticmethod
    def press_key(key: str) -> Dict[str, Any]:
        """
        Presses a single keyboard key (e.g. 'enter', 'tab', 'esc', 'space', 'backspace', 'delete', 'up', 'down').
        """
        return KeyboardEngine.press_key(key)

    @staticmethod
    def press_shortcut(modifiers: List[str], key: str) -> Dict[str, Any]:
        """
        Executes a keyboard combination / shortcut with safe Down/Up sequencing and modifier cleanup.
        Examples:
        - Ctrl+C: modifiers=['ctrl'], key='c'
        - Ctrl+V: modifiers=['ctrl'], key='v'
        - Alt+Tab: modifiers=['alt'], key='tab'
        - Win+D: modifiers=['win'], key='d'
        - Ctrl+Shift+Esc: modifiers=['ctrl', 'shift'], key='esc'
        """
        return KeyboardEngine.press_shortcut(modifiers, key)

    @staticmethod
    def mouse_move(x: int, y: int) -> Dict[str, Any]:
        """
        Moves the mouse cursor smoothly to coordinates (x, y). Clamped safely away from corners.
        """
        return MouseEngine.mouse_move(x, y)

    @staticmethod
    def mouse_click(button: str = "left") -> Dict[str, Any]:
        """
        Performs a mouse click at current cursor position (button: 'left', 'right', 'middle').
        """
        return MouseEngine.mouse_click(button)

    @staticmethod
    def mouse_double_click() -> Dict[str, Any]:
        """
        Performs a mouse double-click at current cursor position.
        """
        return MouseEngine.mouse_double_click()

    @staticmethod
    def mouse_right_click() -> Dict[str, Any]:
        """
        Performs a mouse right-click at current cursor position.
        """
        return MouseEngine.mouse_right_click()

    @staticmethod
    def scroll(amount: int) -> Dict[str, Any]:
        """
        Scrolls the active window vertically. Positive scrolls up, negative down.
        """
        return MouseEngine.mouse_scroll(amount)

    # ==========================================
    # 4. CLIPBOARD TOOLS
    # ==========================================
    @staticmethod
    def get_clipboard() -> Dict[str, Any]:
        """
        Reads text content from the Windows clipboard.
        """
        return ClipboardEngine.get_clipboard()

    @staticmethod
    def set_clipboard(text: str) -> Dict[str, Any]:
        """
        Copies text directly onto the Windows clipboard.
        Useful for moving large blocks of text without simulating thousands of keystrokes.
        """
        return ClipboardEngine.set_clipboard(text)

    # ==========================================
    # 5. CONTROLLED BACKGROUND PROCESS EXECUTION
    # ==========================================
    @staticmethod
    def execute_background_process(command: str, timeout: int = 45) -> Dict[str, Any]:
        """
        Executes a shell/CLI command invisibly in the background without creating a visible CMD or PowerShell window.
        Returns command, stdout, stderr, exit_code, duration_seconds, and process_id.
        Only use when direct Windows APIs (filesystem, process, clipboard) are insufficient.
        """
        return ControlledProcessRunner.run_command(command, timeout=timeout)

    # ==========================================
    # 6. OBSERVATION & SCREENSHOTS
    # ==========================================
    @staticmethod
    def take_screenshot(save_to_disk: bool = True, focus_active_window: bool = False) -> Dict[str, Any]:
        """
        Captures the current desktop screen.
        Supports primary screen, virtual multi-monitor bounding box, or focused window.
        Keeps the image in memory for instant vision/observation,
        and optionally writes to disk only when explicitly requested.
        Strictly verifies that a real PIL image was captured (width > 0, height > 0)
        before reporting success.
        """
        global _latest_screen_image
        img: Optional[Image.Image] = None
        error_details: List[str] = []

        # Tier 1: pyautogui capture
        try:
            if focus_active_window:
                w = gw.getActiveWindow()
                if w and w.width > 20 and w.height > 20:
                    region = (max(0, w.left), max(0, w.top), max(20, w.width), max(20, w.height))
                    img = pyautogui.screenshot(region=region)
                else:
                    img = pyautogui.screenshot()
            else:
                img = pyautogui.screenshot()
        except Exception as e:
            error_details.append(f"pyautogui: {e}")

        # Tier 2: PIL.ImageGrab fallback (handles virtual multi-monitor)
        if img is None or not (isinstance(img, Image.Image) and img.width > 0 and img.height > 0):
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab(all_screens=True)
            except Exception as e:
                error_details.append(f"ImageGrab: {e}")

        # Tier 3: Direct Windows GDI Desktop fallback
        if img is None or not (isinstance(img, Image.Image) and img.width > 0 and img.height > 0):
            try:
                import win32gui, win32ui, win32con, win32api
                hwnd = win32gui.GetDesktopWindow()
                w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                if w > 0 and h > 0:
                    hwnd_dc = win32gui.GetWindowDC(hwnd)
                    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
                    save_dc = mfc_dc.CreateCompatibleDC()
                    save_bmp = win32ui.CreateBitmap()
                    save_bmp.CreateCompatibleBitmap(mfc_dc, w, h)
                    save_dc.SelectObject(save_bmp)
                    save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)
                    bmpinfo = save_bmp.GetInfo()
                    bmpstr = save_bmp.GetBitmapBits(True)
                    img = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
                    win32gui.DeleteObject(save_bmp.GetHandle())
                    save_dc.DeleteDC()
                    mfc_dc.DeleteDC()
                    win32gui.ReleaseDC(hwnd, hwnd_dc)
            except Exception as e:
                error_details.append(f"GDI: {e}")

        # Strict validation
        if img is None or not isinstance(img, Image.Image) or img.width <= 0 or img.height <= 0:
            return {
                "success": False,
                "error": f"Failed to acquire valid screen pixels. Errors: {'; '.join(error_details)}"
            }

        _latest_screen_image = img
        cached_path = "in-memory"

        if save_to_disk:
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
                img.save(SCREENSHOT_FILE)
                if os.path.exists(SCREENSHOT_FILE) and os.path.getsize(SCREENSHOT_FILE) > 0:
                    cached_path = SCREENSHOT_FILE
                else:
                    return {"success": False, "error": "Screenshot file could not be written to cache."}
            except Exception as e:
                return {"success": False, "error": f"Failed writing screenshot to cache: {e}"}

        return {
            "success": True,
            "cached_path": cached_path,
            "resolution": f"{img.width}x{img.height}",
            "width": img.width,
            "height": img.height,
            "status": "Screen frame captured into RAM successfully"
        }

    @staticmethod
    def get_latest_screen_image() -> Optional[Image.Image]:
        """Returns the in-memory screenshot PIL Image object."""
        global _latest_screen_image
        return _latest_screen_image

    @staticmethod
    def inspect_screen(
        prompt: str = "Analyze the visible screen, identify the active application, notable dialogs or errors, and key UI buttons.",
        quality: str = "standard",
        focus_active_window: bool = False
    ) -> Dict[str, Any]:
        """
        Temporarily inspects the current screen or focused window using in-memory Live Vision (Gemini / Local).
        Performs local change detection before sending frames to Gemini.
        Zero permanent disk writes.
        Quality options: 'standard' (adaptive downscale), 'high' (full resolution).
        """
        from veda.vision import live_screen_manager
        region = None
        if focus_active_window:
            w = gw.getActiveWindow()
            if w and w.width > 50 and w.height > 50:
                region = (max(0, w.left), max(0, w.top), max(50, w.width), max(50, w.height))

        return live_screen_manager.inspect_current_screen(
            prompt=prompt,
            quality=quality,
            region=region
        )

    @staticmethod
    def configure_live_screen(mode: str) -> Dict[str, Any]:
        """
        Configures Live Screen observation mode.
        Modes: 'OFF', 'LIVE', 'FOCUS_WINDOW'.
        """
        from veda.vision import live_screen_manager
        clean_mode = mode.upper().strip()
        if clean_mode not in ["OFF", "LIVE", "FOCUS_WINDOW"]:
            clean_mode = "OFF"
        live_screen_manager.set_mode(clean_mode)
        return {
            "success": True,
            "mode": clean_mode,
            "status": f"Live screen observation mode set to {clean_mode}"
        }

    @staticmethod
    def save_screenshot(destination_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Explicitly saves the current screenshot to a user-specified permanent location (e.g. on Desktop).
        Strictly verifies file presence and size > 0 bytes on disk before reporting success.
        Only called when user explicitly asks to 'Save this screenshot'.
        """
        global _latest_screen_image
        try:
            if _latest_screen_image is None:
                cap_res = WindowsCapabilities.take_screenshot(save_to_disk=False)
                if not cap_res.get("success") or _latest_screen_image is None:
                    return {"success": False, "error": cap_res.get("error", "Failed to capture screen.")}

            if not destination_path:
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                os.makedirs(desktop, exist_ok=True)
                destination_path = os.path.join(desktop, f"veda_screenshot_{int(time.time())}.png")
            else:
                dest_dir = os.path.dirname(os.path.abspath(destination_path))
                os.makedirs(dest_dir, exist_ok=True)

            _latest_screen_image.save(destination_path)

            if not os.path.exists(destination_path) or os.path.getsize(destination_path) == 0:
                return {"success": False, "error": "Screenshot failed verification on disk."}

            return {
                "success": True,
                "saved_path": destination_path,
                "file_size": os.path.getsize(destination_path),
                "resolution": f"{_latest_screen_image.width}x{_latest_screen_image.height}",
                "status": f"Screenshot explicitly saved to {destination_path}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================
    # 7. DIRECT FILESYSTEM APIS (NO TERMINAL WINDOWS)
    # ==========================================
    @staticmethod
    def list_directory(path: Optional[str] = None) -> Dict[str, Any]:
        """
        Lists files and folders directly via filesystem API without opening CMD.
        Defaults to Desktop if path is omitted.
        """
        try:
            target = path or os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.exists(target):
                return {"success": False, "error": f"Path '{target}' does not exist."}

            entries = []
            for item in os.listdir(target)[:50]:
                item_path = os.path.join(target, item)
                is_dir = os.path.isdir(item_path)
                size_bytes = os.path.getsize(item_path) if not is_dir else 0
                entries.append({
                    "name": item,
                    "is_directory": is_dir,
                    "size_bytes": size_bytes
                })

            return {
                "success": True,
                "directory": target,
                "count": len(entries),
                "entries": entries
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def read_text_file(path: str) -> Dict[str, Any]:
        """
        Reads text content from file using direct Python file I/O.
        """
        try:
            if not os.path.isabs(path):
                path = os.path.join(os.path.expanduser("~"), "Desktop", path)
            if not os.path.exists(path):
                return {"success": False, "error": f"File '{path}' does not exist."}
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(5000)
            return {
                "success": True,
                "file_path": path,
                "content": content
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def write_text_file(path: str, content: str) -> Dict[str, Any]:
        """
        Creates or updates a text file directly on disk without opening any terminal or editor window.
        """
        try:
            if not os.path.isabs(path):
                path = os.path.join(os.path.expanduser("~"), "Desktop", path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "success": True,
                "created_file": path,
                "bytes_written": len(content)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def create_directory(path: str) -> Dict[str, Any]:
        """
        Creates a new folder directly via Windows filesystem APIs without opening CMD.
        """
        try:
            if not os.path.isabs(path):
                path = os.path.join(os.path.expanduser("~"), "Desktop", path)
            os.makedirs(path, exist_ok=True)
            return {
                "success": True,
                "created_directory": path,
                "status": "Directory created successfully"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================
    # 7. SEMANTIC WINDOWS UI AUTOMATION
    # ==========================================
    @staticmethod
    @guard("computer_control")
    def inspect_ui_elements(window_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Semantically inspects visible UI controls (buttons, textboxes, checkboxes, menus)
        of the specified window or the active window.
        Use this BEFORE attempting visual coordinate clicks.
        """
        return UIAutomationEngine.get_element_tree(window_title=window_title)

    @staticmethod
    @guard("computer_control")
    def click_ui_element(name: str) -> Dict[str, Any]:
        """
        Semantically clicks an interactive UI element by its accessible label/name.
        Examples: 'Save', 'Submit', 'Settings', 'Close', 'Cancel', 'OK'.
        Prefers semantic invocation rather than guessing screen pixel coordinates.
        """
        return UIAutomationEngine.click_element_by_name(name=name)

    @staticmethod
    @guard("computer_control")
    def set_ui_text_field(field_name: str, text: str) -> Dict[str, Any]:
        """
        Semantically finds a named text/edit field and enters text into it directly.
        """
        return UIAutomationEngine.set_text_by_name(name=field_name, text=text)

    @staticmethod
    @guard("computer_control")
    def select_ui_element(element_name: str, item_text: str) -> Dict[str, Any]:
        """
        Selects an item inside a ComboBox, List, or Tab control using UI Automation.
        """
        return UIAutomationEngine.select_element(element_name=element_name, item_text=item_text)

    @staticmethod
    @guard("computer_control")
    def scroll_ui(direction: str = "down", amount: int = 3) -> Dict[str, Any]:
        """
        Scrolls the active window or control ('up', 'down', 'page_up', 'page_down').
        """
        return UIAutomationEngine.scroll(direction=direction, amount=amount)

    @staticmethod
    def read_visible_text(window_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts all visible text strings from controls, labels, and text documents in the window.
        """
        return UIAutomationEngine.read_visible_text(window_title=window_title)

    @staticmethod
    def wait_for_ui_element(name: str, timeout_seconds: float = 5.0) -> Dict[str, Any]:
        """
        Waits for a specific UI element to appear on screen.
        """
        return UIAutomationEngine.wait_for_element(name=name, timeout_seconds=timeout_seconds)

    # ==========================================
    # 8. MULTI-MONITOR & HARDWARE SENSORS
    # ==========================================
    @staticmethod
    def get_monitors_info() -> Dict[str, Any]:
        """
        Returns display configuration, resolutions, bounds, and primary monitor status.
        Useful for multi-monitor setups (e.g. 'What is on my second monitor?').
        """
        return MultiMonitorEngine.get_monitors()

    @staticmethod
    @guard("camera")
    def inspect_camera(prompt: str = "Describe what you see in front of the camera, especially any hand or held object.") -> Dict[str, Any]:
        """
        Temporarily captures a fresh frame from the camera directly in RAM and analyzes it.
        Strictly zero disk writes. Frame is discarded immediately after analysis.
        Transitions state to VISION ANALYZING during inspection.
        """
        prev_state = camera_subsystem.state
        camera_subsystem._set_state("VISION_ANALYZING")
        try:
            capture_res = camera_subsystem.capture_frame()
            if not capture_res.get("success"):
                return capture_res
            
            pil_img = capture_res["image"]
            from veda.vision import GeminiVisionProvider, LocalVisionProvider
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                provider = GeminiVisionProvider(api_key=api_key)
                result = provider.analyze(pil_img, prompt=prompt, is_camera=True)
                result["source"] = "camera"
                return result
            else:
                return {
                    "success": True,
                    "source": "camera",
                    "summary": "Camera frame captured in RAM (Gemini API key not configured for cloud vision)."
                }
        finally:
            if camera_subsystem.is_streaming:
                camera_subsystem._set_state("CAMERA_ACTIVE")
            else:
                camera_subsystem._set_state("CAMERA_OFF" if prev_state == "CAMERA_OFF" else "CAMERA_READY")

    @staticmethod
    @guard("camera")
    def start_camera_mouse() -> Dict[str, Any]:
        """
        Activates offline camera-based mouse control with real-time hand skeleton overlay.
        Allows the user to control the mouse cursor using their hand in front of the webcam.
        Gestures: Point (Cursor Move), Fist (Left Click), Two Fingers (Right Click),
        Thumb+Middle Pinch (Drag), Open Palm (Pause).
        Press ESC at any time to emergency stop.
        """
        ok = camera_mouse_controller.start()
        if ok:
            return {
                "success": True,
                "status": "Camera Mouse started successfully. Press ESC for emergency stop.",
                "diagnostics": camera_mouse_controller.get_diagnostics()
            }
        return {
            "success": False,
            "error": "Failed to start Camera Mouse. Check camera permission and availability."
        }

    @staticmethod
    def stop_camera_mouse() -> Dict[str, Any]:
        """
        Stops camera mouse tracking immediately, releases camera hardware,
        and ensures all mouse buttons are safely unheld.
        """
        camera_mouse_controller.stop()
        return {
            "success": True,
            "status": "Camera Mouse deactivated."
        }

    @staticmethod
    def get_camera_mouse_diagnostics() -> Dict[str, Any]:
        """
        Returns real-time diagnostics, FPS, active gesture, and CPU performance mode for Camera Mouse.
        """
        return {
            "success": True,
            "diagnostics": camera_mouse_controller.get_diagnostics()
        }

    # ==========================================
    # 9. SYSTEM SETTINGS & VOLUME CONTROLS
    # ==========================================
    @staticmethod
    def get_system_volume() -> Dict[str, Any]:
        """Gets master audio volume percentage and mute status."""
        return SystemSettingsEngine.get_master_volume()

    @staticmethod
    def set_system_volume(level_percent: int) -> Dict[str, Any]:
        """Sets master audio volume (0-100)."""
        return SystemSettingsEngine.set_master_volume(level_percent)

    @staticmethod
    def open_windows_settings(page_name: str) -> Dict[str, Any]:
        """
        Opens a Windows Settings page.
        Examples: 'wifi', 'bluetooth', 'display', 'sound', 'battery', 'storage', 'apps', 'update'
        """
        return SystemSettingsEngine.open_settings_page(page_name)

    # ==========================================
    # 10. ELEVATED / ADMIN OPERATIONS
    # ==========================================
    @staticmethod
    def run_elevated_command(command: str, reason: str) -> Dict[str, Any]:
        """
        Executes a command requiring administrator privileges via native Windows UAC elevation.
        Always explains the reason to the user.
        """
        return ElevationManager.run_elevated(command=command, reason=reason)

    # ==========================================
    # 11. AUTOMATIONS & CONDITION RULES
    # ==========================================
    @staticmethod
    def create_automation(condition_text: str) -> Dict[str, Any]:
        """
        Creates and persists a real background Windows automation rule from natural language.
        Examples:
        - "Jab meri battery 30% ho jaye to mujhe bata dena"
        - "Tell me when battery drops below 20%"
        - "CPU 90% se upar jaye to warn karna"
        - "Jab Wi-Fi disconnect ho to bol dena"
        """
        try:
            from veda.automation import automation_engine, AutomationEngine
            rule = AutomationEngine.parse_natural_language_rule(condition_text)
            if not rule:
                return {
                    "success": False,
                    "error": f"Could not parse automation condition from: '{condition_text}'. Please specify battery, CPU, or Wi-Fi conditions."
                }
            automation_engine.add_rule(rule)
            return {
                "success": True,
                "rule_id": rule.rule_id,
                "name": rule.name,
                "metric": rule.metric,
                "threshold": rule.threshold,
                "alert_message": rule.alert_message,
                "message": f"Automation created: {rule.name}. V.E.D.A. will monitor this locally."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def list_automations() -> Dict[str, Any]:
        """Lists all active and configured automation rules."""
        try:
            from veda.automation import automation_engine
            rules = automation_engine.get_rules()
            return {"success": True, "count": len(rules), "automations": rules}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def delete_automation(rule_id: str) -> Dict[str, Any]:
        """Deletes an automation rule by its ID."""
        try:
            from veda.automation import automation_engine
            deleted = automation_engine.delete_rule(rule_id)
            return {"success": deleted, "rule_id": rule_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

