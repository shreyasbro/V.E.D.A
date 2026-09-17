"""
V.E.D.A. — Virtual Executive Desktop Assistant
Root Launcher
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def show_fatal_error(msg: str):
    """Displays a native Windows error dialog and logs to startup_crash.log."""
    try:
        log_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "startup_crash.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass

    try:
        import ctypes
        MB_ICONERROR = 0x10
        ctypes.windll.user32.MessageBoxW(0, msg, "V.E.D.A. Startup Error", MB_ICONERROR)
    except Exception:
        print(f"[FATAL STARTUP ERROR]\n{msg}", file=sys.stderr)

def main():
    try:
        from veda.ui import VedaApp
        app = VedaApp()
        app.mainloop()
    except Exception:
        err = traceback.format_exc()
        show_fatal_error(f"V.E.D.A. encountered an error during startup:\n\n{err}")
        sys.exit(1)

if __name__ == "__main__":
    main()
