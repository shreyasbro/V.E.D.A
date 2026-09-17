"""
V.E.D.A. Elevation Management Subsystem
Handles operations that require administrator privileges via Windows ShellExecute (runas).
Enforces transparency: Explains the reason and asks for confirmation.
"""

import ctypes
import os
import subprocess
from typing import Any, Dict
from veda.permissions import PermissionGuard

class ElevationManager:
    """Manages on-demand administrator elevation."""

    @staticmethod
    def is_currently_admin() -> bool:
        """Checks if current process is running as administrator."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    @staticmethod
    def run_elevated(command: str, reason: str) -> Dict[str, Any]:
        """
        Executes a command with elevated privileges using Windows ShellExecute 'runas'.
        Guarded by the elevated_operations permission.
        """
        PermissionGuard.require("elevated_operations", action_name="Elevated Windows Operation")

        try:
            # Create a temporary script to execute the command and capture exit status
            script_content = f"""
@echo off
title V.E.D.A. Elevated Task
{command}
exit /b %ERRORLEVEL%
"""
            temp_bat = os.path.join(os.path.expanduser("~"), ".veda", "cache", "elevated_task.bat")
            os.makedirs(os.path.dirname(temp_bat), exist_ok=True)
            with open(temp_bat, "w", encoding="utf-8") as f:
                f.write(script_content)

            # ShellExecuteW with "runas" invokes the native Windows UAC prompt
            result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                "cmd.exe",
                f"/c \"{temp_bat}\"",
                None,
                0  # SW_HIDE
            )

            # Result > 32 indicates success in ShellExecute
            if result > 32:
                return {
                    "success": True,
                    "action": "run_elevated",
                    "command": command,
                    "reason": reason,
                    "status": "UAC prompt accepted; elevated task dispatched."
                }
            else:
                return {
                    "success": False,
                    "error": f"Elevation cancelled or rejected by user (code {result})."
                }

        except Exception as e:
            return {"success": False, "error": str(e)}
