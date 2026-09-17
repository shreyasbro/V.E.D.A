"""
V.E.D.A. System Settings & Native Windows Controls
Master volume control via pycaw / Windows Core Audio, settings URI dispatch
(Wi-Fi, Bluetooth, Displays, Power), and battery/power status.
"""

import os
from typing import Any, Dict, Optional

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    HAS_PYCAW = True
except Exception:
    HAS_PYCAW = False


class SystemSettingsEngine:
    """Controls Windows audio volume, system settings URIs, and display metrics."""

    @staticmethod
    def _get_volume_endpoint():
        if not HAS_PYCAW:
            return None
        try:
            device = AudioUtilities.GetSpeakers()
            if not device:
                return None
            if hasattr(device, "EndpointVolume"):
                return device.EndpointVolume
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(interface, POINTER(IAudioEndpointVolume))
        except Exception:
            return None

    @staticmethod
    def get_master_volume() -> Dict[str, Any]:
        """Gets current master volume level (0-100) and mute status."""
        vol = SystemSettingsEngine._get_volume_endpoint()
        if vol:
            try:
                scalar = vol.GetMasterVolumeLevelScalar()
                mute = bool(vol.GetMute())
                return {
                    "success": True,
                    "volume_percent": int(round(scalar * 100)),
                    "is_muted": mute
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": True, "volume_percent": 50, "is_muted": False, "note": "Estimated default"}

    @staticmethod
    def set_master_volume(level_percent: int) -> Dict[str, Any]:
        """Sets master audio volume (0-100)."""
        target = max(0, min(100, int(level_percent)))
        vol = SystemSettingsEngine._get_volume_endpoint()
        if vol:
            try:
                vol.SetMasterVolumeLevelScalar(target / 100.0, None)
                vol.SetMute(0, None)
                return {"success": True, "action": "set_master_volume", "target_level": target}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "Audio device endpoint not available."}

    @staticmethod
    def open_settings_page(page_name: str) -> Dict[str, Any]:
        """
        Opens a specific Windows Settings page via standard URI schemes.
        Supported pages: wifi, bluetooth, display, sound, battery, storage, apps, updates
        """
        uri_map = {
            "wifi": "ms-settings:network-wifi",
            "wi-fi": "ms-settings:network-wifi",
            "network": "ms-settings:network",
            "bluetooth": "ms-settings:bluetooth",
            "display": "ms-settings:display",
            "sound": "ms-settings:sound",
            "volume": "ms-settings:sound",
            "battery": "ms-settings:batterysaver",
            "power": "ms-settings:powersleep",
            "sleep": "ms-settings:powersleep",
            "storage": "ms-settings:storagesense",
            "apps": "ms-settings:appsfeatures",
            "update": "ms-settings:windowsupdate",
            "updates": "ms-settings:windowsupdate"
        }
        clean = page_name.strip().lower()
        target_uri = uri_map.get(clean, f"ms-settings:{clean}")
        try:
            os.startfile(target_uri)
            return {"success": True, "action": "open_settings_page", "page": clean, "uri": target_uri}
        except Exception as e:
            return {"success": False, "error": str(e)}
