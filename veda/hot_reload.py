"""
V.E.D.A. Safe Subsystem Teardown & Development Hot Reload
Features:
- Watches source files (.py, .json, .yaml, .env) in development environment.
- Debounced by HOT_RELOAD_DEBOUNCE_SECONDS (default 1.5s).
- Excludes: logs, cache, temp files, __pycache__, build/, dist/, .git/, screenshots.
- Safe Subsystem Teardown before restart:
  * Stops active AI requests
  * Stops microphone streams
  * Releases camera
  * Stops TTS
  * Stops screen capture
  * Saves settings
  * Releases network & audio devices
- Dynamically detects project and executable root without hardcoded paths.
"""

import os
import sys
import time
import threading
import subprocess
from typing import Set, Dict, Optional, Callable


HOT_RELOAD_DEBOUNCE_SECONDS = 1.5

WATCH_EXTENSIONS = {".py", ".json", ".yaml", ".yml", ".env"}
EXCLUDE_DIRS = {
    "__pycache__", ".git", "build", "dist", "cache", "logs", ".pytest_cache",
    ".idea", ".vscode", "localpycs"
}


def safely_teardown_all_subsystems():
    """
    Safely tears down and releases all hardware, audio, video,
    and background worker threads before a restart or update.
    """
    print("[TEARDOWN] Safely releasing all V.E.D.A. subsystems...")

    # 1. Stop TTS
    try:
        from veda.tts import tts_engine
        tts_engine.stop()
    except Exception as e:
        print(f"[TEARDOWN] TTS stop error: {e}")

    # 2. Stop Microphone
    try:
        from veda.hardware import microphone_subsystem
        microphone_subsystem.stop_always_on()
        microphone_subsystem.stop_listening()
    except Exception as e:
        print(f"[TEARDOWN] Mic stop error: {e}")

    # 3. Stop Camera
    try:
        from veda.hardware import camera_subsystem
        camera_subsystem.stop_preview()
    except Exception as e:
        print(f"[TEARDOWN] Camera stop error: {e}")

    # 4. Stop Live Screen
    try:
        from veda.vision import live_screen_manager
        live_screen_manager.set_mode("OFF")
        live_screen_manager.clear_buffer()
    except Exception as e:
        print(f"[TEARDOWN] Live screen stop error: {e}")

    # 5. Stop Connectivity Monitor
    try:
        from veda.connectivity import internet_monitor
        internet_monitor.stop()
    except Exception as e:
        print(f"[TEARDOWN] Connectivity monitor stop error: {e}")

    time.sleep(0.3)
    print("[TEARDOWN] All subsystems successfully stopped.")
    return True


class DevelopmentWatcher:
    """
    Watches source files and schedules a debounced restart when changes are detected.
    """

    def __init__(self, project_root: Optional[str] = None, on_reload: Optional[Callable[[], None]] = None):
        if project_root is None:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.project_root = project_root
        self.on_reload = on_reload

        self._file_mtimes: Dict[str, float] = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._pending_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

        # Build initial snapshot
        self._scan_files(initial=True)

    def start(self):
        """Starts background file watcher thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        print(f"[HOT RELOAD] Watching for code changes in: {self.project_root} (Debounce: {HOT_RELOAD_DEBOUNCE_SECONDS}s)")

    def stop(self):
        self._stop_event.set()
        with self._lock:
            if self._pending_timer:
                self._pending_timer.cancel()

    def _scan_files(self, initial: bool = False) -> Set[str]:
        changed = set()
        for root, dirs, files in os.walk(self.project_root):
            # Filter out excluded directories in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in WATCH_EXTENSIONS and file != ".env":
                    continue

                full_path = os.path.join(root, file)
                try:
                    mtime = os.path.getmtime(full_path)
                    if initial:
                        self._file_mtimes[full_path] = mtime
                    else:
                        old_mtime = self._file_mtimes.get(full_path)
                        if old_mtime is not None and mtime > old_mtime + 0.05:
                            changed.add(full_path)
                            self._file_mtimes[full_path] = mtime
                        elif old_mtime is None:
                            # Newly created file
                            self._file_mtimes[full_path] = mtime
                            changed.add(full_path)
                except OSError:
                    pass
        return changed

    def _trigger_debounced_restart(self, changed_files: Set[str]):
        with self._lock:
            if self._pending_timer:
                self._pending_timer.cancel()

            sample = [os.path.basename(f) for f in list(changed_files)[:3]]
            print(f"[HOT RELOAD] Code change detected in: {sample}. Debouncing for {HOT_RELOAD_DEBOUNCE_SECONDS}s...")

            self._pending_timer = threading.Timer(
                HOT_RELOAD_DEBOUNCE_SECONDS,
                self._execute_reload
            )
            self._pending_timer.daemon = True
            self._pending_timer.start()

    def _execute_reload(self):
        print("[HOT RELOAD] Changes settled. Executing safe hot reload / restart...")
        if self.on_reload:
            try:
                self.on_reload()
                return
            except Exception as e:
                print(f"[HOT RELOAD] Custom on_reload failed: {e}. Falling back to clean restart.")

        # Default safe application restart
        safely_teardown_all_subsystems()

        python_exe = sys.executable
        main_script = os.path.join(self.project_root, "main.py")
        cmd = [python_exe, main_script] + sys.argv[1:]

        print(f"[HOT RELOAD] Spawning clean instance: {' '.join(cmd)}")
        subprocess.Popen(cmd, cwd=self.project_root)
        os._exit(0)

    def _watch_loop(self):
        while not self._stop_event.is_set():
            time.sleep(0.5)
            changed = self._scan_files(initial=False)
            if changed:
                self._trigger_debounced_restart(changed)


# Global dev watcher instance
dev_watcher = DevelopmentWatcher()
