import os
import sys
import json
import winreg
from typing import Any, Dict, List
from dotenv import load_dotenv

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".veda")
CONFIG_PATH = os.path.join(CONFIG_DIR, "veda_config.json")
HISTORY_PATH = os.path.join(CONFIG_DIR, "chat_history.json")
CACHE_DIR = os.path.join(CONFIG_DIR, "cache")
SCREENSHOT_FILE = os.path.join(CACHE_DIR, "veda_current_screen.png")
KOKORO_MODELS_DIR = os.path.join(CONFIG_DIR, "models", "kokoro")
UPDATE_CACHE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "V.E.D.A", "updates")

DEFAULT_CONFIG: Dict[str, Any] = {
    "identity": {
        "name": "V.E.D.A.",
        "full_name": "Virtual Executive Desktop Assistant",
        "creator": "Shreyas",
        "author": "Shreyas",
        "description": "An autonomous Windows desktop AI assistant created by Shreyas."
    },
    "settings": {
        "start_with_windows": False,
        "desktop_mode": False,
        "desktop_geometry": "380x540+100+100",
        "first_run_completed": False,
        "mic_mode": "mic_toggle",
        "camera_orientation": "Normal",
        "camera_mirror": False,
        "camera_rotation": 0,
        "local_ai_fallback": False,
        "provider_mode": "AUTOMATIC",
        "tts_provider_mode": "LOCAL",
        "tts_selected_provider": "Kokoro",
        "kokoro_voice": "af_heart",
        "kokoro_speed": 1.0,
        "kokoro_perf_mode": "AUTO",
        "camera_mouse_enabled": False,
        "camera_mouse_sensitivity": 1.8,
        "camera_mouse_smoothing": 0.45,
        "camera_mouse_deadzone": 0.003,
        "camera_mouse_deadzone_mode": "Adaptive",
        "camera_mouse_deadzone_px": 3.5,
        "camera_mouse_pinch_sensitivity": 1.0,
        "camera_mouse_click_stability": "High",
        "camera_mouse_prediction": 0.015,
        "camera_mouse_one_euro_min_cutoff": 1.2,
        "camera_mouse_one_euro_beta": 0.02,
        "camera_mouse_click_debounce": 0.25,
        "camera_mouse_debounce_preset": "Low",
        "camera_mouse_tracking_fps": 30,
        "camera_mouse_resolution": "640x480",
        "camera_mouse_emergency_key": "Escape",
        "camera_mouse_left_gesture": "Pinch (Thumb + Index)",
        "camera_mouse_right_gesture": "Two Fingers Extended",
        "update_auto_check": True,
        "update_auto_download": False,
        "update_auto_install": False,
        "update_ask_before_restart": True,
        "update_notifications": True,
        "notification_sounds": False,
        "github_owner": "shreyasbro",
        "github_repo": "V.E.D.A"
    },
    "permissions": {
        "computer_control": True,
        "file_access": True,
        "live_screen": False,
        "microphone": False,
        "camera": False,
        "gemini_network": True,
        "elevated_operations": "ask_every_time"
    }
}

class VedaConfig:
    """Manages persistent config, identity, and Windows startup for V.E.D.A."""

    @classmethod
    def ensure_directories(cls):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        os.makedirs(KOKORO_MODELS_DIR, exist_ok=True)

    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        cls.ensure_directories()
        if not os.path.exists(CONFIG_PATH):
            cls.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["identity"] = DEFAULT_CONFIG["identity"]
                if "settings" not in data:
                    data["settings"] = DEFAULT_CONFIG["settings"]
                else:
                    for k, v in DEFAULT_CONFIG["settings"].items():
                        if k not in data["settings"]:
                            data["settings"][k] = v
                if "permissions" not in data:
                    data["permissions"] = DEFAULT_CONFIG["permissions"]
                else:
                    for k, v in DEFAULT_CONFIG["permissions"].items():
                        if k not in data["permissions"]:
                            data["permissions"][k] = v
                return data
        except Exception:
            return DEFAULT_CONFIG

    @classmethod
    def save_config(cls, config: Dict[str, Any]):
        cls.ensure_directories()
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"[VedaConfig] Error saving config: {e}")

    @classmethod
    def get_identity(cls) -> Dict[str, str]:
        config = cls.load_config()
        return config.get("identity", DEFAULT_CONFIG["identity"])

    @classmethod
    def get_settings(cls) -> Dict[str, Any]:
        config = cls.load_config()
        return config.get("settings", DEFAULT_CONFIG["settings"])

    @classmethod
    def update_setting(cls, key: str, value: Any):
        config = cls.load_config()
        config.setdefault("settings", {})[key] = value
        cls.save_config(config)

    @classmethod
    def get_permissions(cls) -> Dict[str, Any]:
        config = cls.load_config()
        return config.get("permissions", DEFAULT_CONFIG["permissions"])

    @classmethod
    def update_permission(cls, key: str, value: Any):
        config = cls.load_config()
        config.setdefault("permissions", {})[key] = value
        cls.save_config(config)

    @classmethod
    def is_first_run(cls) -> bool:
        settings = cls.get_settings()
        return not bool(settings.get("first_run_completed", False))

    @classmethod
    def mark_first_run_completed(cls):
        cls.update_setting("first_run_completed", True)

    @classmethod
    def reset_first_run(cls):
        cls.update_setting("first_run_completed", False)

    @classmethod
    def set_start_with_windows(cls, enable: bool) -> bool:
        """Sets or removes V.E.D.A. in the Windows Registry Run key."""
        cls.update_setting("start_with_windows", enable)
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "run_veda.bat"))
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "VEDA_Assistant"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as reg_key:
                if enable:
                    winreg.SetValueEx(reg_key, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
                else:
                    try:
                        winreg.DeleteValue(reg_key, app_name)
                    except FileNotFoundError:
                        pass
            return True
        except Exception as e:
            print(f"[VedaConfig] Error configuring Windows startup: {e}")
            return False

    @classmethod
    def load_history(cls) -> List[Dict[str, Any]]:
        cls.ensure_directories()
        if not os.path.exists(HISTORY_PATH):
            return []
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    @classmethod
    def save_history(cls, history: List[Dict[str, Any]]):
        cls.ensure_directories()
        try:
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(history[-100:], f, indent=2)
        except Exception as e:
            print(f"[VedaConfig] Error saving history: {e}")

    @classmethod
    def append_history(cls, sender: str, text: str, action_tag: str = ""):
        history = cls.load_history()
        history.append({
            "sender": sender,
            "text": text,
            "action_tag": action_tag
        })
        cls.save_history(history)

    @classmethod
    def get_env_path(cls) -> str:
        """
        Dynamically discovers the .env file path across environments:
        1. PyInstaller frozen app directory (sys._MEIPASS or dir of sys.executable)
        2. Project root directory relative to this source file
        3. User config directory ~/.veda/.env (fallback)
        """
        # Check PyInstaller frozen directory
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            exe_env = os.path.join(exe_dir, ".env")
            if os.path.exists(exe_env):
                return exe_env
            if hasattr(sys, "_MEIPASS"):
                bundle_env = os.path.join(sys._MEIPASS, ".env")
                if os.path.exists(bundle_env):
                    return bundle_env

        # Check source project root
        project_root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
        if os.path.exists(project_root_env):
            return project_root_env

        # Fallback to user config directory
        cls.ensure_directories()
        user_env = os.path.join(CONFIG_DIR, ".env")
        return user_env

    @classmethod
    def load_environment(cls):
        """Loads environment variables safely from the resolved .env path."""
        env_path = cls.get_env_path()
        if os.path.exists(env_path):
            load_dotenv(dotenv_path=env_path, override=True)

    @classmethod
    def set_env_variable(cls, key: str, value: str):
        """Persists or updates an environment variable in the resolved .env and os.environ."""
        os.environ[key] = value
        env_path = cls.get_env_path()
        parent_dir = os.path.dirname(env_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    @classmethod
    def clean_api_key(cls, key: Any) -> str:
        """Sanitizes an API key by stripping quotes, whitespace, newlines, and accidental Bearer prefix."""
        if not key:
            return ""
        s = str(key).strip()
        # Remove outer quotes if user or env wrapped in quotes
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1].strip()
        # Strip accidental "Bearer " prefix (even if repeated) if user pasted header
        while s.lower().startswith("bearer "):
            s = s[7:].strip()
        return s


# Automatically load environment on import
VedaConfig.load_environment()
