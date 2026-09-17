"""
V.E.D.A. Standalone Process Updater & Rollback Engine
Launched as an isolated external process by V.E.D.A. when an update is applied.
Waits for the main process to exit, creates a rollback backup, applies the update,
and verifies launch before cleaning temporary update files.
"""

import os
import sys
import time
import shutil
import subprocess
import argparse


def log(msg: str):
    print(f"[VEDA-UPDATER] {msg}", flush=True)


def wait_for_process_exit(pid: int, timeout_sec: int = 30) -> bool:
    """Waits for the given process ID to terminate."""
    t0 = time.time()
    log(f"Waiting for main V.E.D.A. process (PID {pid}) to exit...")
    while time.time() - t0 < timeout_sec:
        try:
            # Using Windows tasklist / ctypes or os.kill(pid, 0)
            os.kill(pid, 0)
        except (OSError, ProcessLookupError, PermissionError):
            log("Main process exited cleanly.")
            return True
        time.sleep(0.5)
    return False


def apply_update_and_verify(
    package_path: str,
    install_dir: str,
    main_exe_name: str,
    pid: int
) -> bool:
    # 1. Wait for main process to terminate
    if pid > 0:
        if not wait_for_process_exit(pid):
            log(f"Process {pid} did not exit within timeout. Aborting update.")
            return False

    exe_path = os.path.join(install_dir, main_exe_name)
    backup_path = exe_path + ".bak"

    # 2. Create Rollback Backup
    if os.path.exists(exe_path):
        try:
            log(f"Creating rollback backup: {backup_path}")
            shutil.copy2(exe_path, backup_path)
        except Exception as e:
            log(f"Failed to create backup: {e}")
            return False

    # 3. Apply New Binary or Directory Update
    try:
        if package_path.endswith(".zip"):
            import zipfile
            log(f"Extracting update archive: {package_path} -> {install_dir}")
            with zipfile.ZipFile(package_path, 'r') as zip_ref:
                zip_ref.extractall(install_dir)
        else:
            log(f"Replacing executable: {exe_path}")
            shutil.copy2(package_path, exe_path)
    except Exception as e:
        log(f"Failed to apply update files: {e}. Initiating rollback...")
        _rollback(exe_path, backup_path)
        return False

    # 4. Verify Launch
    log("Verifying updated version launch...")
    try:
        verify_proc = subprocess.Popen([exe_path, "--verify-launch"])
        time.sleep(2.0)
        poll = verify_proc.poll()
        if poll is not None and poll != 0:
            log(f"Verification failed with exit code {poll}. Rolling back...")
            _rollback(exe_path, backup_path)
            return False
    except Exception as e:
        log(f"Failed to launch new binary: {e}. Rolling back...")
        _rollback(exe_path, backup_path)
        return False

    # 5. Relaunch V.E.D.A. normally
    log("Update verified! Relaunching V.E.D.A...")
    try:
        subprocess.Popen([exe_path])
    except Exception as e:
        log(f"Could not relaunch V.E.D.A.: {e}")

    # 6. Cleanup temporary installer files
    try:
        if os.path.exists(package_path):
            os.remove(package_path)
        if os.path.exists(backup_path):
            os.remove(backup_path)
    except Exception:
        pass

    return True


def _rollback(exe_path: str, backup_path: str):
    if os.path.exists(backup_path):
        try:
            log("Restoring previous executable from backup...")
            shutil.copy2(backup_path, exe_path)
            log("Restarting previous version...")
            subprocess.Popen([exe_path])
        except Exception as e:
            log(f"Rollback failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="V.E.D.A. Standalone Updater")
    parser.add_argument("--package", required=True, help="Path to downloaded update file (.exe or .zip)")
    parser.add_argument("--install-dir", required=True, help="Target installation directory")
    parser.add_argument("--exe-name", default="VEDA.exe", help="Main executable file name")
    parser.add_argument("--pid", type=int, default=0, help="Main process PID to wait for")
    args = parser.parse_args()

    success = apply_update_and_verify(
        package_path=args.package,
        install_dir=args.install_dir,
        main_exe_name=args.exe_name,
        pid=args.pid
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
