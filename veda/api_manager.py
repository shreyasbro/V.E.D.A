"""
V.E.D.A. Universal AI Provider Manager & Real Network Diagnostics Engine
Allows users to configure, test, enable/disable, and prioritize their own AI providers.
Zero bundled or preconfigured developer API keys.
"""

import os
import sys
import json
import time
import uuid
import threading
import requests
from dataclasses import dataclass, asdict, field
from typing import Callable, Any, Dict, List, Optional, Tuple

from veda.security import encrypt_secret, decrypt_secret, mask_key

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".veda")
AI_PROVIDERS_FILE = os.path.join(CONFIG_DIR, "ai_providers.json")

# Event constants
EVENT_PROVIDER_CONFIG_CHANGED = "PROVIDER_CONFIG_CHANGED"
EVENT_PROVIDER_TEST_STARTED = "PROVIDER_TEST_STARTED"
EVENT_PROVIDER_TEST_SUCCESS = "PROVIDER_TEST_SUCCESS"
EVENT_PROVIDER_TEST_FAILED = "PROVIDER_TEST_FAILED"
EVENT_PROVIDER_PRIMARY_CHANGED = "PROVIDER_PRIMARY_CHANGED"
EVENT_PROVIDER_REMOVED = "PROVIDER_REMOVED"
EVENT_PROVIDER_ADDED = "PROVIDER_ADDED"

# Presets available to help user quickly fill endpoints (without any pre-set keys!)
PROVIDER_PRESETS = {
    "gemini": {
        "name": "Google Gemini",
        "protocol": "gemini",
        "base_url": "https://generativelanguage.googleapis.com",
        "default_model": "gemini-2.5-flash",
    },
    "groq": {
        "name": "Groq",
        "protocol": "openai_compatible",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "name": "OpenRouter",
        "protocol": "openai_compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "openai": {
        "name": "OpenAI",
        "protocol": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "mistral": {
        "name": "Mistral AI",
        "protocol": "openai_compatible",
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest",
    },
    "custom": {
        "name": "Custom / Local AI",
        "protocol": "openai_compatible",
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.2",
    }
}


@dataclass
class UserAIProvider:
    id: str
    name: str
    protocol: str = "openai_compatible"  # 'openai_compatible', 'gemini', 'custom_http'
    base_url: str = ""
    model: str = ""
    encrypted_key: str = ""
    enabled: bool = True
    is_primary: bool = False
    timeout_seconds: int = 15
    custom_headers: Dict[str, str] = field(default_factory=dict)

    # Diagnostic state
    status: str = "UNTESTED"  # UNTESTED, READY, ERROR, 401_UNAUTHORIZED, 429_RATE_LIMITED, TIMEOUT
    last_latency_ms: Optional[int] = None
    last_tested_time: Optional[float] = None
    last_error: Optional[str] = None

    @property
    def api_key(self) -> str:
        return decrypt_secret(self.encrypted_key)

    @api_key.setter
    def api_key(self, value: str):
        self.encrypted_key = encrypt_secret(value)

    def to_dict(self, mask_credentials: bool = False) -> Dict[str, Any]:
        d = asdict(self)
        if mask_credentials:
            d["api_key"] = mask_key(self.api_key)
            d.pop("encrypted_key", None)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserAIProvider":
        # Handle legacy slot structure if migrated
        p_id = str(data.get("id") or uuid.uuid4().hex[:8])
        name = data.get("name") or "AI Provider"
        protocol = data.get("protocol") or "openai_compatible"
        base_url = data.get("base_url") or ""
        model = data.get("model") or ""
        enc_key = data.get("encrypted_key") or ""
        if not enc_key and "api_key" in data and data["api_key"]:
            enc_key = encrypt_secret(data["api_key"])

        return cls(
            id=p_id,
            name=name,
            protocol=protocol,
            base_url=base_url,
            model=model,
            encrypted_key=enc_key,
            enabled=data.get("enabled", True),
            is_primary=data.get("is_primary", False),
            timeout_seconds=data.get("timeout_seconds", 15),
            custom_headers=data.get("custom_headers", {}),
            status=data.get("status", "UNTESTED"),
            last_latency_ms=data.get("last_latency_ms"),
            last_tested_time=data.get("last_tested_time"),
            last_error=data.get("last_error")
        )


class APIManager:
    """Central singleton manager for user-owned AI providers."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(APIManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.providers: List[UserAIProvider] = []
        self._listeners: List[Callable[[str, Dict[str, Any]], None]] = []
        self._lock = threading.Lock()
        self._load_providers()
        self._initialized = True

    def _ensure_dir(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)

    def _load_providers(self):
        """Loads user-owned AI providers. On fresh install, starts with zero providers."""
        self._ensure_dir()
        if not os.path.exists(AI_PROVIDERS_FILE):
            self.providers = []
            return

        try:
            with open(AI_PROVIDERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                loaded = [UserAIProvider.from_dict(item) for item in data.get("providers", [])]
                self.providers = loaded
        except Exception:
            self.providers = []

    def save_providers(self):
        self._ensure_dir()
        try:
            payload = {
                "version": 2,
                "updated_at": time.time(),
                "providers": [asdict(p) for p in self.providers]
            }
            with open(AI_PROVIDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def subscribe(self, callback: Callable[[str, Dict[str, Any]], None]):
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[str, Dict[str, Any]], None]):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def emit_event(self, event_type: str, data: Optional[Dict[str, Any]] = None):
        payload = data or {}
        payload["timestamp"] = time.time()
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(event_type, payload)
            except Exception:
                pass

    def get_providers(self) -> List[UserAIProvider]:
        with self._lock:
            return list(self.providers)

    def get_provider(self, provider_id: str) -> Optional[UserAIProvider]:
        with self._lock:
            for p in self.providers:
                if str(p.id) == str(provider_id):
                    return p
            return None

    def add_provider(
        self,
        name: str,
        protocol: str,
        base_url: str,
        model: str,
        api_key: str,
        enabled: bool = True,
        is_primary: bool = False
    ) -> UserAIProvider:
        with self._lock:
            p_id = str(uuid.uuid4().hex[:8])
            # If this is the first provider or marked primary, set is_primary True
            if not self.providers or is_primary:
                for existing in self.providers:
                    existing.is_primary = False
                is_primary = True

            prov = UserAIProvider(
                id=p_id,
                name=name.strip(),
                protocol=protocol.strip(),
                base_url=base_url.strip().rstrip("/"),
                model=model.strip(),
                enabled=enabled,
                is_primary=is_primary
            )
            prov.api_key = api_key.strip()
            self.providers.append(prov)
            self.save_providers()

        self.emit_event(EVENT_PROVIDER_ADDED, {"provider_id": prov.id, "name": prov.name})
        return prov

    def update_provider(self, provider_id: str, **kwargs) -> bool:
        with self._lock:
            prov = None
            for p in self.providers:
                if str(p.id) == str(provider_id):
                    prov = p
                    break
            if not prov:
                return False

            for k, v in kwargs.items():
                if k == "api_key":
                    prov.api_key = v.strip()
                elif hasattr(prov, k):
                    setattr(prov, k, v)

            self.save_providers()

        self.emit_event(EVENT_PROVIDER_CONFIG_CHANGED, {"provider_id": prov.id, "name": prov.name})
        return True

    def remove_provider(self, provider_id: str) -> bool:
        removed_name = ""
        with self._lock:
            target = None
            for p in self.providers:
                if str(p.id) == str(provider_id):
                    target = p
                    break
            if not target:
                return False

            was_primary = target.is_primary
            removed_name = target.name
            self.providers = [p for p in self.providers if str(p.id) != str(provider_id)]

            # If removed was primary, pick the first remaining provider as primary
            if was_primary and self.providers:
                self.providers[0].is_primary = True

            self.save_providers()

        self.emit_event(EVENT_PROVIDER_REMOVED, {"provider_id": provider_id, "name": removed_name})
        return True

    def set_primary(self, provider_id: str) -> bool:
        p_name = ""
        with self._lock:
            found = False
            for p in self.providers:
                if str(p.id) == str(provider_id):
                    p.is_primary = True
                    p_name = p.name
                    found = True
                else:
                    p.is_primary = False
            if not found:
                return False
            self.save_providers()

        self.emit_event(EVENT_PROVIDER_PRIMARY_CHANGED, {"provider_id": provider_id, "name": p_name})
        return True

    def get_primary_provider(self) -> Optional[UserAIProvider]:
        with self._lock:
            for p in self.providers:
                if p.is_primary and p.enabled:
                    return p
            # Fallback to first enabled provider
            for p in self.providers:
                if p.enabled:
                    return p
            return None

    def get_ready_providers(self) -> List[UserAIProvider]:
        """Returns enabled providers whose real connection test succeeded (status == 'READY')."""
        with self._lock:
            return [p for p in self.providers if p.enabled and p.status == "READY"]

    def test_provider(self, provider_id: str) -> Tuple[bool, str, Optional[int]]:
        """
        Executes a genuine HTTP/API probe against the provider endpoint.
        Returns: (success: bool, message: str, latency_ms: Optional[int])
        """
        prov = self.get_provider(provider_id)
        if not prov:
            return False, "Provider not found", None

        key = prov.api_key
        t0 = time.time()
        self.emit_event(EVENT_PROVIDER_TEST_STARTED, {"provider_id": prov.id, "name": prov.name})

        # Gemini protocol test
        if prov.protocol == "gemini":
            if not key:
                prov.status = "NOT_CONFIGURED"
                prov.last_error = "Missing Gemini API Key"
                self.save_providers()
                return False, "Gemini API key is required", None

            endpoint = f"{prov.base_url or 'https://generativelanguage.googleapis.com'}/v1beta/models?key={key}"
            try:
                resp = requests.get(endpoint, timeout=prov.timeout_seconds)
                lat = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
                    prov.status = "READY"
                    prov.last_latency_ms = lat
                    prov.last_tested_time = time.time()
                    prov.last_error = None
                    self.save_providers()
                    self.emit_event(EVENT_PROVIDER_TEST_SUCCESS, {"provider_id": prov.id, "latency_ms": lat})
                    return True, f"Verified Gemini API ({len(models)} models available)", lat
                elif resp.status_code == 400 or resp.status_code == 403:
                    prov.status = "401_UNAUTHORIZED"
                    prov.last_error = f"HTTP {resp.status_code}: Invalid API Key"
                    self.save_providers()
                    return False, f"Invalid Gemini API Key (HTTP {resp.status_code})", None
                else:
                    prov.status = f"HTTP_{resp.status_code}"
                    prov.last_error = f"HTTP {resp.status_code}: {resp.text[:100]}"
                    self.save_providers()
                    return False, f"HTTP Error {resp.status_code}", None
            except requests.Timeout:
                prov.status = "TIMEOUT"
                prov.last_error = "Connection timed out"
                self.save_providers()
                return False, "Request timed out", None
            except Exception as e:
                prov.status = "ERROR"
                prov.last_error = str(e)
                self.save_providers()
                return False, f"Connection failed: {e}", None

        # OpenAI-Compatible protocol test
        else:
            base = prov.base_url.rstrip("/") if prov.base_url else "https://api.openai.com/v1"
            endpoint = f"{base}/models"
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            headers.update(prov.custom_headers)

            try:
                resp = requests.get(endpoint, headers=headers, timeout=prov.timeout_seconds)
                lat = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    prov.status = "READY"
                    prov.last_latency_ms = lat
                    prov.last_tested_time = time.time()
                    prov.last_error = None
                    self.save_providers()
                    self.emit_event(EVENT_PROVIDER_TEST_SUCCESS, {"provider_id": prov.id, "latency_ms": lat})
                    return True, f"Verified OpenAI endpoint ({lat}ms)", lat
                elif resp.status_code == 401:
                    prov.status = "401_UNAUTHORIZED"
                    prov.last_error = "Invalid API Key (HTTP 401)"
                    self.save_providers()
                    return False, "Invalid API Key (HTTP 401 Unauthorized)", None
                elif resp.status_code == 404:
                    # Some local servers don't expose /models, try a lightweight /chat/completions ping
                    chat_endpoint = f"{base}/chat/completions"
                    test_payload = {
                        "model": prov.model or "default",
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1
                    }
                    resp_chat = requests.post(chat_endpoint, headers=headers, json=test_payload, timeout=prov.timeout_seconds)
                    lat = int((time.time() - t0) * 1000)
                    if resp_chat.status_code in [200, 400]:
                        prov.status = "READY"
                        prov.last_latency_ms = lat
                        prov.last_tested_time = time.time()
                        prov.last_error = None
                        self.save_providers()
                        return True, f"Verified Chat endpoint ({lat}ms)", lat

                prov.status = f"HTTP_{resp.status_code}"
                prov.last_error = f"HTTP {resp.status_code}: {resp.text[:100]}"
                self.save_providers()
                return False, f"Server returned HTTP {resp.status_code}", None
            except requests.Timeout:
                prov.status = "TIMEOUT"
                prov.last_error = "Connection timed out"
                self.save_providers()
                return False, "Connection timed out", None
            except Exception as e:
                prov.status = "ERROR"
                prov.last_error = str(e)
                self.save_providers()
                return False, f"Network error: {e}", None

    def fetch_models(self, provider_id: str) -> Tuple[bool, List[str], str]:
        """Queries the provider's /models endpoint for dynamic model autocompletion."""
        prov = self.get_provider(provider_id)
        if not prov:
            return False, [], "Provider not found"

        key = prov.api_key
        if prov.protocol == "gemini":
            if not key:
                return False, [], "Gemini API key is required"
            endpoint = f"{prov.base_url or 'https://generativelanguage.googleapis.com'}/v1beta/models?key={key}"
            try:
                resp = requests.get(endpoint, timeout=10)
                if resp.status_code == 200:
                    models = [m.get("name", "").replace("models/", "") for m in resp.json().get("models", [])]
                    return True, models, f"Found {len(models)} Gemini models"
                return False, [], f"HTTP {resp.status_code}"
            except Exception as e:
                return False, [], str(e)
        else:
            base = prov.base_url.rstrip("/") if prov.base_url else "https://api.openai.com/v1"
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            try:
                resp = requests.get(f"{base}/models", headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                    return True, models, f"Found {len(models)} models"
                return False, [], f"HTTP {resp.status_code}"
            except Exception as e:
                return False, [], str(e)

    def format_header_label(self, primary_provider_name: str) -> Tuple[str, str]:
        """
        Formats header button label and tooltip dynamically.
        Never hardcodes 'Gemini' or assumptions.
        """
        if not self.providers or not any(p.enabled for p in self.providers):
            return "◆ V.E.D.A. • NO AI CONFIGURED", "No AI providers configured. Click to add your provider."

        ready_providers = self.get_ready_providers()
        primary = self.get_primary_provider()

        if not ready_providers:
            if primary and primary.status in ["ERROR", "TIMEOUT", "401_UNAUTHORIZED"]:
                return f"◆ V.E.D.A. • AI OFFLINE", f"{primary.name} connection failed. Check credentials."
            return "◆ V.E.D.A. • AI OFFLINE", "Configured AI providers are offline or untested."

        # At least one provider is ready
        active_name = primary.name if (primary and primary.status == "READY") else ready_providers[0].name
        tooltip = f"Primary AI: {active_name} [{primary.model if primary else ''}]\nActive Verified Providers: " + ", ".join([p.name for p in ready_providers])
        return f"◆ V.E.D.A. • {active_name}", tooltip

    def format_status_pill(self, is_online: bool, active_ai_name: str, failover_occurred: bool = False) -> Tuple[str, str]:
        """
        Formats the dynamic status pill and color badge.
        Returns: (status_text, hex_color)
        """
        if not is_online:
            return "OFFLINE • NO INTERNET", "#d97706"

        if not self.providers or not any(p.enabled for p in self.providers):
            return "NO AI CONFIGURED", "#475569"

        ready = self.get_ready_providers()
        if not ready:
            has_err = any("ERROR" in p.status or "40" in p.status for p in self.providers if p.enabled)
            if has_err:
                return "AI OFFLINE", "#b91c1c"
            return "AI NOT TESTED", "#eab308"

        primary = self.get_primary_provider()
        name = (primary.name if primary and primary.status == "READY" else ready[0].name).upper()
        if failover_occurred:
            return f"ONLINE • {name} (FAILOVER)", "#ea580c"
        return f"ONLINE • {name} READY", "#0284c7"


api_manager = APIManager()
# Backwards compatibility alias
PRESET_TEMPLATES = PROVIDER_PRESETS
