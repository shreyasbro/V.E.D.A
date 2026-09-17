"""
V.E.D.A. In-App Notification Engine & Storage
Provides centralized notification management, persistence, unread tracking,
and event dispatching for:
- OTA updates
- AI provider errors / test results
- System notifications & warnings
- Permissions alerts
"""

import os
import time
import json
import uuid
import threading
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Callable

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".veda")
NOTIFICATIONS_FILE = os.path.join(CONFIG_DIR, "notifications.json")


@dataclass
class Notification:
    id: str
    category: str       # 'UPDATE', 'AI_PROVIDER', 'SYSTEM', 'PERMISSION', 'ERROR'
    title: str
    message: str
    timestamp: float
    read: bool = False
    dismissed: bool = False
    action_type: Optional[str] = None  # e.g., 'UPDATE_NOW', 'OPEN_SETTINGS', 'VIEW_DETAILS'
    action_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Notification":
        valid_keys = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class NotificationManager:
    """Singleton manager for V.E.D.A. notifications."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(NotificationManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.notifications: List[Notification] = []
        self._listeners: List[Callable[[str, Any], None]] = []
        self._lock = threading.Lock()
        self._load_notifications()
        self._initialized = True

    def _ensure_dir(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)

    def _load_notifications(self):
        self._ensure_dir()
        if not os.path.exists(NOTIFICATIONS_FILE):
            self.notifications = []
            return
        try:
            with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data.get("notifications", [])
                self.notifications = [Notification.from_dict(item) for item in items if not item.get("dismissed", False)]
        except Exception:
            self.notifications = []

    def _save_notifications(self):
        self._ensure_dir()
        try:
            with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
                payload = {
                    "version": 1,
                    "updated_at": time.time(),
                    "notifications": [n.to_dict() for n in self.notifications[-150:]]
                }
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def subscribe(self, callback: Callable[[str, Any], None]):
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[str, Any], None]):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _emit(self, event_type: str, data: Any = None):
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(event_type, data)
            except Exception:
                pass

    def add_notification(
        self,
        category: str,
        title: str,
        message: str,
        action_type: Optional[str] = None,
        action_data: Optional[Dict[str, Any]] = None,
        play_sound: bool = False
    ) -> Notification:
        """Adds a notification and prevents repeating duplicate update notices."""
        with self._lock:
            # Check for existing pending notification with the exact same category and title
            for existing in self.notifications:
                if not existing.dismissed and existing.category == category and existing.title == title:
                    # Update timestamp and message instead of duplicating
                    existing.message = message
                    existing.timestamp = time.time()
                    existing.read = False
                    if action_type:
                        existing.action_type = action_type
                    if action_data:
                        existing.action_data = action_data
                    self._save_notifications()
                    self._emit("UPDATED", existing)
                    return existing

            n = Notification(
                id=str(uuid.uuid4())[:8],
                category=category.upper(),
                title=title,
                message=message,
                timestamp=time.time(),
                read=False,
                dismissed=False,
                action_type=action_type,
                action_data=action_data
            )
            self.notifications.insert(0, n)
            self._save_notifications()

        if play_sound:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

        self._emit("ADDED", n)
        return n

    def get_notifications(self, include_read: bool = True) -> List[Notification]:
        with self._lock:
            if include_read:
                return [n for n in self.notifications if not n.dismissed]
            return [n for n in self.notifications if not n.dismissed and not n.read]

    def get_unread_count(self) -> int:
        with self._lock:
            return sum(1 for n in self.notifications if not n.dismissed and not n.read)

    def mark_as_read(self, notification_id: str):
        with self._lock:
            for n in self.notifications:
                if n.id == notification_id:
                    n.read = True
                    break
            self._save_notifications()
        self._emit("READ", notification_id)

    def mark_all_read(self):
        with self._lock:
            for n in self.notifications:
                n.read = True
            self._save_notifications()
        self._emit("ALL_READ", None)

    def dismiss(self, notification_id: str):
        with self._lock:
            for n in self.notifications:
                if n.id == notification_id:
                    n.dismissed = True
                    break
            self.notifications = [n for n in self.notifications if not n.dismissed]
            self._save_notifications()
        self._emit("DISMISSED", notification_id)

    def clear_all(self):
        with self._lock:
            self.notifications.clear()
            self._save_notifications()
        self._emit("CLEARED", None)


notification_manager = NotificationManager()
