"""
V.E.D.A. AI Provider Router & Health Management
Connects user-configured AI providers to the execution pipeline.
Supports dynamic failover, offline local AI fallback, and connectivity recovery.
"""

import os
import re
import time
import queue
import threading
from typing import Any, Dict, List, Optional, Iterator, Callable
from PIL import Image

from veda.config import VedaConfig
from veda.providers import AIProvider, GeminiProvider, LocalDeterministicProvider, GenericOpenAIProvider
from veda.api_manager import api_manager, UserAIProvider
from veda.capabilities import WindowsCapabilities
from veda.connectivity import internet_monitor


class AIRouter:
    """Intelligent AI Router routing to user-owned AI providers with deterministic fallback."""

    def __init__(self, on_provider_switched: Optional[Callable[[str, str], None]] = None):
        self.on_provider_switched = on_provider_switched

        # Provider instances cache
        self._provider_instances: Dict[str, AIProvider] = {}
        self._local: Optional[LocalDeterministicProvider] = None

        # State tracking
        self.active_provider_name: str = "None"
        self.last_provider_used: str = "None"
        self.last_fallback_reason: Optional[str] = None
        self.last_failover_time: Optional[float] = None
        self.last_request_duration: float = 0.0

        # Persistent user provider mode & preference
        saved_settings = VedaConfig.get_settings()
        self.provider_mode: str = saved_settings.get("provider_mode", "AUTOMATIC")
        self.selected_provider_id: Optional[str] = saved_settings.get("selected_provider_id")

        # Connectivity Monitor
        internet_monitor.on_status_changed = self._on_internet_status_changed
        internet_monitor.start(run_immediate=True)

        self._update_active_name()

    def _update_active_name(self):
        primary = api_manager.get_primary_provider()
        if primary:
            self.active_provider_name = primary.name
        else:
            self.active_provider_name = "Offline Local AI"

    def set_provider_mode(self, mode: str, provider_id: Optional[str] = None):
        self.provider_mode = "MANUAL" if mode.upper() == "MANUAL" else "AUTOMATIC"
        if provider_id:
            self.selected_provider_id = provider_id
            api_manager.set_primary(provider_id)
        VedaConfig.update_setting("provider_mode", self.provider_mode)
        if self.selected_provider_id:
            VedaConfig.update_setting("selected_provider_id", self.selected_provider_id)
        self._update_active_name()
        api_manager.emit_event("PROVIDER_PRIMARY_CHANGED", {
            "mode": self.provider_mode,
            "selected_provider_id": self.selected_provider_id,
            "active_provider": self.active_provider_name
        })

    def _on_internet_status_changed(self, old_status: str, new_status: str):
        if new_status == "ONLINE":
            # Clear transient network errors on providers
            for p in self._provider_instances.values():
                if p.status in ["ERROR", "OFFLINE"] and not p.is_in_cooldown():
                    p.status = "AVAILABLE"
                    p.last_error = None
            self._update_active_name()

    @property
    def local(self) -> LocalDeterministicProvider:
        if self._local is None:
            self._local = LocalDeterministicProvider()
        return self._local

    def get_provider_instance(self, cfg: UserAIProvider) -> AIProvider:
        key = (cfg.id, cfg.protocol, cfg.base_url, cfg.model, cfg.encrypted_key)
        cache_id = str(cfg.id)
        if cache_id in self._provider_instances:
            inst = self._provider_instances[cache_id]
            # Update key/model/base if changed
            if hasattr(inst, "api_key"):
                inst.api_key = cfg.api_key
            if hasattr(inst, "model_name"):
                inst.model_name = cfg.model
            if hasattr(inst, "base_url"):
                inst.base_url = cfg.base_url
            return inst

        if cfg.protocol == "gemini":
            inst = GeminiProvider(api_key=cfg.api_key, model_name=cfg.model or "gemini-2.5-flash")
        else:
            inst = GenericOpenAIProvider(
                name=cfg.name,
                base_url=cfg.base_url or "https://api.openai.com/v1",
                api_key=cfg.api_key,
                model_name=cfg.model or "gpt-4o-mini",
                timeout=cfg.timeout_seconds,
                custom_headers=cfg.custom_headers
            )
        self._provider_instances[cache_id] = inst
        return inst

    def build_active_chain(self) -> List[tuple]:
        """Constructs the failover chain from user-configured providers in priority order."""
        chain = []
        providers = api_manager.get_providers()
        enabled = [p for p in providers if p.enabled]

        if self.provider_mode == "MANUAL" and self.selected_provider_id:
            sel = api_manager.get_provider(self.selected_provider_id)
            if sel and sel.enabled:
                inst = self.get_provider_instance(sel)
                chain.append((sel.name, inst))

        if not chain:
            # Primary first
            primary = api_manager.get_primary_provider()
            if primary and primary.enabled:
                chain.append((primary.name, self.get_provider_instance(primary)))
            # Remaining enabled providers
            for p in enabled:
                if not primary or p.id != primary.id:
                    chain.append((p.name, self.get_provider_instance(p)))

        # Local deterministic fallback is always available at the end of the chain
        chain.append(("Offline Local AI", self.local))
        return chain

    def get_diagnostics(self) -> Dict[str, Any]:
        self._update_active_name()
        return {
            "active_provider": self.active_provider_name,
            "last_provider_used": self.last_provider_used,
            "last_fallback_reason": self.last_fallback_reason,
            "last_failover_time": self.last_failover_time,
            "last_request_duration": self.last_request_duration,
            "provider_mode": self.provider_mode,
            "is_online": internet_monitor.is_internet_available(),
            "configured_count": len(api_manager.providers),
            "ready_count": len(api_manager.get_ready_providers())
        }

    def execute_with_tools_stream(
        self,
        prompt: str,
        tools: List[Any],
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        image: Optional[Image.Image] = None
    ) -> Iterator[Dict[str, Any]]:
        chain = self.build_active_chain()
        is_net = internet_monitor.is_internet_available()

        # If user configured zero online providers, inform them cleanly unless deterministic action matches
        has_online_user_provider = any(p.enabled and p.api_key for p in api_manager.providers)
        if not has_online_user_provider:
            # Check fast-path deterministic capabilities first
            t0 = time.time()
            try:
                for chunk in self.local.generate_with_tools_stream(prompt, tools, system_prompt, history):
                    self.last_provider_used = "Offline Local AI"
                    self.last_request_duration = time.time() - t0
                    yield chunk
                return
            except Exception:
                yield {
                    "type": "text",
                    "content": "No AI provider is configured. Please open Settings → AI Providers to add your API credentials."
                }
                return

        t0 = time.time()
        for prov_name, provider in chain:
            # Skip cloud providers if device has no internet
            if not is_net and prov_name != "Offline Local AI":
                continue

            try:
                stream = provider.generate_with_tools_stream(prompt, tools, system_prompt, history)
                first_item_yielded = False
                for item in stream:
                    first_item_yielded = True
                    yield item

                self.last_provider_used = prov_name
                self.last_request_duration = time.time() - t0
                return
            except Exception as e:
                self.last_fallback_reason = f"{prov_name} failed: {e}"
                self.last_failover_time = time.time()
                if self.on_provider_switched:
                    try:
                        self.on_provider_switched(prov_name, "Next Fallback")
                    except Exception:
                        pass
                continue

        # Ultimate deterministic safety yield
        yield {"type": "text", "content": "I am currently unable to reach any configured AI service. Please verify your internet and API settings."}

    def execute_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None
    ) -> Iterator[str]:
        for item in self.execute_with_tools_stream(prompt, [], system_prompt, history):
            if item.get("type") == "text" and item.get("content"):
                yield item["content"]

    def refresh_health(self, silent: bool = False):
        internet_monitor.check_now(async_mode=False)
        self._update_active_name()
