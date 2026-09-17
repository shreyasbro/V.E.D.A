"""
V.E.D.A. Windows Control Engine
Deep Windows control: dynamic known folder resolution, dynamic application discovery,
File Explorer navigation, window state management, and action verification.
"""

import ctypes
from ctypes import wintypes
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple
import winreg

try:
    import win32api
    import win32con
    import win32gui
    import win32process
    import win32com.client
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    import pygetwindow as gw
    HAS_GW = True
except ImportError:
    HAS_GW = False


# Known Folder GUIDs for SHGetKnownFolderPath
KNOWN_FOLDER_GUIDS = {
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "music": "{4BD8D570-569F-4822-8700-1B2F2A632120}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
    "localappdata": "{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}",
    "appdata": "{3EB685FD-984F-4E5E-BB50-0CE8B8E8C8E1}",
    "programfiles": "{905e63b6-c1bf-494e-b29c-65b732d3d21a}",
    "programfilesx86": "{7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E}",
    "system": "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}",
    "windows": "{F38BF404-1D43-42F2-9305-67DE0B28FC23}",
}


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8)
    ]

    @classmethod
    def from_string(cls, guid_str: str):
        guid = cls()
        ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(guid_str), ctypes.byref(guid))
        return guid


class WindowsControlEngine:
    """Core engine for deep Windows control and dynamic system discovery."""

    _app_cache: Dict[str, str] = {}
    _app_cache_time: float = 0.0

    @classmethod
    def get_known_folder(cls, folder_name: str) -> Optional[str]:
        """
        Dynamically resolves standard Windows known folder paths using native SHGetKnownFolderPath.
        Works across all Windows configurations without hardcoding drive letters or usernames.
        """
        clean_name = folder_name.strip().lower()
        guid_str = KNOWN_FOLDER_GUIDS.get(clean_name)

        if guid_str:
            try:
                guid = GUID.from_string(guid_str)
                path_ptr = ctypes.c_wchar_p()
                res = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path_ptr))
                if res == 0 and path_ptr.value:
                    resolved = path_ptr.value
                    ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                    if os.path.exists(resolved):
                        return resolved
            except Exception:
                pass

        env_map = {
            "downloads": os.path.join(os.environ.get("USERPROFILE", ""), "Downloads"),
            "documents": os.path.join(os.environ.get("USERPROFILE", ""), "Documents"),
            "desktop": os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
            "pictures": os.path.join(os.environ.get("USERPROFILE", ""), "Pictures"),
            "music": os.path.join(os.environ.get("USERPROFILE", ""), "Music"),
            "videos": os.path.join(os.environ.get("USERPROFILE", ""), "Videos"),
            "localappdata": os.environ.get("LOCALAPPDATA", ""),
            "appdata": os.environ.get("APPDATA", ""),
            "windows": os.environ.get("WINDIR", "C:\\Windows"),
            "programfiles": os.environ.get("ProgramFiles", "C:\\Program Files"),
            "programfilesx86": os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        }

        path = env_map.get(clean_name)
        if path and os.path.exists(path):
            return path
        return None

    @classmethod
    def resolve_path(cls, path_query: str) -> str:
        """
        Resolves arbitrary paths, handles tildes, relative paths, known folder names,
        and quotes.
        """
        cleaned = path_query.strip().strip('"').strip("'")

        known = cls.get_known_folder(cleaned)
        if known:
            return known

        expanded = os.path.expandvars(os.path.expanduser(cleaned))
        if os.path.isabs(expanded):
            return expanded

        desktop_rel = os.path.join(cls.get_known_folder("desktop") or os.path.expanduser("~/Desktop"), expanded)
        if os.path.exists(desktop_rel):
            return desktop_rel

        return os.path.abspath(expanded)

    @classmethod
    def navigate_file_explorer(cls, target_path: str) -> Dict[str, Any]:
        """
        Navigates File Explorer directly to the target directory or selects the specified file.
        Uses COM automation to update existing Explorer windows or launches a new one.
        Guarantees the target folder is opened without getting stuck at Quick Access.
        """
        resolved = cls.resolve_path(target_path)
        if not os.path.exists(resolved):
            user_home = os.environ.get("USERPROFILE", "")
            alt_path = os.path.join(user_home, target_path.strip("/\\"))
            if os.path.exists(alt_path):
                resolved = alt_path
            else:
                return {
                    "success": False,
                    "error": f"Path '{target_path}' does not exist (resolved to '{resolved}')."
                }

        is_file = os.path.isfile(resolved)
        folder_to_open = os.path.dirname(resolved) if is_file else resolved

        navigated = False
        method_used = "process"

        if HAS_WIN32:
            try:
                shell = win32com.client.Dispatch("Shell.Application")
                windows = shell.Windows()
                for i in range(windows.Count):
                    w = windows.Item(i)
                    if w and hasattr(w, "LocationURL"):
                        url = str(w.LocationURL or "")
                        name = str(w.Name or "").lower()
                        if "explorer" in name or "file explorer" in name:
                            norm_folder = folder_to_open.replace("\\", "/")
                            w.Navigate(f"file:///{norm_folder}")
                            hwnd = getattr(w, "HWND", 0)
                            if hwnd:
                                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                                win32gui.SetForegroundWindow(hwnd)
                            navigated = True
                            method_used = "shell_com_reuse"
                            break
            except Exception:
                navigated = False

        if not navigated:
            try:
                if is_file:
                    os.system(f'explorer.exe /select,"{resolved}"')
                else:
                    os.startfile(folder_to_open)
                navigated = True
                method_used = "startfile"
            except Exception:
                try:
                    os.system(f'explorer.exe "{folder_to_open}"')
                    navigated = True
                    method_used = "explorer_cmd"
                except Exception as e:
                    return {"success": False, "error": f"Failed to open File Explorer: {e}"}

        time.sleep(0.6)
        folder_basename = os.path.basename(folder_to_open)
        open_wins = cls.find_windows(folder_basename or "File Explorer")

        return {
            "success": True,
            "action": "navigate_file_explorer",
            "target_path": resolved,
            "opened_folder": folder_to_open,
            "method": method_used,
            "verified": len(open_wins) > 0,
            "active_window": open_wins[0]["title"] if open_wins else "File Explorer"
        }

    @classmethod
    def discover_installed_applications(cls, force_refresh: bool = False) -> Dict[str, str]:
        """
        Scans Windows Start Menu, Registry App Paths, and common install locations.
        Builds a comprehensive name -> executable/command path mapping.
        """
        now = time.time()
        if not force_refresh and cls._app_cache and (now - cls._app_cache_time < 300):
            return cls._app_cache

        apps: Dict[str, str] = {}

        reg_keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        ]

        for root_key, subkey in reg_keys:
            try:
                with winreg.OpenKey(root_key, subkey) as key:
                    count = winreg.QueryInfoKey(key)[0]
                    for i in range(count):
                        try:
                            app_key_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, app_key_name) as app_sub:
                                exec_path, _ = winreg.QueryValueEx(app_sub, None)
                                if exec_path and os.path.exists(exec_path):
                                    name_stem = os.path.splitext(app_key_name)[0].lower()
                                    apps[name_stem] = exec_path
                                    apps[app_key_name.lower()] = exec_path
                        except Exception:
                            continue
            except Exception:
                continue

        start_dirs = [
            os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        ]

        shell = None
        if HAS_WIN32:
            try:
                shell = win32com.client.Dispatch("WScript.Shell")
            except Exception:
                shell = None

        for sdir in start_dirs:
            if not os.path.exists(sdir):
                continue
            for root, _, files in os.walk(sdir):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        name_stem = os.path.splitext(f)[0].lower()
                        lnk_path = os.path.join(root, f)
                        if shell:
                            try:
                                shortcut = shell.CreateShortcut(lnk_path)
                                target_path = shortcut.TargetPath
                                if target_path and os.path.exists(target_path):
                                    apps[name_stem] = target_path
                                    clean_stem = re.sub(r"[^a-zA-Z0-9\s]", " ", name_stem).strip()
                                    if clean_stem and clean_stem != name_stem:
                                        apps[clean_stem] = target_path
                                    continue
                            except Exception:
                                pass
                        apps[name_stem] = lnk_path

        builtin_defaults = {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "paint": "mspaint.exe",
            "mspaint": "mspaint.exe",
            "cmd": "cmd.exe",
            "command prompt": "cmd.exe",
            "powershell": "powershell.exe",
            "terminal": "wt.exe",
            "windows terminal": "wt.exe",
            "explorer": "explorer.exe",
            "file explorer": "explorer.exe",
            "taskmgr": "taskmgr.exe",
            "task manager": "taskmgr.exe",
            "chrome": "chrome.exe",
            "google chrome": "chrome.exe",
            "edge": "msedge.exe",
            "microsoft edge": "msedge.exe",
            "vscode": "code.cmd",
            "code": "code.cmd",
            "settings": "ms-settings:",
            "windows settings": "ms-settings:",
        }
        for k, v in builtin_defaults.items():
            if k not in apps:
                apps[k] = v

        cls._app_cache = apps
        cls._app_cache_time = now
        return apps

    @classmethod
    def find_application(cls, query: str) -> Optional[str]:
        """
        Dynamically finds the executable or shortcut path for an application query.
        Uses fuzzy token matching across discovered applications, registry, and PATH.
        """
        clean_q = query.strip().lower()
        apps = cls.discover_installed_applications()

        if clean_q in apps:
            return apps[clean_q]

        which_res = shutil.which(clean_q)
        if which_res:
            return which_res
        if not clean_q.endswith(".exe"):
            which_res_exe = shutil.which(f"{clean_q}.exe")
            if which_res_exe:
                return which_res_exe

        q_tokens = set(re.findall(r"\w+", clean_q))
        best_match = None
        best_score = 0

        for app_name, app_path in apps.items():
            name_tokens = set(re.findall(r"\w+", app_name))
            if q_tokens == name_tokens:
                return app_path
            overlap = len(q_tokens.intersection(name_tokens))
            if overlap > best_score:
                best_score = overlap
                best_match = app_path

        if best_score > 0 and best_match:
            return best_match

        for app_name, app_path in apps.items():
            if clean_q in app_name or app_name in clean_q:
                return app_path

        return None

    @classmethod
    def launch_application(cls, app_name_or_path: str, arguments: Optional[str] = None) -> Dict[str, Any]:
        """
        Launches an application reliably with action verification.
        """
        target = cls.find_application(app_name_or_path) or app_name_or_path.strip()

        if target.endswith(":"):
            try:
                os.startfile(target)
                time.sleep(1.0)
                return {
                    "success": True,
                    "application": app_name_or_path,
                    "target": target,
                    "verified": True,
                    "status": "Launched system URI protocol"
                }
            except Exception as e:
                return {"success": False, "error": f"Failed launching URI {target}: {e}"}

        try:
            if arguments:
                full_cmd = f'\"{target}\" {arguments}'
            else:
                full_cmd = f'\"{target}\"'

            if os.path.exists(target) and (target.lower().endswith(".lnk") or target.lower().endswith(".exe")):
                os.startfile(target)
            else:
                from veda.process_runner import ControlledProcessRunner
                res = ControlledProcessRunner.run_command(f'start "" {full_cmd}', timeout=10)
                if not res.get("success"):
                    os.system(f'start "" {full_cmd}')

            time.sleep(1.2)

            clean_name = os.path.splitext(os.path.basename(target))[0].lower()
            matching_windows = cls.find_windows(clean_name)
            if not matching_windows:
                matching_windows = cls.find_windows(app_name_or_path)

            return {
                "success": True,
                "application": app_name_or_path,
                "resolved_target": target,
                "verified": len(matching_windows) > 0,
                "window": matching_windows[0]["title"] if matching_windows else None,
                "status": "Application launched successfully"
            }
        except Exception as e:
            return {"success": False, "error": f"Error launching '{app_name_or_path}': {e}"}

    @classmethod
    def find_windows(cls, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Enumerates all active desktop windows with HWND, PID, titles, and rectangles.
        """
        results: List[Dict[str, Any]] = []

        if not HAS_WIN32:
            if HAS_GW:
                wins = gw.getAllWindows()
                for w in wins:
                    if w.title and w.title.strip():
                        if not query or query.lower() in w.title.lower():
                            results.append({
                                "title": w.title,
                                "hwnd": getattr(w, "_hWnd", 0),
                                "is_minimized": bool(w.isMinimized),
                                "is_maximized": bool(w.isMaximized),
                                "is_active": bool(w.isActive),
                                "bounds": {"left": w.left, "top": w.top, "width": w.width, "height": w.height}
                            })
            return results

        def enum_handler(hwnd, extra):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).strip()
                    if title:
                        if not query or query.lower() in title.lower():
                            try:
                                rect = win32gui.GetWindowRect(hwnd)
                                bounds = {
                                    "left": rect[0],
                                    "top": rect[1],
                                    "right": rect[2],
                                    "bottom": rect[3],
                                    "width": rect[2] - rect[0],
                                    "height": rect[3] - rect[1]
                                }
                            except Exception:
                                bounds = {"left": 0, "top": 0, "right": 0, "bottom": 0, "width": 0, "height": 0}

                            try:
                                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            except Exception:
                                pid = 0

                            try:
                                placement = win32gui.GetWindowPlacement(hwnd)
                                state_code = placement[1] if placement else 1
                            except Exception:
                                state_code = 1

                            results.append({
                                "title": title,
                                "hwnd": hwnd,
                                "pid": pid,
                                "is_minimized": state_code == win32con.SW_SHOWMINIMIZED,
                                "is_maximized": state_code == win32con.SW_SHOWMAXIMIZED,
                                "is_active": hwnd == win32gui.GetForegroundWindow(),
                                "bounds": bounds
                            })
            except Exception:
                pass
            return True

        win32gui.EnumWindows(enum_handler, None)
        return results

    @classmethod
    def get_window_state(cls, window_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Gets detailed state (position, size, visibility, minimized/maximized) of a window.
        """
        if window_title:
            matches = cls.find_windows(window_title)
            if not matches:
                return {"success": False, "error": f"No window matching '{window_title}' found."}
            w = matches[0]
            return {"success": True, "window": w}

        if HAS_WIN32:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd or not win32gui.IsWindow(hwnd):
                # If no active foreground window (e.g. headless task), return desktop/none state safely
                return {
                    "success": True,
                    "window": {
                        "title": "Desktop",
                        "hwnd": 0,
                        "pid": 0,
                        "is_minimized": False,
                        "is_maximized": True,
                        "is_active": False,
                        "bounds": {"left": 0, "top": 0, "right": 0, "bottom": 0, "width": 0, "height": 0}
                    }
                }
            try:
                title = win32gui.GetWindowText(hwnd).strip()
                rect = win32gui.GetWindowRect(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                placement = win32gui.GetWindowPlacement(hwnd)
                state_code = placement[1] if placement else 1
                return {
                    "success": True,
                    "window": {
                        "title": title or "Foreground Window",
                        "hwnd": hwnd,
                        "pid": pid,
                        "is_minimized": state_code == win32con.SW_SHOWMINIMIZED,
                        "is_maximized": state_code == win32con.SW_SHOWMAXIMIZED,
                        "is_active": True,
                        "bounds": {
                            "left": rect[0], "top": rect[1], "right": rect[2], "bottom": rect[3],
                            "width": rect[2] - rect[0], "height": rect[3] - rect[1]
                        }
                    }
                }
            except Exception as e:
                return {"success": False, "error": f"Failed reading foreground window: {e}"}

        return {"success": False, "error": "win32gui not available."}

    @classmethod
    def focus_window(cls, window_title: str) -> Dict[str, Any]:
        """
        Brings the matching window to foreground, restoring it if minimized.
        """
        matches = cls.find_windows(window_title)
        if not matches:
            return {"success": False, "error": f"No window matching '{window_title}' found."}

        target = matches[0]
        hwnd = target["hwnd"]

        if HAS_WIN32:
            try:
                if target.get("is_minimized"):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                else:
                    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.3)
                verified = (win32gui.GetForegroundWindow() == hwnd)
                return {
                    "success": True,
                    "focused_window": target["title"],
                    "verified": verified
                }
            except Exception as e:
                return {"success": False, "error": f"Failed focusing window: {e}"}

        return {"success": False, "error": "Window focus failed."}

    @classmethod
    def move_window(cls, window_title: str, x: int, y: int) -> Dict[str, Any]:
        """Moves a window to coordinates (x, y) while preserving width and height."""
        matches = cls.find_windows(window_title)
        if not matches:
            return {"success": False, "error": f"No window matching '{window_title}' found."}

        target = matches[0]
        hwnd = target["hwnd"]
        bounds = target["bounds"]

        if HAS_WIN32:
            try:
                win32gui.MoveWindow(hwnd, x, y, bounds["width"], bounds["height"], True)
                return {"success": True, "window": target["title"], "moved_to": {"x": x, "y": y}}
            except Exception as e:
                return {"success": False, "error": f"Failed moving window: {e}"}

        return {"success": False, "error": "win32gui not available."}

    @classmethod
    def resize_window(cls, window_title: str, width: int, height: int) -> Dict[str, Any]:
        """Resizes a window while preserving its current top-left position."""
        matches = cls.find_windows(window_title)
        if not matches:
            return {"success": False, "error": f"No window matching '{window_title}' found."}

        target = matches[0]
        hwnd = target["hwnd"]
        bounds = target["bounds"]

        if HAS_WIN32:
            try:
                win32gui.MoveWindow(hwnd, bounds["left"], bounds["top"], width, height, True)
                return {"success": True, "window": target["title"], "resized_to": {"width": width, "height": height}}
            except Exception as e:
                return {"success": False, "error": f"Failed resizing window: {e}"}

        return {"success": False, "error": "win32gui not available."}

    @classmethod
    def wait_for_window(cls, window_title: str, timeout_seconds: float = 5.0) -> Dict[str, Any]:
        """Waits until a window matching window_title is open and visible."""
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            matches = cls.find_windows(window_title)
            if matches:
                return {
                    "success": True,
                    "window": matches[0]["title"],
                    "waited_seconds": round(time.time() - start_time, 2)
                }
            time.sleep(0.3)

        return {
            "success": False,
            "error": f"Timed out waiting for window matching '{window_title}' after {timeout_seconds}s."
        }

    @classmethod
    def verify_action(cls, action_type: str, target: str) -> Dict[str, Any]:
        """
        Verifies the outcome of an action (application launched, file created, folder open).
        Follows PLAN -> ACT -> OBSERVE -> VERIFY loop.
        """
        clean_action = action_type.strip().lower()

        if clean_action in ["app", "application", "window"]:
            wins = cls.find_windows(target)
            return {
                "verified": len(wins) > 0,
                "action_type": action_type,
                "target": target,
                "details": f"Found {len(wins)} matching window(s)" if wins else "No matching windows found."
            }

        elif clean_action in ["folder", "directory", "file", "path"]:
            resolved = cls.resolve_path(target)
            exists = os.path.exists(resolved)
            return {
                "verified": exists,
                "action_type": action_type,
                "target": target,
                "resolved_path": resolved,
                "details": "Path exists on disk." if exists else "Path does not exist."
            }

        return {"verified": False, "error": f"Unknown action_type '{action_type}' for verification."}
