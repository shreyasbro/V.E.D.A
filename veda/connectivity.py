"""
V.E.D.A. Real Internet Connectivity Monitor
Features:
- Periodic asynchronous connectivity checks every INTERNET_CHECK_INTERVAL_SECONDS (default 60s).
- Lightweight HTTPS HEAD/GET 204 against ultra-reliable endpoints (Google generate_204, Cloudflare 1.1.1.1).
- Does NOT rely on Wi-Fi adapter state, Ethernet status, or Windows network icons.
- Maintains distinct states: ONLINE, OFFLINE, CHECKING, UNKNOWN.
- Listener/Subscriber mechanism: add_listener(callback), remove_listener(callback).
- Thread-safe listener notifications with error isolation (UI listener exceptions never crash monitor).
- Exposes is_internet_available(), get_connection_status(), get_diagnostics().
- Backward-compatible on_status_changed legacy callback and check_now / check_internet_now APIs.
- Clean and safe shutdown via stop().
- Zero UI freeze, short timeout (3.0s), minimal bandwidth (< 1KB).
"""

import time
import urllib.request
import threading
from typing import Optional, Callable, Dict, Any, List

INTERNET_CHECK_INTERVAL_SECONDS = 60.0
CHECK_TIMEOUT_SECONDS = 3.0

PRIMARY_ENDPOINT = "https://www.google.com/generate_204"
FALLBACK_ENDPOINT = "https://1.1.1.1"


class InternetConnectivityMonitor:
    """
    Asynchronous, lightweight background Internet connectivity monitor.
    Thread-safe singleton supporting subscriber listeners and backward-compatible hooks.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(InternetConnectivityMonitor, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, check_interval: float = INTERNET_CHECK_INTERVAL_SECONDS):
        if self._initialized:
            return
        self._initialized = True

        self.check_interval = check_interval
        self.status = "CHECKING"  # Initial state is CHECKING before first real probe
        self.last_successful_check: Optional[float] = None
        self.last_failed_check: Optional[float] = None
        self.last_check_duration: float = 0.0
        self.last_endpoint_used: Optional[str] = None
        self.last_error: Optional[str] = None

        # Thread-safe listener registry
        self._listeners: List[Callable[[bool, Dict[str, Any]], None]] = []
        self._listener_lock = threading.Lock()

        # Legacy backward-compatibility callback: on_status_changed(old_status, new_status)
        self.on_status_changed: Optional[Callable[[str, str], None]] = None

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def add_listener(self, callback: Callable[[bool, Dict[str, Any]], None], notify_current: bool = False):
        """
        Registers a connectivity listener: callback(is_online: bool, diagnostics: Dict[str, Any]).
        If notify_current is True and initial check is done, immediately notifies callback with current state.
        """
        if not callable(callback):
            return
        with self._listener_lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

        if notify_current and self.status in ["ONLINE", "OFFLINE"]:
            try:
                callback(self.status == "ONLINE", self.get_diagnostics())
            except Exception as e:
                print(f"[INTERNET MONITOR] Error notifying new listener: {e}")

    def remove_listener(self, callback: Callable[[bool, Dict[str, Any]], None]):
        """Removes a registered connectivity listener."""
        with self._listener_lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify_listeners(self, is_online: bool, diagnostics: Dict[str, Any]):
        """Notifies all registered listeners safely without letting subscriber errors crash the monitor."""
        with self._listener_lock:
            listeners_snapshot = list(self._listeners)

        for cb in listeners_snapshot:
            try:
                cb(is_online, diagnostics)
            except Exception as e:
                print(f"[INTERNET MONITOR] Listener callback error (isolated): {e}")

    def start(self, run_immediate: bool = True):
        """Starts background monitor thread."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

        if run_immediate:
            # Trigger immediate asynchronous check
            self.check_now(async_mode=True)

    def stop(self):
        """Stops background monitor thread and clears pending check signals."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            try:
                self._thread.join(timeout=1.0)
            except Exception:
                pass
        self._thread = None

    def is_internet_available(self) -> bool:
        """
        Returns True if genuine Internet access is verified.
        If monitor is in initial CHECKING state and has never recorded a failed check,
        returns True to allow initial request resolution without blocking on the first probe.
        """
        if self.status == "ONLINE":
            return True
        if self.status == "CHECKING" and self.last_failed_check is None:
            return True
        return False

    def get_connection_status(self) -> str:
        """Returns ONLINE, OFFLINE, CHECKING, or UNKNOWN."""
        return self.status

    def get_diagnostics(self) -> Dict[str, Any]:
        """Telemetry details for listeners, settings modal, and status badges."""
        return {
            "status": self.status,
            "is_online": self.is_internet_available(),
            "last_successful_check": self.last_successful_check,
            "last_failed_check": self.last_failed_check,
            "last_check_duration": round(self.last_check_duration, 3),
            "latency_ms": round(self.last_check_duration * 1000.0, 1),
            "check_interval": self.check_interval,
            "endpoint": self.last_endpoint_used or PRIMARY_ENDPOINT,
            "error": self.last_error,
            "checked_at": time.time()
        }

    def check_now(self, async_mode: bool = False) -> bool:
        """Triggers an on-demand check."""
        if async_mode:
            threading.Thread(target=self._perform_check, daemon=True).start()
            return self.is_internet_available()
        return self._perform_check()

    def check_internet_now(self) -> tuple[bool, float, str]:
        """Convenience method returning (is_online, latency_seconds, endpoint_used)."""
        is_online = self._perform_check()
        return is_online, self.last_check_duration, self.last_endpoint_used or PRIMARY_ENDPOINT

    def _perform_check(self) -> bool:
        """Performs actual lightweight network probe."""
        old_status = self.status
        t0 = time.time()
        is_online = False
        active_endpoint = None
        last_err = None

        endpoints = [PRIMARY_ENDPOINT, FALLBACK_ENDPOINT]
        for url in endpoints:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VEDA/2.4"}
                )
                with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT_SECONDS) as resp:
                    if resp.status in [200, 204]:
                        is_online = True
                        active_endpoint = url
                        last_err = None
                        break
            except Exception as e:
                last_err = str(e)
                continue

        duration = time.time() - t0
        self.last_check_duration = duration
        self.last_endpoint_used = active_endpoint
        self.last_error = last_err

        if is_online:
            new_status = "ONLINE"
            self.last_successful_check = time.time()
        else:
            new_status = "OFFLINE"
            self.last_failed_check = time.time()

        self.status = new_status
        diagnostics = self.get_diagnostics()

        # If transition occurred (or first check completed from initial CHECKING/UNKNOWN)
        if old_status != new_status:
            print(f"[INTERNET MONITOR] State changed: {old_status} -> {new_status} (Latency: {duration:.3f}s)")
            
            # 1. Notify subscriber listeners
            self._notify_listeners(is_online, diagnostics)

            # 2. Legacy single callback compatibility
            if self.on_status_changed:
                try:
                    self.on_status_changed(old_status, new_status)
                except Exception as e:
                    print(f"[INTERNET MONITOR] on_status_changed error: {e}")

        return is_online

    def _monitor_loop(self):
        """Periodic loop running every check_interval seconds."""
        # Initial check
        try:
            self._perform_check()
        except Exception as e:
            print(f"[INTERNET MONITOR] Initial check error: {e}")

        while not self._stop_event.is_set():
            # Sleep in small slices so shutdown is instant
            slices = max(1, int(self.check_interval * 2))
            for _ in range(slices):
                if self._stop_event.is_set():
                    return
                time.sleep(0.5)

            if not self._stop_event.is_set():
                try:
                    self._perform_check()
                except Exception as e:
                    print(f"[INTERNET MONITOR] Periodic check error: {e}")


# Global singleton instance
internet_monitor = InternetConnectivityMonitor()
