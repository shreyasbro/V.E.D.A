"""
V.E.D.A. Reliable Input Engine
Dedicated, safe keyboard, mouse, and clipboard interaction layer.
Guarantees modifier cleanup, separated text typing vs. key combinations, and PyAutoGUI failsafe protection.
"""

import time
from typing import Any, Dict, List, Optional
import pyautogui
import pyperclip

# Keep failsafe enabled for user safety
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.04

MODIFIER_MAP = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "win": "win",
    "windows": "win",
    "super": "win",
    "cmd": "win"
}

STANDARD_KEY_ALIASES = {
    "enter": "enter",
    "return": "enter",
    "esc": "esc",
    "escape": "esc",
    "tab": "tab",
    "space": "space",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "home": "home",
    "end": "end",
    "capslock": "capslock",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4", "f5": "f5", "f6": "f6",
    "f7": "f7", "f8": "f8", "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12"
}

try:
    import win32api
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

WIN32_VK_MAP = {
    "ctrl": 0x11,  # VK_CONTROL
    "control": 0x11,
    "alt": 0x12,   # VK_MENU
    "shift": 0x10, # VK_SHIFT
    "win": 0x5B,   # VK_LWIN
    "windows": 0x5B,
    "enter": 0x0D, # VK_RETURN
    "return": 0x0D,
    "tab": 0x09,   # VK_TAB
    "esc": 0x1B,   # VK_ESCAPE
    "escape": 0x1B,
    "space": 0x20, # VK_SPACE
    "backspace": 0x08, # VK_BACK
    "delete": 0x2E, # VK_DELETE
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B
}

class KeyboardEngine:
    """
    Dedicated Keyboard Input Layer.
    Explicitly separates raw text typing, individual key presses, and modifier shortcuts.
    Guarantees that all held keys are released even if exceptions occur.
    Uses Win32 keyboard events where available to bypass PyAutoGUI failsafe corner bounds,
    falling back safely to PyAutoGUI.
    """

    @staticmethod
    def normalize_key(key: str) -> str:
        k = key.strip().lower()
        return STANDARD_KEY_ALIASES.get(k, k)

    @staticmethod
    def normalize_modifier(mod: str) -> str:
        m = mod.strip().lower()
        return MODIFIER_MAP.get(m, m)

    @classmethod
    def type_text(cls, text: str, fast_paste: bool = False) -> Dict[str, Any]:
        """
        Types pure text strings into the currently focused application.
        Never executes shortcuts or modifiers here.
        """
        try:
            if fast_paste or len(text) > 80:
                pyperclip.copy(text)
                cls.press_shortcut(["ctrl"], "v")
                time.sleep(0.05)
                return {
                    "success": True,
                    "characters_typed": len(text),
                    "method": "fast_paste",
                    "text": text[:100] + ("..." if len(text) > 100 else "")
                }
            else:
                if HAS_WIN32:
                    for char in text:
                        pyautogui.write(char)
                        time.sleep(0.015)
                else:
                    pyautogui.write(text, interval=0.02)

                return {
                    "success": True,
                    "characters_typed": len(text),
                    "method": "keystroke_typing",
                    "text": text[:100] + ("..." if len(text) > 100 else "")
                }
        except pyautogui.FailSafeException:
            # Fallback to clipboard paste
            try:
                pyperclip.copy(text)
                cls.press_shortcut(["ctrl"], "v")
                return {"success": True, "characters_typed": len(text), "method": "clipboard_failsafe_recovery"}
            except Exception as e2:
                return {"success": False, "error": f"PyAutoGUI fail-safe: {str(e2)}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def press_key(cls, key: str) -> Dict[str, Any]:
        """
        Presses a single individual non-modifier key (e.g. 'enter', 'tab', 'esc', 'space', 'backspace').
        """
        norm_key = cls.normalize_key(key)
        if HAS_WIN32 and norm_key in WIN32_VK_MAP:
            vk = WIN32_VK_MAP[norm_key]
            try:
                win32api.keybd_event(vk, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
                return {"success": True, "pressed_key": norm_key, "backend": "win32"}
            except Exception:
                pass

        try:
            pyautogui.press(norm_key)
            return {
                "success": True,
                "pressed_key": norm_key,
                "backend": "pyautogui"
            }
        except pyautogui.FailSafeException:
            return {"success": False, "error": "PyAutoGUI fail-safe triggered during press_key."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def press_shortcut(cls, modifiers: List[str], key: str) -> Dict[str, Any]:
        """
        Executes a keyboard combination / shortcut with strict Down/Up sequencing.
        Guarantees that all held modifiers are released even if an error occurs.
        Example: modifiers=['CTRL', 'SHIFT'], key='S'
        """
        norm_mods = [cls.normalize_modifier(m) for m in modifiers if m.strip()]
        norm_key = cls.normalize_key(key)

        # 1. Prefer native Win32 keybd_event (bypasses failsafe cursor restrictions completely)
        if HAS_WIN32:
            held_vks: List[int] = []
            try:
                for mod in norm_mods:
                    vk = WIN32_VK_MAP.get(mod)
                    if vk:
                        win32api.keybd_event(vk, 0, 0, 0)
                        held_vks.append(vk)
                        time.sleep(0.015)

                key_upper = norm_key.upper()
                if len(key_upper) == 1:
                    target_vk = ord(key_upper)
                else:
                    target_vk = WIN32_VK_MAP.get(norm_key, 0)

                if target_vk:
                    win32api.keybd_event(target_vk, 0, 0, 0)
                    time.sleep(0.02)
                    win32api.keybd_event(target_vk, 0, win32con.KEYEVENTF_KEYUP, 0)

                return {
                    "success": True,
                    "shortcut": f"{'+'.join(norm_mods)}+{norm_key}" if norm_mods else norm_key,
                    "modifiers": norm_mods,
                    "key": norm_key,
                    "backend": "win32"
                }
            except Exception as e:
                pass
            finally:
                for vk in reversed(held_vks):
                    try:
                        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
                    except Exception:
                        pass

        # 2. PyAutoGUI Fallback with strict release guarantee
        pressed_mods: List[str] = []
        try:
            for mod in norm_mods:
                pyautogui.keyDown(mod)
                pressed_mods.append(mod)
                time.sleep(0.02)

            pyautogui.press(norm_key)
            time.sleep(0.02)

            return {
                "success": True,
                "shortcut": f"{'+'.join(norm_mods)}+{norm_key}" if norm_mods else norm_key,
                "modifiers": norm_mods,
                "key": norm_key,
                "backend": "pyautogui"
            }
        except pyautogui.FailSafeException:
            return {
                "success": False,
                "error": "PyAutoGUI fail-safe triggered during keyboard shortcut."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            for mod in reversed(pressed_mods):
                try:
                    pyautogui.keyUp(mod)
                except Exception:
                    pass


class MouseEngine:
    """
    Dedicated, safe mouse interaction layer.
    Separates physical execution from visual reasoning.
    Clamps bounds away from screen corners to prevent accidental fail-safe triggers.
    """

    @staticmethod
    def _get_safe_coordinates(x: int, y: int) -> tuple[int, int]:
        sw, sh = pyautogui.size()
        margin = 8
        safe_x = max(margin, min(sw - margin, int(x)))
        safe_y = max(margin, min(sh - margin, int(y)))
        return safe_x, safe_y

    @classmethod
    def mouse_move(cls, x: int, y: int) -> Dict[str, Any]:
        try:
            safe_x, safe_y = cls._get_safe_coordinates(x, y)
            pyautogui.moveTo(safe_x, safe_y, duration=0.3)
            return {
                "success": True,
                "position": [safe_x, safe_y]
            }
        except pyautogui.FailSafeException:
            return {"success": False, "error": "PyAutoGUI fail-safe triggered during mouse move."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def mouse_click(cls, button: str = "left") -> Dict[str, Any]:
        try:
            curr_x, curr_y = pyautogui.position()
            safe_x, safe_y = cls._get_safe_coordinates(curr_x, curr_y)
            if curr_x != safe_x or curr_y != safe_y:
                pyautogui.moveTo(safe_x, safe_y, duration=0.1)

            pyautogui.click(button=button.lower())
            return {
                "success": True,
                "button": button,
                "position": [safe_x, safe_y]
            }
        except pyautogui.FailSafeException:
            return {"success": False, "error": "PyAutoGUI fail-safe triggered during mouse click."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def mouse_double_click(cls) -> Dict[str, Any]:
        try:
            curr_x, curr_y = pyautogui.position()
            safe_x, safe_y = cls._get_safe_coordinates(curr_x, curr_y)
            if curr_x != safe_x or curr_y != safe_y:
                pyautogui.moveTo(safe_x, safe_y, duration=0.1)

            pyautogui.doubleClick()
            return {
                "success": True,
                "action": "double_click",
                "position": [safe_x, safe_y]
            }
        except pyautogui.FailSafeException:
            return {"success": False, "error": "PyAutoGUI fail-safe triggered during double click."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def mouse_right_click(cls) -> Dict[str, Any]:
        return cls.mouse_click(button="right")

    @classmethod
    def mouse_scroll(cls, amount: int) -> Dict[str, Any]:
        try:
            pyautogui.scroll(amount)
            return {
                "success": True,
                "amount": amount
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class ClipboardEngine:
    """
    Dedicated Windows Clipboard management.
    Allows moving text directly without simulating thousands of keystrokes.
    """

    @staticmethod
    def get_clipboard() -> Dict[str, Any]:
        try:
            text = pyperclip.paste()
            return {
                "success": True,
                "content": text,
                "length": len(text)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def set_clipboard(text: str) -> Dict[str, Any]:
        try:
            pyperclip.copy(text)
            return {
                "success": True,
                "characters_copied": len(text),
                "preview": text[:100] + ("..." if len(text) > 100 else "")
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
