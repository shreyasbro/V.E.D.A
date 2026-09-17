"""
V.E.D.A. Controlled Background Process Runner
Executes shell and CLI tasks headlessly without creating visible console windows.
Captures command, stdout, stderr, exit_code, duration, and PID.
"""

import subprocess
import time
from typing import Any, Dict, Optional

class ControlledProcessRunner:
    """
    Controlled background execution layer for Windows.
    Suppresses console window creation using subprocess.CREATE_NO_WINDOW and STARTUPINFO.
    """

    @staticmethod
    def run_command(
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 45,
        shell: bool = True
    ) -> Dict[str, Any]:
        """
        Executes a command headlessly without flashing or opening a CMD/PowerShell window.
        Returns structured execution metrics.
        """
        start_time = time.time()
        # Windows-specific flags to completely hide the window
        creationflags = subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            proc = subprocess.Popen(
                command,
                cwd=cwd,
                shell=shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                startupinfo=startupinfo
            )

            pid = proc.pid
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                duration = round(time.time() - start_time, 3)
                exit_code = proc.returncode

                return {
                    "success": exit_code == 0,
                    "command": command,
                    "exit_code": exit_code,
                    "stdout": stdout.strip(),
                    "stderr": stderr.strip(),
                    "duration_seconds": duration,
                    "process_id": pid
                }

            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                duration = round(time.time() - start_time, 3)
                return {
                    "success": False,
                    "command": command,
                    "exit_code": -1,
                    "stdout": stdout.strip(),
                    "stderr": f"Process timed out after {timeout} seconds.",
                    "duration_seconds": duration,
                    "process_id": pid
                }

        except Exception as e:
            duration = round(time.time() - start_time, 3)
            return {
                "success": False,
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "duration_seconds": duration,
                "process_id": None
            }
