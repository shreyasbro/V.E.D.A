import os
import time
import subprocess
from typing import Any, Dict, List, Optional
import pyautogui
import pygetwindow as gw
import pyperclip
from PIL import Image

from veda.core.types import ToolDefinition, ToolResult

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

class WindowsTools:
    """Real Windows system automation tools."""

    @staticmethod
    def get_active_window() -> ToolResult:
        try:
            w = gw.getActiveWindow()
            if w:
                return ToolResult(True, {"title": w.title, "is_maximized": w.isMaximized, "is_active": w.isActive})
            return ToolResult(True, {"title": "Desktop / None", "is_active": False})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def get_open_windows() -> ToolResult:
        try:
            titles = [w.title for w in gw.getAllWindows() if w.title and w.title.strip()]
            unique_titles = sorted(list(set(titles)))
            return ToolResult(True, {"open_windows": unique_titles, "count": len(unique_titles)})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def take_screenshot(save_path: Optional[str] = None) -> ToolResult:
        try:
            img = pyautogui.screenshot()
            if not save_path:
                temp_dir = os.path.join(os.path.expanduser("~"), ".veda", "screenshots")
                os.makedirs(temp_dir, exist_ok=True)
                save_path = os.path.join(temp_dir, f"screenshot_{int(time.time())}.png")
            img.save(save_path)
            return ToolResult(True, {"saved_path": save_path, "size": img.size})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def open_application(application: str) -> ToolResult:
        try:
            pyautogui.hotkey("win", "r")
            time.sleep(0.35)
            pyautogui.write(application, interval=0.03)
            pyautogui.press("enter")
            time.sleep(1.2)
            # Verify if handle materialized or returned
            return ToolResult(True, {"launched": application, "method": "Win+R"})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def focus_window(title_query: str) -> ToolResult:
        try:
            windows = gw.getWindowsWithTitle(title_query)
            if windows:
                w = windows[0]
                if w.isMinimized:
                    w.restore()
                w.activate()
                time.sleep(0.3)
                return ToolResult(True, {"focused": w.title})
            return ToolResult(False, error=f"No window matching '{title_query}' found to focus.")
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def type_text(text: str) -> ToolResult:
        try:
            # Type characters with natural cadence
            for ch in text:
                pyautogui.write(ch)
                time.sleep(0.02)
            return ToolResult(True, {"typed_characters": len(text)})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def press_key(key: str) -> ToolResult:
        try:
            clean_key = key.strip().lower()
            if "+" in clean_key:
                keys = [k.strip() for k in clean_key.split("+")]
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(clean_key)
            return ToolResult(True, {"pressed": key})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def mouse_move(x: int, y: int) -> ToolResult:
        try:
            pyautogui.moveTo(x, y, duration=0.3)
            return ToolResult(True, {"moved_to": [x, y]})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def mouse_click(x: Optional[int] = None, y: Optional[int] = None, clicks: int = 1) -> ToolResult:
        try:
            if x is not None and y is not None:
                pyautogui.moveTo(x, y, duration=0.2)
            if clicks == 2:
                pyautogui.doubleClick()
            elif clicks == 3:
                pyautogui.tripleClick()
            else:
                pyautogui.click()
            return ToolResult(True, {"clicked": True, "clicks": clicks})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def scroll(clicks: int) -> ToolResult:
        try:
            pyautogui.scroll(clicks)
            return ToolResult(True, {"scrolled": clicks})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def list_directory(path: Optional[str] = None) -> ToolResult:
        try:
            target = path or os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.exists(target):
                return ToolResult(False, error=f"Directory '{target}' does not exist.")
            items = os.listdir(target)[:30]
            return ToolResult(True, {"directory": target, "items": items})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def read_text_file(path: str) -> ToolResult:
        try:
            if not os.path.exists(path):
                return ToolResult(False, error=f"File '{path}' does not exist.")
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(4000)
            return ToolResult(True, {"file_path": path, "content": content})
        except Exception as e:
            return ToolResult(False, error=str(e))

    @staticmethod
    def write_text_file(path: str, content: str) -> ToolResult:
        try:
            # Resolve relative to Desktop if user provides simple filename
            if not os.path.isabs(path):
                path = os.path.join(os.path.expanduser("~"), "Desktop", path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(True, {"created_file": path, "bytes_written": len(content)})
        except Exception as e:
            return ToolResult(False, error=str(e))
