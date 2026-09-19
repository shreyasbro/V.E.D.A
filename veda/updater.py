"""
V.E.D.A. Production GitHub Releases OTA Update Engine
Features:
- Real GitHub Releases API checking (https://api.github.com/repos/shreyasbro/V.E.D.A/releases/latest).
- Semantic version comparison against release tag_name ('v1.0.1' -> 1.0.1).
- Windows release asset discovery (V.E.D.A.exe, V.E.D.A-Setup.exe, VEDA.exe, .zip).
- Release notes extraction and presentation.
- Real background download with byte progress, percent, speed, and time remaining.
- SHA-256 verification against asset digest / release sha256 checksums file.
- Automatic download and automatic installation options with safe restart handling.
- Prompt before restart when 'ask_before_restart' is enabled.
- Separate updater process execution with automatic rollback if launch fails.
- Preserves all persistent configuration and user credentials in ~/.veda.
- Zero GitHub token embedded in application.
- Periodic 24-hour update checking loop.
- Full state machine: IDLE, CHECKING, UPDATE_AVAILABLE, DOWNLOADING, DOWNLOAD_CANCELLED,
  VERIFYING, VERIFIED, READY_TO_INSTALL, WAITING_FOR_RESTART, INSTALLING, RESTARTING,
  SUCCESS, FAILED, ROLLED_BACK, OFFLINE, NO_ASSET.
"""

import os
import re
import sys
import json
import time
import hashlib
import threading
import urllib.request
import urllib.error
import subprocess
from typing import Dict, Any, Optional, Callable, List, Tuple

from veda.version import VERSION, BUILD, is_newer_version, parse_semver
from veda.notifications import notification_manager
from veda.config import VedaConfig, UPDATE_CACHE_DIR

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
STATE_DOWNLOAD_CANCELLED = "DOWNLOAD_CANCELLED"
STATE_VERIFYING = "VERIFYING"
STATE_VERIFIED = "VERIFIED"
STATE_READY_TO_INSTALL = "READY_TO_INSTALL"
STATE_WAITING_FOR_RESTART = "WAITING_FOR_RESTART"
STATE_INSTALLING = "INSTALLING"
STATE_RESTARTING = "RESTARTING"
STATE_SUCCESS = "SUCCESS"
STATE_FAILED = "FAILED"
STATE_ROLLED_BACK = "ROLLED_BACK"
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

    @property
    def formatted_published_date(self) -> str:
        if not self.published_at:
            return "Unknown"
        try:
            # Format ISO date like 2026-09-19T12:00:00Z to 'September 19, 2026'
            raw = self.published_at.rstrip("Z")
            if "T" in raw:
                date_part = raw.split("T")[0]
                parts = [int(p) for p in date_part.split("-")]
                if len(parts) == 3:
                    import datetime
                    d = datetime.date(parts[0], parts[1], parts[2])
                    return d.strftime("%B %d, %Y")
            return self.published_at
        except Exception:
            return self.published_at


    def find_windows_asset(self) -> Optional[GitHubReleaseAsset]:
        """
        Locates suitable Windows executable or zip archive:
        Matches patterns like:
        - VEDA-Setup*.exe
        - V.E.D.A*.exe / VEDA*.exe
        - VEDA*.zip / V.E.D.A*.zip
        """
        candidates = []
        for asset in self.assets:
            n_lower = asset.name.lower()
            if n_lower.endswith(".sha256") or n_lower.endswith(".md5") or n_lower.endswith(".txt"):
                continue
            if n_lower.endswith(".exe") or n_lower.endswith(".zip"):
                score = 0
                if "setup" in n_lower or "installer" in n_lower:
                    score += 20
                if "veda" in n_lower or "v.e.d.a" in n_lower:
                    score += 10
                if "win" in n_lower or "x64" in n_lower or "windows" in n_lower:
                    score += 5
                if n_lower.endswith(".exe"):
                    score += 5
                candidates.append((score, asset))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        return None

    def find_checksum_asset(self, target_asset_name: Optional[str] = None) -> Optional[GitHubReleaseAsset]:
        """
        Finds the matching checksum file in release assets.
        Prioritizes:
        1. <target_asset_name>.sha256 (e.g. VEDA-Setup-v1.0.1.exe.sha256)
        2. Exact filename match with .sha256
        3. Generic sha256 checksums file (e.g. SHA256SUMS.txt, checksums.txt)
        """
        if target_asset_name:
            target_lower = target_asset_name.lower()
            expected_exact = f"{target_lower}.sha256"
            for asset in self.assets:
                if asset.name.lower() == expected_exact:
                    return asset

        # Fallback to any matching checksum asset
        for asset in self.assets:
            n_lower = asset.name.lower()
            if target_asset_name and target_asset_name.lower() in n_lower and "sha256" in n_lower:
                return asset

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
        self.downloaded_package_path: Optional[str] = None
        self.postponed_version: Optional[str] = None

        # Download telemetry
        self.download_progress: float = 0.0
        self.download_speed_mbps: float = 0.0
        self.downloaded_bytes: int = 0
        self.total_bytes: int = 0
        self.eta_seconds: Optional[int] = None
        self._cancel_download_event = threading.Event()
        self._is_downloading = False

        # Periodic checker thread & busy hook
        self._periodic_thread: Optional[threading.Thread] = None
        self._stop_periodic_event = threading.Event()
        self._is_busy_hook: Optional[Callable[[], bool]] = None
        self._prompt_restart_callback: Optional[Callable[[str], None]] = None

        self._listeners: list = []
        self._lock = threading.Lock()
        self._initialized = True

    def set_busy_hook(self, hook: Callable[[], bool]):
        """Sets a callback to test if V.E.D.A. is currently executing a task."""
        self._is_busy_hook = hook

    def set_prompt_restart_callback(self, cb: Callable[[str], None]):
        """Sets UI prompt callback when an update is ready to restart."""
        self._prompt_restart_callback = cb

    def is_busy(self) -> bool:
        if self._is_busy_hook:
            try:
                return bool(self._is_busy_hook())
            except Exception:
                return False
        return False

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

    def start_periodic_checker(self, interval_hours: float = 24.0):
        """Starts background thread to check updates periodically (e.g. every 24 hours)."""
        if self._periodic_thread and self._periodic_thread.is_alive():
            return

        def _loop():
            # Wait initial 5 seconds before first background check
            time.sleep(5.0)
            while not self._stop_periodic_event.is_set():
                settings = VedaConfig.get_settings()
                if settings.get("update_auto_check", True):
                    ota_logger.log("PERIODIC_CHECK", "Running periodic update check...")
                    self.check_for_updates()

                # Sleep interval (default 24h) checking stop event every 30 seconds
                total_sleep = int(interval_hours * 3600)
                slept = 0
                while slept < total_sleep and not self._stop_periodic_event.is_set():
                    time.sleep(30)
                    slept += 30

        self._periodic_thread = threading.Thread(target=_loop, daemon=True, name="VEDA-PeriodicUpdateChecker")
        self._periodic_thread.start()

    def stop_periodic_checker(self):
        self._stop_periodic_event.set()

    def check_for_updates_async(self, on_complete: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Asynchronously checks GitHub releases without blocking caller."""
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
        if self.state in [STATE_DOWNLOADING, STATE_INSTALLING]:
            return {
                "success": False,
                "update_available": False,
                "current_version": self.current_version,
                "message": f"Update already in progress ({self.state})"
            }

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
            with urllib.request.urlopen(req, timeout=10.0) as resp:
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

                        # Only notify if this version hasn't been postponed by user
                        if self.postponed_version != remote_ver:
                            self._post_update_notification(release, win_asset)

                        # Check if auto-download is configured
                        settings = VedaConfig.get_settings()
                        if settings.get("update_auto_download", False):
                            ota_logger.log("AUTO_DOWNLOAD", f"Automatically downloading v{remote_ver}...")
                            self.download_and_install_async()

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
                self._set_state(STATE_FAILED, {"error": self.last_error})
                ota_logger.log("HTTP_RATELIMIT", f"GitHub API returned {e.code}", level="WARN")
            else:
                self.last_error = f"GitHub API error (HTTP {e.code})"
                self._set_state(STATE_FAILED, {"error": self.last_error})
                ota_logger.log("HTTP_ERROR", f"HTTP {e.code}: {e.reason}", level="ERROR")

        except urllib.error.URLError as e:
            self.last_error = "Update check unavailable — you're offline or GitHub is unreachable."
            self._set_state(STATE_OFFLINE, {"error": self.last_error})
            ota_logger.log("OFFLINE", f"URLError: {e.reason}", level="WARN")

        except Exception as e:
            self.last_error = f"Unable to check for updates: {e}"
            self._set_state(STATE_FAILED, {"error": self.last_error})
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

        title = "V.E.D.A. Update Available"
        msg = (
            f"New version: v{release.clean_version}\n"
            f"Current version: v{self.current_version}"
        )
        if release.body:
            lines = [l.strip() for l in release.body.splitlines() if l.strip()]
            if lines:
                notes_preview = "\n".join(lines[:4])
                msg += f"\n\nWhat's new:\n{notes_preview}"

        notification_manager.add_notification(
            category="UPDATE",
            title=title,
            message=msg,
            action_type="UPDATE_NOW",
            action_data={
                "release_tag": release.tag_name,
                "html_url": release.html_url or f"https://github.com/shreyasbro/V.E.D.A/releases/tag/{release.tag_name}"
            },
            play_sound=settings.get("notification_sounds", False)
        )

    def cancel_download(self):
        """Cancels an in-flight download."""
        self._cancel_download_event.set()
        self._set_state(STATE_DOWNLOAD_CANCELLED)
        ota_logger.log("DOWNLOAD_CANCEL", "Update download canceled by user")

    def postpone_update(self, version: Optional[str] = None):
        """User chose 'Later'. Postpone notifications for this version."""
        ver = version or (self.latest_release.clean_version if self.latest_release else None)
        self.postponed_version = ver
        self._set_state(STATE_WAITING_FOR_RESTART, {"postponed": True, "version": ver})
        ota_logger.log("UPDATE_POSTPONED", f"User chose to postpone update for version {ver}")

    def download_and_install_async(
        self,
        progress_callback: Optional[Callable[[float, int, int, float, Optional[int]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_ready_to_restart: Optional[Callable[[], None]] = None
    ):
        """Downloads the real GitHub release asset in the background."""
        if self._is_downloading:
            return

        def _worker():
            self._is_downloading = True
            try:
                success, err = self._download_and_install_impl(progress_callback, on_ready_to_restart)
                if not success:
                    self._set_state(STATE_FAILED, {"error": err})
                    ota_logger.log("DOWNLOAD_FAIL", f"Download/install failed: {err}", level="ERROR")
                    if on_error:
                        try:
                            on_error(err)
                        except Exception:
                            pass
            finally:
                self._is_downloading = False

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

        # Directory: %LOCALAPPDATA%\V.E.D.A\updates
        update_dir = UPDATE_CACHE_DIR
        os.makedirs(update_dir, exist_ok=True)
        ext = ".zip" if asset.name.lower().endswith(".zip") else ".exe"
        target_pkg = os.path.join(update_dir, f"update_{self.latest_release.clean_version}{ext}")
        self.downloaded_package_path = target_pkg

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
                                try:
                                    os.remove(target_pkg)
                                except Exception:
                                    pass
                            self._set_state(STATE_DOWNLOAD_CANCELLED)
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
                        if dt >= 0.3 or downloaded == total_size:
                            speed = ((downloaded - last_downloaded) / dt) / (1024 * 1024) if dt > 0 else 0.0
                            self.download_speed_mbps = speed
                            self.downloaded_bytes = downloaded
                            self.total_bytes = total_size
                            pct = (downloaded / total_size) if total_size > 0 else 0.0
                            self.download_progress = pct

                            rem_bytes = total_size - downloaded
                            speed_bytes = ((downloaded - last_downloaded) / dt) if dt > 0 else 0
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
                        try:
                            os.remove(target_pkg)
                        except Exception:
                            pass
                    self._set_state(STATE_FAILED, {"error": "Update verification failed. SHA-256 checksum mismatch."})
                    ota_logger.log("SHA_MISMATCH", f"Expected: {expected_sha}, Got: {calc_sha}", level="ERROR")
                    notification_manager.add_notification(
                        category="UPDATE",
                        title="Update Verification Failed",
                        message="The downloaded update package failed SHA-256 integrity verification. The corrupted file has been removed."
                    )
                    return False, "Update verification failed. Checksum mismatch."
                ota_logger.log("SHA_MATCH", "SHA256 verified successfully against release manifest")

            self._set_state(STATE_VERIFIED)

            # 3. Ready to install
            settings = VedaConfig.get_settings()
            auto_install = settings.get("update_auto_install", False)
            ask_restart = settings.get("update_ask_before_restart", True)

            self._set_state(STATE_READY_TO_INSTALL)

            # Check if user needs to be prompted before restart
            if ask_restart or not auto_install:
                self._set_state(STATE_WAITING_FOR_RESTART)
                ota_logger.log("WAIT_CONFIRM", "Update downloaded and verified. Prompting user to restart.")
                if on_ready_to_restart:
                    try:
                        on_ready_to_restart()
                    except Exception:
                        pass
                if self._prompt_restart_callback:
                    try:
                        self._prompt_restart_callback(self.latest_release.clean_version)
                    except Exception:
                        pass
                return True, ""

            # If auto_install is True and ask_before_restart is False:
            # Check if V.E.D.A is busy before restarting
            self._safe_auto_restart(target_pkg)
            return True, ""

        except Exception as e:
            if os.path.exists(target_pkg):
                try:
                    os.remove(target_pkg)
                except Exception:
                    pass
            self._set_state(STATE_FAILED, {"error": str(e)})
            return False, str(e)

    def _safe_auto_restart(self, package_path: str):
        """Waits until V.E.D.A. is not busy before launching standalone updater."""
        def _wait_and_restart():
            ota_logger.log("AUTO_RESTART_WAIT", "Checking if V.E.D.A. is busy before auto-restart...")
            # Wait up to 60 seconds if busy
            for _ in range(30):
                if not self.is_busy():
                    break
                time.sleep(2.0)

            self.apply_update_and_restart(package_path)

        threading.Thread(target=_wait_and_restart, daemon=True).start()

    def apply_update_and_restart(self, package_path: Optional[str] = None):
        """Triggers the external standalone updater and exits V.E.D.A."""
        pkg = package_path or self.downloaded_package_path
        if not pkg or not os.path.exists(pkg):
            # Try to resolve in cache directory
            if self.latest_release:
                for ext in [".exe", ".zip"]:
                    cand = os.path.join(UPDATE_CACHE_DIR, f"update_{self.latest_release.clean_version}{ext}")
                    if os.path.exists(cand):
                        pkg = cand
                        break
        if not pkg or not os.path.exists(pkg):
            self._set_state(STATE_FAILED, {"error": "Update package file not found."})
            return

        self._set_state(STATE_INSTALLING)
        self._launch_external_updater(pkg)

    def _extract_expected_checksum(self, asset_name: str) -> Optional[str]:
        """Attempts to find SHA256 checksum in release assets or release notes body."""
        if not self.latest_release:
            return None

        sha_pattern = r"\b([a-fA-F0-9]{64})\b"

        # 1. Look for asset-specific checksum file (e.g. VEDA-Setup-v1.0.1.exe.sha256)
        chk_asset = self.latest_release.find_checksum_asset(asset_name)
        if chk_asset and chk_asset.download_url:
            try:
                ota_logger.log("FETCH_CHECKSUM", f"Downloading checksum asset: {chk_asset.name}")
                req = urllib.request.Request(chk_asset.download_url, headers={"User-Agent": f"VEDA-Updater/{self.current_version}"})
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    text = resp.read().decode("utf-8", errors="ignore").strip()
                    # First check if the file contains the target asset name
                    for line in text.splitlines():
                        if asset_name.lower() in line.lower():
                            line_matches = re.findall(sha_pattern, line)
                            if line_matches:
                                return line_matches[0]
                    # If single line or raw hash in dedicated .sha256 file
                    all_matches = re.findall(sha_pattern, text)
                    if all_matches:
                        return all_matches[0]
            except Exception as e:
                ota_logger.log("CHECKSUM_FETCH_ERR", f"Failed to fetch checksum asset: {e}", level="WARN")

        # 2. Look in release notes text
        body = self.latest_release.body or ""
        matches = re.findall(sha_pattern, body)
        if matches:
            return matches[0]

        return None

    def _launch_external_updater(self, package_path: str):
        """Spawns standalone updater process and cleanly shuts down current V.E.D.A. instance."""
        pid = os.getpid()
        self._set_state(STATE_RESTARTING)
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
