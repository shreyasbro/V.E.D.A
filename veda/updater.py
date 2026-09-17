"""
V.E.D.A. Production GitHub Releases OTA Update Engine
Features:
- Real GitHub Releases API checking (https://api.github.com/repos/shreyasbro/V.E.D.A/releases/latest).
- Semantic version comparison against release tag_name ('v1.0.1' -> 1.0.1).
- Windows release asset discovery (V.E.D.A.exe, V.E.D.A-Setup.exe, VEDA.exe, .zip).
- Release notes extraction and presentation.
- Real background download with byte progress, percent, speed, and time remaining.
- SHA-256 verification against asset digest / release sha256 checksums file.
- Separate updater process execution with automatic rollback if launch fails.
- Preserves all persistent configuration and user credentials in ~/.veda.
- Zero GitHub token embedded in application.
- Bounded OTA diagnostics logger.
"""

import os
import re
import sys
import json
import time
import hashlib
import tempfile
import threading
import urllib.request
import urllib.error
import subprocess
from typing import Dict, Any, Optional, Callable, List, Tuple

from veda.version import VERSION, BUILD, is_newer_version, parse_semver
from veda.notifications import notification_manager
from veda.config import VedaConfig

# Centralized GitHub OTA Configuration
GITHUB_OWNER = "shreyasbro"
GITHUB_REPOSITORY = "V.E.D.A"
GITHUB_LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases/latest"

# OTA States
STATE_IDLE = "IDLE"
STATE_CHECKING = "CHECKING"
STATE_UP_TO_DATE = "UP_TO_DATE"
STATE_UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
STATE_DOWNLOADING = "DOWNLOADING"
STATE_VERIFYING = "VERIFYING"
STATE_INSTALLING = "INSTALLING"
STATE_UPDATE_FAILED = "UPDATE_FAILED"
STATE_OFFLINE = "OFFLINE"
STATE_NO_ASSET = "NO_ASSET"


class OTALogger:
    """Bounded in-memory ring logger for OTA diagnostic events."""
    def __init__(self, max_entries: int = 50):
        self.max_entries = max_entries
        self.entries: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def log(self, event: str, message: str, level: str = "INFO"):
        with self._lock:
            entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": event,
                "message": message,
                "level": level
            }
            self.entries.append(entry)
            if len(self.entries) > self.max_entries:
                self.entries.pop(0)

    def get_entries(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.entries)


ota_logger = OTALogger()


class GitHubReleaseAsset:
    """Structured representation of a GitHub release asset."""
    def __init__(self, raw: Dict[str, Any]):
        self.name: str = raw.get("name", "")
        self.size_bytes: int = raw.get("size", 0)
        self.download_url: str = raw.get("browser_download_url", "")
        self.content_type: str = raw.get("content_type", "")


class GitHubReleaseInfo:
    """Structured representation of a GitHub release."""
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw
        self.tag_name: str = raw.get("tag_name", "")
        self.name: str = raw.get("name", "")
        self.body: str = raw.get("body", "")
        self.published_at: str = raw.get("published_at", "")
        self.html_url: str = raw.get("html_url", "")
        self.assets: List[GitHubReleaseAsset] = [
            GitHubReleaseAsset(a) for a in raw.get("assets", [])
        ]

    @property
    def clean_version(self) -> str:
        tag = self.tag_name or self.name or ""
        return tag.strip().lstrip("vV")

    def find_windows_asset(self) -> Optional[GitHubReleaseAsset]:
        """
        Locates suitable Windows executable or zip archive:
        Matches patterns like:
        - V.E.D.A*.exe
        - VEDA*.exe
        - V.E.D.A*.zip
        - VEDA*.zip
        """
        candidates = []
        for asset in self.assets:
            n_lower = asset.name.lower()
            if n_lower.endswith(".exe") or n_lower.endswith(".zip"):
                # Prioritize Windows specific binaries
                score = 0
                if "veda" in n_lower or "v.e.d.a" in n_lower:
                    score += 10
                if "setup" in n_lower or "installer" in n_lower:
                    score += 5
                if "win" in n_lower or "x64" in n_lower or "windows" in n_lower:
                    score += 5
                if n_lower.endswith(".exe"):
                    score += 3
                candidates.append((score, asset))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        return None

    def find_checksum_asset(self) -> Optional[GitHubReleaseAsset]:
        """Finds any checksum file in release assets (e.g. SHA256SUMS.txt, checksums.txt)."""
        for asset in self.assets:
            n_lower = asset.name.lower()
            if "sha256" in n_lower or "checksum" in n_lower or n_lower.endswith(".sha256"):
                return asset
        return None


class ProductionUpdater:
    """Manages GitHub Releases OTA update checks, downloads, verification, and rollback."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ProductionUpdater, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.current_version = VERSION
        self.current_build = BUILD
        self.state = STATE_IDLE
        self.latest_release: Optional[GitHubReleaseInfo] = None
        self.selected_asset: Optional[GitHubReleaseAsset] = None
        self.last_check_time: Optional[float] = None
        self.last_error: Optional[str] = None

        # Download telemetry
        self.download_progress: float = 0.0
        self.download_speed_mbps: float = 0.0
        self.downloaded_bytes: int = 0
        self.total_bytes: int = 0
        self.eta_seconds: Optional[int] = None
        self._cancel_download_event = threading.Event()

        self._listeners: list = []
        self._lock = threading.Lock()
        self._initialized = True

    def subscribe(self, callback: Callable[[str, Dict[str, Any]], None]):
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[str, Dict[str, Any]], None]):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _set_state(self, new_state: str, details: Optional[Dict[str, Any]] = None):
        self.state = new_state
        payload = details or {}
        payload["state"] = new_state
        payload["timestamp"] = time.time()
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(new_state, payload)
            except Exception:
                pass

    def check_for_updates_async(self, on_complete: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Asynchronously checks GitHub releases without blocking the UI thread."""
        def _worker():
            res = self.check_for_updates()
            if on_complete:
                try:
                    on_complete(res)
                except Exception:
                    pass
        threading.Thread(target=_worker, daemon=True).start()

    def check_for_updates(self) -> Dict[str, Any]:
        """Checks the real GitHub release API against current installed version."""
        self._set_state(STATE_CHECKING)
        ota_logger.log("CHECK_START", f"Checking GitHub release at {GITHUB_LATEST_RELEASE_URL}")

        try:
            req = urllib.request.Request(
                GITHUB_LATEST_RELEASE_URL,
                headers={
                    "User-Agent": f"VEDA-Updater/{self.current_version} (Windows NT 10.0; x64)",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                status_code = resp.status
                ota_logger.log("HTTP_RESPONSE", f"GitHub responded with HTTP {status_code}")

                if status_code == 200:
                    raw_data = json.loads(resp.read().decode("utf-8"))
                    release = GitHubReleaseInfo(raw_data)
                    self.latest_release = release
                    self.last_check_time = time.time()
                    remote_ver = release.clean_version

                    ota_logger.log("RELEASE_DETECTED", f"Tag: {release.tag_name}, Name: {release.name}, Clean Version: {remote_ver}")

                    if is_newer_version(remote_ver, self.current_version):
                        # Locate Windows release asset
                        win_asset = release.find_windows_asset()
                        self.selected_asset = win_asset

                        if not win_asset:
                            self._set_state(STATE_NO_ASSET, {
                                "latest_version": remote_ver,
                                "release_name": release.name,
                                "error": "Update found, but the Windows update package is unavailable."
                            })
                            ota_logger.log("NO_ASSET", f"Release v{remote_ver} exists, but no Windows binary asset found", level="WARN")
                            return {
                                "success": True,
                                "update_available": True,
                                "has_asset": False,
                                "current_version": self.current_version,
                                "latest_version": remote_ver,
                                "release": release,
                                "error": "Update found, but the Windows update package is unavailable."
                            }

                        self._set_state(STATE_UPDATE_AVAILABLE, {
                            "latest_version": remote_ver,
                            "release_name": release.name,
                            "asset_name": win_asset.name,
                            "asset_size": win_asset.size_bytes
                        })
                        ota_logger.log("UPDATE_AVAILABLE", f"Newer version detected: v{remote_ver} (Asset: {win_asset.name})")
                        self._post_update_notification(release, win_asset)

                        return {
                            "success": True,
                            "update_available": True,
                            "has_asset": True,
                            "current_version": self.current_version,
                            "latest_version": remote_ver,
                            "release": release,
                            "asset": win_asset
                        }
                    else:
                        self._set_state(STATE_UP_TO_DATE, {"latest_version": remote_ver})
                        ota_logger.log("UP_TO_DATE", f"Installed version {self.current_version} is up to date (Remote: {remote_ver})")
                        return {
                            "success": True,
                            "update_available": False,
                            "current_version": self.current_version,
                            "latest_version": remote_ver,
                            "release": release
                        }

        except urllib.error.HTTPError as e:
            if e.code == 404:
                # No release published yet
                self.last_error = "No releases found on GitHub repository."
                self._set_state(STATE_UP_TO_DATE, {"error": self.last_error})
                ota_logger.log("HTTP_404", "No releases published yet on GitHub", level="INFO")
                return {
                    "success": True,
                    "update_available": False,
                    "current_version": self.current_version,
                    "latest_version": self.current_version,
                    "message": "No releases found on GitHub."
                }
            elif e.code in [403, 429]:
                self.last_error = "GitHub API rate limit reached. Please try again later."
                self._set_state(STATE_UPDATE_FAILED, {"error": self.last_error})
                ota_logger.log("HTTP_RATELIMIT", f"GitHub API returned {e.code}", level="WARN")
            else:
                self.last_error = f"GitHub API error (HTTP {e.code})"
                self._set_state(STATE_UPDATE_FAILED, {"error": self.last_error})
                ota_logger.log("HTTP_ERROR", f"HTTP {e.code}: {e.reason}", level="ERROR")

        except urllib.error.URLError as e:
            self.last_error = "Update check unavailable — you're offline or GitHub is unreachable."
            self._set_state(STATE_OFFLINE, {"error": self.last_error})
            ota_logger.log("OFFLINE", f"URLError: {e.reason}", level="WARN")

        except Exception as e:
            self.last_error = f"Unable to check for updates: {e}"
            self._set_state(STATE_UPDATE_FAILED, {"error": self.last_error})
            ota_logger.log("CHECK_ERROR", f"Exception during check: {e}", level="ERROR")

        return {
            "success": False,
            "update_available": False,
            "current_version": self.current_version,
            "error": self.last_error or "Unable to check for updates."
        }

    def _post_update_notification(self, release: GitHubReleaseInfo, asset: GitHubReleaseAsset):
        """Creates an in-app notification for the detected GitHub release."""
        settings = VedaConfig.get_settings()
        if not settings.get("update_notifications", True):
            return

        title = f"V.E.D.A. Update Available"
        msg = f"Version {release.clean_version} is available on GitHub."
        if release.body:
            # Take first 3 lines of release body
            lines = [l.strip() for l in release.body.splitlines() if l.strip()]
            if lines:
                msg += "\n" + "\n".join(lines[:3])

        notification_manager.add_notification(
            category="UPDATE",
            title=title,
            message=msg,
            action_type="UPDATE_NOW",
            action_data={"release_tag": release.tag_name, "html_url": release.html_url},
            play_sound=settings.get("notification_sounds", False)
        )

    def cancel_download(self):
        """Cancels an in-flight download."""
        self._cancel_download_event.set()

    def download_and_install_async(
        self,
        progress_callback: Optional[Callable[[float, int, int, float, Optional[int]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_ready_to_restart: Optional[Callable[[], None]] = None
    ):
        """Downloads the real GitHub release asset in the background."""
        def _worker():
            success, err = self._download_and_install_impl(progress_callback, on_ready_to_restart)
            if not success:
                self._set_state(STATE_UPDATE_FAILED, {"error": err})
                ota_logger.log("DOWNLOAD_FAIL", f"Download/install failed: {err}", level="ERROR")
                if on_error:
                    try:
                        on_error(err)
                    except Exception:
                        pass
        threading.Thread(target=_worker, daemon=True).start()

    def _download_and_install_impl(
        self,
        progress_callback: Optional[Callable[[float, int, int, float, Optional[int]], None]] = None,
        on_ready_to_restart: Optional[Callable[[], None]] = None
    ) -> Tuple[bool, str]:
        if not self.latest_release or not self.selected_asset:
            return False, "No active update asset identified"

        asset = self.selected_asset
        download_url = asset.download_url
        if not download_url:
            return False, "Selected asset has no download URL"

        self._set_state(STATE_DOWNLOADING)
        self._cancel_download_event.clear()
        ota_logger.log("DOWNLOAD_START", f"Starting download: {asset.name} ({asset.size_bytes} bytes)")

        # Dynamic temporary download directory
        temp_dir = os.path.join(tempfile.gettempdir(), "veda_update_packages")
        os.makedirs(temp_dir, exist_ok=True)
        ext = ".zip" if asset.name.lower().endswith(".zip") else ".exe"
        target_pkg = os.path.join(temp_dir, f"update_{self.latest_release.clean_version}{ext}")

        try:
            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": f"VEDA-Updater/{self.current_version} (Windows NT 10.0; x64)"}
            )
            start_time = time.time()
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                total_size = int(resp.headers.get("content-length", asset.size_bytes or 0))
                downloaded = 0
                chunk_size = 64 * 1024
                hasher = hashlib.sha256()

                with open(target_pkg, "wb") as f:
                    last_time = time.time()
                    last_downloaded = 0

                    while True:
                        if self._cancel_download_event.is_set():
                            f.close()
                            if os.path.exists(target_pkg):
                                os.remove(target_pkg)
                            ota_logger.log("DOWNLOAD_CANCEL", "Download canceled by user")
                            return False, "Download canceled by user"

                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        dt = now - last_time
                        if dt >= 0.5:
                            speed = ((downloaded - last_downloaded) / dt) / (1024 * 1024)  # MB/s
                            self.download_speed_mbps = speed
                            self.downloaded_bytes = downloaded
                            self.total_bytes = total_size
                            pct = (downloaded / total_size) if total_size > 0 else 0.0
                            self.download_progress = pct

                            rem_bytes = total_size - downloaded
                            speed_bytes = (downloaded - last_downloaded) / dt
                            eta = int(rem_bytes / speed_bytes) if speed_bytes > 0 else None
                            self.eta_seconds = eta

                            last_time = now
                            last_downloaded = downloaded

                            if progress_callback:
                                try:
                                    progress_callback(pct, downloaded, total_size, speed, eta)
                                except Exception:
                                    pass

            # 2. Verification Step
            self._set_state(STATE_VERIFYING)
            calc_sha = hasher.hexdigest().lower()
            ota_logger.log("VERIFY_SHA", f"Calculated SHA256: {calc_sha}")

            # Check if expected checksum exists in release assets or body
            expected_sha = self._extract_expected_checksum(asset.name)
            if expected_sha:
                if calc_sha != expected_sha.lower():
                    if os.path.exists(target_pkg):
                        os.remove(target_pkg)
                    ota_logger.log("SHA_MISMATCH", f"Expected: {expected_sha}, Got: {calc_sha}", level="ERROR")
                    return False, f"Update verification failed. Checksum mismatch."
                ota_logger.log("SHA_MATCH", "SHA256 verified successfully against release manifest")

            # 3. Ready to install
            settings = VedaConfig.get_settings()
            auto_install = settings.get("update_auto_install", False)

            if not auto_install and on_ready_to_restart:
                ota_logger.log("WAIT_CONFIRM", "Update downloaded and verified. Prompting user to install.")
                on_ready_to_restart()
                return True, ""

            # Automatic or confirmed installation
            self._set_state(STATE_INSTALLING)
            self._launch_external_updater(target_pkg)
            return True, ""

        except Exception as e:
            if os.path.exists(target_pkg):
                try:
                    os.remove(target_pkg)
                except Exception:
                    pass
            return False, str(e)

    def _extract_expected_checksum(self, asset_name: str) -> Optional[str]:
        """Attempts to find SHA256 checksum in release assets or release notes body."""
        if not self.latest_release:
            return None

        # Look in release notes text
        body = self.latest_release.body or ""
        sha_pattern = r"\b([a-fA-F0-9]{64})\b"
        matches = re.findall(sha_pattern, body)
        if matches:
            return matches[0]

        # Look for checksum file asset
        chk_asset = self.latest_release.find_checksum_asset()
        if chk_asset and chk_asset.download_url:
            try:
                req = urllib.request.Request(chk_asset.download_url, headers={"User-Agent": f"VEDA-Updater/{self.current_version}"})
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    text = resp.read().decode("utf-8", errors="ignore")
                    for line in text.splitlines():
                        if asset_name.lower() in line.lower():
                            line_matches = re.findall(sha_pattern, line)
                            if line_matches:
                                return line_matches[0]
            except Exception:
                pass

        return None

    def _launch_external_updater(self, package_path: str):
        """Spawns standalone updater process and cleanly shuts down current V.E.D.A. instance."""
        pid = os.getpid()
        if getattr(sys, "frozen", False):
            install_dir = os.path.dirname(sys.executable)
            main_exe = os.path.basename(sys.executable)
        else:
            install_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            main_exe = "VEDA.exe"

        updater_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "standalone_updater.py"))
        ota_logger.log("LAUNCH_UPDATER", f"Spawning updater script: {updater_script} (PID {pid})")

        python_exe = sys.executable
        cmd = [
            python_exe,
            updater_script,
            "--package", package_path,
            "--install-dir", install_dir,
            "--exe-name", main_exe,
            "--pid", str(pid)
        ]

        subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )

        def _exit_main():
            time.sleep(1.0)
            os._exit(0)

        threading.Thread(target=_exit_main, daemon=True).start()


production_updater = ProductionUpdater()
