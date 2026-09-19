"""
V.E.D.A. Standalone Process Updater & Rollback Engine
Launched as an isolated external process by V.E.D.A. when an update is applied.
Waits for the main process to exit, creates a rollback backup, applies the update,
and verifies launch before cleaning temporary update files.
Preserves all user profile and settings data in ~/.veda.
"""

import os
import sys
import time
import shutil
import subprocess
import argparse


def log(msg: str):
    print(f"[VEDA-UPDATER] {msg}", flush=True)


def wait_for_process_exit(pid: int, timeout_sec: int = 45) -> bool:
    """Waits for the given process ID to terminate."""
    t0 = time.time()
    log(f"Waiting for main V.E.D.A. process (PID {pid}) to exit...")
    while time.time() - t0 < timeout_sec:
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError, PermissionError):
            log("Main process exited cleanly.")
            return True
        time.sleep(0.5)
    return False


def copy_with_retry(src: str, dst: str, retries: int = 5, delay: float = 1.0):
    """Copies a file with retries in case Windows briefly locks it."""
    for attempt in range(retries):
        try:
            shutil.copy2(src, dst)
            return
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(delay)


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

    # 2. Create Rollback Backup of executable
    if os.path.exists(exe_path):
        try:
            log(f"Creating rollback backup: {backup_path}")
            copy_with_retry(exe_path, backup_path)
        except Exception as e:
            log(f"Failed to create backup: {e}")
            return False

    # 3. Apply New Binary or Directory / Installer Update
    try:
        pkg_lower = package_path.lower()
        if pkg_lower.endswith(".zip"):
            import zipfile
            log(f"Extracting update archive: {package_path} -> {install_dir}")
            with zipfile.ZipFile(package_path, 'r') as zip_ref:
                zip_ref.extractall(install_dir)
        elif "setup" in pkg_lower or "installer" in pkg_lower:
            log(f"Executing Windows installer package: {package_path}")
            # Try running installer silently or waiting for its completion
            inst_proc = subprocess.run([package_path, "/S", f"/D={install_dir}"], capture_output=True, timeout=120)
            if inst_proc.returncode != 0:
                # If silent flag not recognized, try standard execution
                inst_proc2 = subprocess.run([package_path], timeout=180)
                if inst_proc2.returncode != 0:
                    raise RuntimeError(f"Installer exited with code {inst_proc2.returncode}")
        else:
            log(f"Replacing executable: {exe_path}")
            copy_with_retry(package_path, exe_path)
    except Exception as e:
        log(f"Failed to apply update files: {e}. Initiating rollback...")
        _rollback(exe_path, backup_path)
        return False

    # 4. Verify Launch
    log("Verifying updated version launch...")
    try:
        # Run with --verify-launch flag
        verify_proc = subprocess.Popen([exe_path, "--verify-launch"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            poll = verify_proc.wait(timeout=10.0)
            if poll != 0:
                log(f"Verification failed with exit code {poll}. Rolling back...")
                _rollback(exe_path, backup_path)
                return False
        except subprocess.TimeoutExpired:
            log("Verification timed out. Killing process and rolling back...")
            verify_proc.kill()
            _rollback(exe_path, backup_path)
            return False
    except Exception as e:
        log(f"Failed to launch new binary: {e}. Rolling back...")
        _rollback(exe_path, backup_path)
        return False

    # 5. Relaunch V.E.D.A. normally
    log("Update verified! Relaunching V.E.D.A...")
    try:
        subprocess.Popen([exe_path], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0x00000008))
    except Exception as e:
        log(f"Could not relaunch V.E.D.A.: {e}")

    # 6. Cleanup temporary installer files and backup
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
            copy_with_retry(backup_path, exe_path)
            log("Restarting previous version...")
            subprocess.Popen([exe_path], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0x00000008))
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
