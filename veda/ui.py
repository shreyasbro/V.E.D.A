import os
import sys
import re
import math
import random
import threading
import time
from typing import Optional, List, Dict
from PIL import Image, ImageDraw
import pystray
from dotenv import load_dotenv
import customtkinter as ctk
import tkinter as tk

load_dotenv()

from veda.agent import GeminiAgent
from veda.api_manager import api_manager, mask_key, PRESET_TEMPLATES
from veda.config import VedaConfig
from veda.vision import live_screen_manager
from veda.hardware import microphone_subsystem, camera_subsystem
from veda.camera_mouse import camera_mouse_controller
from veda.tts import tts_engine
from veda.permissions import PermissionGuard
from veda.language import detect_language
from veda.connectivity import internet_monitor
from veda.hot_reload import dev_watcher, safely_teardown_all_subsystems
from veda.automation import automation_engine, AutomationRule
from veda.notifications import notification_manager, Notification
from veda.updater import production_updater
from veda.version import VERSION, BUILD, RELEASE_CHANNEL


class CTkToolTip:
    """Lightweight tooltip popup for CustomTkinter widgets."""
    def __init__(self, widget, text: str, delay_ms: int = 400):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.tip_window = None
        self._id = None
        self.widget.bind("<Enter>", self._on_enter, add="+")
        self.widget.bind("<Leave>", self._on_leave, add="+")
        self.widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._cancel()
        self._id = self.widget.after(self.delay_ms, self._show)

    def _on_leave(self, event=None):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None

    def _show(self):
        if self.tip_window or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            background="#0f172a",
            foreground="#38bdf8",
            relief="solid",
            borderwidth=1,
            font=("Consolas", 9, "bold"),
            padx=8,
            pady=4
        )
        label.pack()

    def _hide(self):
        if self.tip_window:
            try:
                self.tip_window.destroy()
            except Exception:
                pass
            self.tip_window = None


class AudioWaveformCanvas(ctk.CTkCanvas):
    """
    Real-time dynamic cyber-audio waveform visualizer.
    Directly reflects incoming microphone RMS audio amplitude.
    Completely flat and resting when silent or mic off; dynamically active during speech/TTS.
    """
    def __init__(self, master, width=88, height=36, **kwargs):
        super().__init__(master, width=width, height=height, bg="#05080e", highlightthickness=0, **kwargs)
        self.w = width
        self.h = height
        self.num_bars = 12
        self.bar_values = [0.0] * self.num_bars
        self.current_level = 0.0
        self.target_level = 0.0
        self.mode_color = "#38bdf8"
        self._animating = True
        self._step()

    def set_level(self, level: float, color: str = "#38bdf8"):
        """Sets target audio amplitude (0.0 to 1.0) and rendering color."""
        self.target_level = max(0.0, min(1.0, float(level)))
        self.mode_color = color

    def _step(self):
        if not self.winfo_exists():
            return
        self.delete("all")

        # Smooth exponential decay / attack
        self.current_level += (self.target_level - self.current_level) * 0.42
        level = self.current_level

        bar_w = max(2, (self.w - (self.num_bars * 3)) // self.num_bars)
        mid_y = self.h / 2

        is_active = level > 0.03

        for i in range(self.num_bars):
            if is_active:
                # Responsive modulation based on real level
                phase = math.sin(time.time() * 12.0 + (i * 0.55))
                bar_scale = max(0.05, level * (0.65 + 0.35 * abs(phase)))
                bh = max(3.0, bar_scale * (self.h - 6))
                color = self.mode_color
            else:
                bh = 2.0  # Resting flat line
                color = "#1e293b"

            x0 = i * (bar_w + 3) + 4
            x1 = x0 + bar_w
            y0 = mid_y - (bh / 2)
            y1 = mid_y + (bh / 2)

            self.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

        self.after(35, self._step)


class VedaApp(ctk.CTk):
    """
    V.E.D.A. — Virtual Executive Desktop Assistant
    Created by Shreyas.
    Futuristic Dark Glassmorphism AI Desktop Agent UI with Cyber Animations.
    """

    def __init__(self):
        super().__init__()

        self.identity = VedaConfig.get_identity()
        self.settings = VedaConfig.get_settings()

        # Appearance & Geometry
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("V.E.D.A. — Virtual Executive Desktop Assistant")
        self.geometry("820x700")
        self.minsize(760, 600)
        self.configure(fg_color="#07090e")

        # Desktop Overlay & Live Screen Tracking
        self.is_desktop_mode = bool(self.settings.get("desktop_mode", False))
        self.is_paused = False
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Voice Conversation & Dual Mode State
        self.mic_mode = self.settings.get("mic_mode", "mic_toggle")
        self.is_mic_active = False
        self._is_agent_busy = False
        self._is_refreshing_health = False
        self._provider_menu_window = None
        self._notification_window = None
        self._settings_window = None
        self._last_real_status_text = "ONLINE • NO AI CONFIGURED"
        self._status_glow_phase = 0

        # Protocol handlers for background running
        self.protocol("WM_DELETE_WINDOW", self.on_close_window)

        # Initialize Agent with Unified Router
        self.agent = GeminiAgent(
            status_callback=self.update_status_safe,
            action_callback=self.log_action_safe,
            provider_switched_callback=lambda old, new: self.after(0, lambda: self._on_ai_provider_switched(old, new))
        )

        # Connect Real Internet Connectivity Monitor
        self.internet_monitor = internet_monitor
        self._connectivity_listener = lambda online, diag: self.after(0, lambda: self._update_connection_status(online, diag))
        self.internet_monitor.add_listener(self._connectivity_listener)
        self.internet_monitor.start()

        # Connect and Start Natural-Language Automation Engine
        self.automation_engine = automation_engine
        self.automation_engine.tts_callback = lambda text, lang: tts_engine.speak(text, language_mode=lang)
        self.automation_engine.on_trigger_callback = lambda rule, state: self.after(0, lambda: self.add_message(f"⚡ [AUTOMATION] {rule.alert_message}", sender="assistant", action_tag="AUTOMATION"))
        self.automation_engine.start()

        # Start Development Hot-Reload watcher if running in dev environment
        if not getattr(sys, "frozen", False):
            dev_watcher.start()

        self.worker_thread: Optional[threading.Thread] = None

        # Link instant barge-in and real-time audio/camera pipeline callbacks
        microphone_subsystem.on_speech_started = self._handle_barge_in
        microphone_subsystem.on_level_change = self._on_mic_level
        microphone_subsystem.on_state_change = self._on_mic_state_change
        microphone_subsystem.on_interim_transcript = lambda text: self.after(0, lambda: self._on_interim_speech(text))
        tts_engine.on_speech_started = self._on_tts_start
        tts_engine.on_speech_finished = self._on_tts_finish
        camera_subsystem.on_state_change = self._on_camera_state_change
        camera_subsystem.on_frame_received = self._on_camera_frame_received
        camera_mouse_controller.on_preview_frame = lambda img, gest, det, fps: self.after(0, self._on_cam_mouse_preview_frame, img, gest, det, fps)
        camera_mouse_controller.on_state_change = lambda st: self.after(0, self._on_cam_mouse_state_change, st)

        # Build Main View Hierarchy
        self._build_header()
        self._build_chat_stream()
        self._build_input_dock()

        # Load persisted conversation history
        self._load_persisted_history()

        # Setup Windows System Tray
        self._init_system_tray()

        # Global Hotkey for Quick Reload / Force Refresh
        self.bind("<Control-Shift-R>", lambda e: self.restart_veda())
        self.bind("<Control-Shift-r>", lambda e: self.restart_veda())
        # Global Emergency Stop for Camera Mouse
        self.bind("<Escape>", lambda e: self._handle_emergency_stop())

        # Start ambient UI glowing animations
        self._start_ambient_glow()

        # Subscribe to centralized APIManager events for dynamic header updates
        api_manager.subscribe(lambda ev, data: self.after(0, self._on_provider_state_event, ev, data))

        # Subscribe to NotificationManager events for bell badge updates
        notification_manager.subscribe(lambda ev, data: self.after(0, self._refresh_notification_badge))

        # Synchronize header badges with persisted provider settings
        self.after(50, lambda: (self._refresh_ai_provider_button(), self._refresh_status_pill(), self._refresh_notification_badge()))

        # Connect ProductionUpdater hooks (busy check and prompt dialog)
        production_updater.set_busy_hook(lambda: getattr(self, "_is_agent_busy", False) or getattr(self.automation_engine, "_is_running", False))
        production_updater.set_prompt_restart_callback(lambda ver: self.after(0, lambda: self.prompt_restart_modal(ver)))

        # Start 24-hour periodic update checker and initial check if enabled
        if VedaConfig.get_settings().get("update_auto_check", True):
            production_updater.start_periodic_checker(24.0)
            self.after(3000, lambda: production_updater.check_for_updates_async())

        # First-Run Permission Onboarding Check
        if VedaConfig.is_first_run():
            self.after(500, self.open_first_run_onboarding)

    def _on_tts_start(self):
        self.update_hearing_state("SPEAKING")
        if hasattr(self, "waveform"):
            self.waveform.set_level(0.75, "#a855f7")

    def _on_tts_finish(self):
        if self.mic_mode == "always_on" and microphone_subsystem.is_always_on:
            self.update_hearing_state("MIC_READY")
        else:
            self.update_hearing_state("MIC_OFF")
        if hasattr(self, "waveform"):
            self.waveform.set_level(0.0, "#38bdf8")

    def _on_mic_level(self, level: float):
        if hasattr(self, "waveform") and not tts_engine.is_speaking:
            if level > 0.08:
                self.waveform.set_level(level, "#22c55e")
            elif level > 0.02:
                self.waveform.set_level(level, "#38bdf8")
            else:
                self.waveform.set_level(0.0, "#38bdf8")

    def _on_mic_state_change(self, state: str):
        self.after(0, lambda: self.update_hearing_state(state))

    def update_hearing_state(self, state: str):
        """
        Updates the dedicated Hearing Indicator with the exact 7 states:
        MIC_OFF, MIC_READY, HEARING, SPEECH_DETECTED, PROCESSING, SPEAKING, MIC_ERROR.
        """
        state_map = {
            "MIC_OFF": ("🔴 MIC OFF", "#1e293b", "#94a3b8"),
            "MIC_INITIALIZING": ("🟡 MIC INIT", "#713f12", "#fde047"),
            "MIC_READY": ("⚪ MIC READY", "#1e293b", "#cbd5e1"),
            "HEARING": ("🟢 HEARING", "#14532d", "#22c55e"),
            "SPEECH_DETECTED": ("🟡 SPEECH DETECTED", "#713f12", "#eab308"),
            "TRANSCRIBING": ("🔵 TRANSCRIBING", "#1e3a8a", "#60a5fa"),
            "PROCESSING": ("🔵 PROCESSING", "#1e3a8a", "#60a5fa"),
            "SPEAKING": ("🟣 SPEAKING", "#581c87", "#c084fc"),
            "MIC_ERROR": ("⚠️ MIC ERROR", "#7f1d1d", "#f87171"),
        }
        text, bg_col, text_col = state_map.get(state, (f"● {state}", "#1e293b", "#cbd5e1"))

        if hasattr(self, "btn_mic"):
            self.btn_mic.configure(text=text, fg_color=bg_col, text_color=text_col)

        if hasattr(self, "status_pill"):
            if state in ["PROCESSING", "SPEAKING", "SPEECH_DETECTED", "TRANSCRIBING"]:
                self.status_pill.configure(text=f"● {state}", fg_color=bg_col)
            else:
                self._refresh_status_pill()

    def _on_interim_speech(self, interim_text: str):
        """Displays real interim STT words directly inside the normal input entry box."""
        if hasattr(self, "input_field") and self.input_field.winfo_exists():
            self.input_field.delete(0, "end")
            self.input_field.insert(0, interim_text)
            self.update_hearing_state("TRANSCRIBING")

    def _update_connection_status(self, is_online: bool, diagnostics: dict):
        """Standard connection status handler invoked by InternetConnectivityMonitor listener."""
        self._on_connectivity_changed(is_online, diagnostics)

    def _on_connectivity_changed(self, is_online: bool, diagnostics: dict):
        """Called when internet status changes (checked asynchronously every 60s via real HTTPS)."""
        self._refresh_status_pill()
        if not is_online:
            self.add_message("Internet connection lost. Switched to Offline AI.", sender="assistant", action_tag="OFFLINE", animate=False)
        else:
            self.add_message("Internet connection restored. Cloud AI re-enabled.", sender="assistant", action_tag="ONLINE", animate=False)

    def _on_provider_state_event(self, event_type: str, data: dict):
        """Event listener called when any AI provider state changes in the centralized registry."""
        self._refresh_ai_provider_button()
        self._refresh_status_pill()

    def _refresh_status_pill(self):
        """
        Updates the status pill to display dynamic, real-time Internet + AI status
        without hardcoded provider assumptions.
        """
        if not hasattr(self, "status_pill"):
            return
        if getattr(self, "_is_refreshing_health", False):
            self.status_pill.configure(text="CHECKING...", fg_color="#334155")
            return

        is_net = internet_monitor.is_internet_available()
        diag = self.agent.router.get_diagnostics() if hasattr(self, "agent") and hasattr(self.agent, "router") else {}
        active_ai = diag.get("active_provider", "Gemini")
        failover_active = bool(diag.get("last_fallback_reason") and diag.get("last_fallback_reason") != "None")

        status_text, color = api_manager.format_status_pill(is_net, active_ai, failover_occurred=failover_active)
        self._last_real_status_text = status_text
        self.status_pill.configure(text=status_text, fg_color=color)

    def _refresh_ai_provider_button(self):
        """
        Dynamically calculates header button label, colors, and tooltip
        reflecting all active, verified AI providers and the primary provider.
        """
        if not hasattr(self, "btn_ai_provider"):
            return
        diag = self.agent.router.get_diagnostics() if hasattr(self, "agent") and hasattr(self.agent, "router") else {}
        active_ai = diag.get("active_provider", "Gemini")

        label, tip = api_manager.format_header_label(active_ai)
        
        # Color coding: Amber for Offline, Cyan/Blue for verified cloud LLMs
        if "Offline" in active_ai or "Local" in active_ai:
            color = "#d97706"
        elif any(s.status == "READY" for s in api_manager.get_active_ready_providers()):
            color = "#0284c7"
        else:
            color = "#475569"

        # Calculate width dynamically to fit multiple provider names comfortably
        target_width = max(165, min(290, len(label) * 8 + 30))
        self.btn_ai_provider.configure(text=label, fg_color=color, width=target_width)
        if hasattr(self, "tip_ai_provider"):
            self.tip_ai_provider.set_text(tip)

    def trigger_health_refresh(self):
        """
        Triggered when user clicks the ONLINE STATUS pill in the header.
        Performs an immediate, real-time Internet reachability check and refreshes
        Gemini and Offline AI health without waiting 60 seconds.
        Preserves user's manual provider mode & selected provider.
        Does NOT restart the app or emit chat spam.
        """
        if getattr(self, "_is_refreshing_health", False):
            return

        self._is_refreshing_health = True
        if hasattr(self, "status_pill"):
            self.status_pill.configure(text="CHECKING...", fg_color="#334155")

        def _worker():
            try:
                # Real active health refresh on router and connectivity monitor
                if hasattr(self, "agent") and hasattr(self.agent, "router"):
                    self.agent.router.refresh_health(silent=True)
                else:
                    internet_monitor.check_now(async_mode=False)

                # Schedule UI synchronization
                def _update_ui():
                    self._is_refreshing_health = False
                    self._refresh_status_pill()
                    self._refresh_ai_provider_button()

                self.after(0, _update_ui)
            except Exception as e:
                print(f"[UI] Health reload error: {e}")
                def _err_ui():
                    self._is_refreshing_health = False
                    if hasattr(self, "status_pill"):
                        self.status_pill.configure(text="REFRESH FAILED", fg_color="#7f1d1d")
                        self.after(2000, self._refresh_status_pill)
                self.after(0, _err_ui)

        threading.Thread(target=_worker, daemon=True).start()

    # ==========================================
    # COMPACT IN-APP AI PROVIDER SWITCHER POPOVER
    # ==========================================
    def toggle_provider_menu(self):
        """Toggles the compact, non-modal AI Provider Switcher popover docked under btn_ai_provider."""
        if self._provider_menu_window and self._provider_menu_window.winfo_exists():
            self._close_provider_menu()
            return
        self._open_provider_menu()

    def _close_provider_menu(self):
        if self._provider_menu_window:
            try:
                self._provider_menu_window.destroy()
            except Exception:
                pass
            self._provider_menu_window = None

    def _open_provider_menu(self):
        self._close_provider_menu()

        # Calculate position right below the btn_ai_provider
        btn_x = self.btn_ai_provider.winfo_rootx()
        btn_y = self.btn_ai_provider.winfo_rooty() + self.btn_ai_provider.winfo_height() + 4

        # Create borderless top-level popover
        pop = tk.Toplevel(self)
        pop.wm_overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.configure(bg="#0b101b")
        pop.geometry(f"+{btn_x}+{btn_y}")
        self._provider_menu_window = pop

        # Container frame
        container = ctk.CTkFrame(
            pop,
            fg_color="#0b101b",
            corner_radius=10,
            border_width=1,
            border_color="#1e293b",
            width=320
        )
        container.pack(fill="both", expand=True, padx=2, pady=2)

        # Header title
        title_bar = ctk.CTkFrame(container, fg_color="transparent", height=32)
        title_bar.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkLabel(
            title_bar,
            text="V.E.D.A. AI PROVIDERS",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color="#38bdf8"
        ).pack(side="left")

        # Separator
        sep = ctk.CTkFrame(container, fg_color="#1e293b", height=1)
        sep.pack(fill="x", padx=10, pady=(0, 6))

        # Query real provider options from router
        options = self.agent.router.get_provider_options()
        diag = self.agent.router.get_diagnostics() if hasattr(self, "agent") and hasattr(self.agent, "router") else {}
        primary_name = diag.get("active_provider", "Gemini")

        for opt in options:
            opt_id = opt["id"]
            label = opt["label"]
            configured = opt["configured"]
            status = opt["status"]
            is_active = opt["is_active"]
            is_primary = (label.lower() in primary_name.lower() or primary_name.lower() in label.lower()) and opt_id != "AUTOMATIC"

            row = ctk.CTkFrame(container, fg_color="#0f172a" if (is_active or is_primary) else "transparent", corner_radius=6)
            row.pack(fill="x", padx=8, pady=2)

            check_mark = "● " if (is_active or is_primary) else ("○ " if configured else "× ")
            row_btn = ctk.CTkButton(
                row,
                text=f"{check_mark}{label}",
                font=ctk.CTkFont(family="Consolas", size=11, weight="bold" if (is_active or is_primary) else "normal"),
                text_color="#38bdf8" if (is_active or is_primary) else ("#f8fafc" if configured else "#64748b"),
                fg_color="transparent",
                hover_color="#1e293b" if configured else "#0f172a",
                anchor="w",
                height=28,
                command=lambda oid=opt_id: self._select_ai_provider(oid)
            )
            row_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

            # Primary Tag
            if is_primary:
                ctk.CTkLabel(
                    row,
                    text="PRIMARY",
                    font=ctk.CTkFont(family="Consolas", size=8, weight="bold"),
                    text_color="#38bdf8",
                    fg_color="#0369a1",
                    corner_radius=4,
                    width=48,
                    height=18
                ).pack(side="left", padx=4)

            # Status badge
            if opt_id == "AUTOMATIC":
                st_color = "#38bdf8"
            elif status == "READY":
                st_color = "#22c55e"
            elif "QUOTA" in status or "RATE" in status:
                st_color = "#ea580c"
            elif "NOT CONFIGURED" in status or "DISABLED" in status:
                st_color = "#64748b"
            else:
                st_color = "#ef4444" if ("ERROR" in status or "40" in status) else "#eab308"

            lbl_st = ctk.CTkLabel(
                row,
                text=status,
                font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
                text_color=st_color
            )
            lbl_st.pack(side="right", padx=(0, 8))

        # Bottom Action Bar: "⚡ Test this provider"
        sep2 = ctk.CTkFrame(container, fg_color="#1e293b", height=1)
        sep2.pack(fill="x", padx=10, pady=(6, 4))

        diag_row = ctk.CTkFrame(container, fg_color="transparent")
        diag_row.pack(fill="x", padx=8, pady=(2, 6))

        lbl_test_result = ctk.CTkLabel(
            container,
            text="",
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color="#94a3b8",
            wraplength=260,
            justify="left"
        )
        lbl_test_result.pack(fill="x", padx=10, pady=(0, 4))

        def _run_test_probe():
            sel = self.agent.router.selected_provider if self.agent.router.provider_mode == "MANUAL" else "AUTOMATIC"
            lbl_test_result.configure(text=f"Probing {sel}...", text_color="#38bdf8")
            def _worker():
                success, msg = self.agent.router.test_provider(sel)
                def _ui():
                    if not pop.winfo_exists():
                        return
                    if success:
                        lbl_test_result.configure(text=f"✓ {sel}: {msg[:60]}", text_color="#22c55e")
                    else:
                        lbl_test_result.configure(text=f"✕ {sel}: {msg[:80]}", text_color="#ef4444")
                self.after(0, _ui)
            threading.Thread(target=_worker, daemon=True).start()

        btn_test = ctk.CTkButton(
            diag_row,
            text="⚡ Test Current Provider",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color="#38bdf8",
            fg_color="#1e293b",
            hover_color="#334155",
            height=26,
            command=_run_test_probe
        )
        btn_test.pack(side="left", fill="x", expand=True, padx=(2, 4))

        btn_ai_settings = ctk.CTkButton(
            diag_row,
            text="⚙ Settings",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color="#38bdf8",
            fg_color="#1e293b",
            hover_color="#334155",
            width=75,
            height=26,
            command=lambda: (self._close_provider_menu(), self.open_settings_modal(initial_tab="AI Provider"))
        )
        btn_ai_settings.pack(side="right", padx=(0, 2))

        # Dismiss when clicking outside
        def _on_root_click(event):
            if not self._provider_menu_window or not self._provider_menu_window.winfo_exists():
                return
            wx = self._provider_menu_window.winfo_rootx()
            wy = self._provider_menu_window.winfo_rooty()
            ww = self._provider_menu_window.winfo_width()
            wh = self._provider_menu_window.winfo_height()
            if not (wx <= event.x_root <= wx + ww and wy <= event.y_root <= wy + wh):
                self._close_provider_menu()

        self.bind_all("<Button-1>", _on_root_click, add="+")

    # ==========================================
    # IN-APP NOTIFICATIONS PANEL & ACTIONS
    # ==========================================
    def _refresh_notification_badge(self):
        if not hasattr(self, "btn_notifications"):
            return
        unread = notification_manager.get_unread_count()
        if unread > 0:
            self.btn_notifications.configure(text=f"🔔 {unread}", fg_color="#0369a1", text_color="#ffffff")
        else:
            self.btn_notifications.configure(text="🔔 0", fg_color="#0f172a", text_color="#94a3b8")

    def toggle_notification_menu(self):
        if self._notification_window and self._notification_window.winfo_exists():
            self._close_notification_menu()
            return
        self._open_notification_menu()

    def _close_notification_menu(self):
        if self._notification_window:
            try:
                self._notification_window.destroy()
            except Exception:
                pass
            self._notification_window = None

    def _open_notification_menu(self):
        self._close_notification_menu()
        self._close_provider_menu()

        btn_x = self.btn_notifications.winfo_rootx() - 260
        btn_y = self.btn_notifications.winfo_rooty() + self.btn_notifications.winfo_height() + 4

        pop = tk.Toplevel(self)
        pop.wm_overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.configure(bg="#0b101b")
        pop.geometry(f"+{max(10, btn_x)}+{btn_y}")
        self._notification_window = pop

        container = ctk.CTkFrame(
            pop,
            fg_color="#0b101b",
            corner_radius=10,
            border_width=1,
            border_color="#1e293b",
            width=360
        )
        container.pack(fill="both", expand=True, padx=2, pady=2)

        # Header
        hdr = ctk.CTkFrame(container, fg_color="transparent", height=32)
        hdr.pack(fill="x", padx=12, pady=(10, 6))

        unread = notification_manager.get_unread_count()
        ctk.CTkLabel(
            hdr,
            text=f"NOTIFICATIONS ({unread} UNREAD)",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#38bdf8"
        ).pack(side="left")

        def _mark_all():
            notification_manager.mark_all_read()
            self._refresh_notification_badge()
            self._open_notification_menu()

        btn_clear = ctk.CTkButton(
            hdr,
            text="Mark All Read",
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color="#94a3b8",
            fg_color="#1e293b",
            hover_color="#334155",
            height=22,
            width=90,
            command=_mark_all
        )
        btn_clear.pack(side="right")

        # Scrollable Notifications list
        scroll_notifs = ctk.CTkScrollableFrame(container, fg_color="transparent", width=340, height=260)
        scroll_notifs.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        notifs = notification_manager.get_notifications(include_read=True)
        if not notifs:
            ctk.CTkLabel(
                scroll_notifs,
                text="No notifications at this time.",
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color="#64748b"
            ).pack(pady=30)
        else:
            for n in notifs[:15]:
                card_bg = "#0f172a" if not n.read else "#080c14"
                border_c = "#0284c7" if not n.read else "#1e293b"
                card = ctk.CTkFrame(scroll_notifs, fg_color=card_bg, corner_radius=6, border_width=1, border_color=border_c)
                card.pack(fill="x", pady=3)

                t_row = ctk.CTkFrame(card, fg_color="transparent")
                t_row.pack(fill="x", padx=8, pady=(6, 2))

                icon = "📦" if n.category == "UPDATE" else ("⚠️" if n.category in ["ERROR", "PERMISSION"] else "ℹ️")
                ctk.CTkLabel(
                    t_row,
                    text=f"{icon} {n.title}",
                    font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
                    text_color="#38bdf8" if not n.read else "#cbd5e1"
                ).pack(side="left")

                # Action buttons for update
                msg_lbl = ctk.CTkLabel(
                    card,
                    text=n.message,
                    font=ctk.CTkFont(family="Consolas", size=9),
                    text_color="#94a3b8",
                    wraplength=310,
                    justify="left"
                )
                msg_lbl.pack(anchor="w", padx=8, pady=(2, 6))

                if n.category == "UPDATE" and n.action_type == "UPDATE_NOW":
                    act_row = ctk.CTkFrame(card, fg_color="transparent")
                    act_row.pack(fill="x", padx=8, pady=(0, 6))

                    def _do_update():
                        self._close_notification_menu()
                        self.open_settings_modal(initial_tab="Updates")

                    def _later(nid=n.id):
                        notification_manager.mark_as_read(nid)
                        self._refresh_notification_badge()
                        self._open_notification_menu()

                    ctk.CTkButton(
                        act_row,
                        text="Update Now",
                        font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
                        fg_color="#0284c7",
                        hover_color="#0369a1",
                        height=22,
                        width=85,
                        command=_do_update
                    ).pack(side="left", padx=(0, 4))

                    ctk.CTkButton(
                        act_row,
                        text="View Details",
                        font=ctk.CTkFont(family="Consolas", size=9),
                        fg_color="#1e293b",
                        hover_color="#334155",
                        text_color="#38bdf8",
                        height=22,
                        width=85,
                        command=lambda: (self._close_notification_menu(), self.open_settings_modal(initial_tab="About"))
                    ).pack(side="left", padx=(0, 4))

                    ctk.CTkButton(
                        act_row,
                        text="Later",
                        font=ctk.CTkFont(family="Consolas", size=9),
                        fg_color="#1e293b",
                        hover_color="#334155",
                        text_color="#94a3b8",
                        height=22,
                        width=55,
                        command=_later
                    ).pack(side="left")

        # Close when clicking outside
        def _on_root_click_notif(event):
            if not self._notification_window or not self._notification_window.winfo_exists():
                return
            wx = self._notification_window.winfo_rootx()
            wy = self._notification_window.winfo_rooty()
            ww = self._notification_window.winfo_width()
            wh = self._notification_window.winfo_height()
            if not (wx <= event.x_root <= wx + ww and wy <= event.y_root <= wy + wh):
                self._close_notification_menu()

        self.bind_all("<Button-1>", _on_root_click_notif, add="+")


    def _select_ai_provider(self, provider_id: str):
        """Handles user selection from the AI Provider Switcher menu."""
        self._close_provider_menu()
        if provider_id == "AUTOMATIC":
            self.agent.router.set_provider_mode("AUTOMATIC")
        else:
            self.agent.router.set_provider_mode("MANUAL", provider=provider_id)

        # Synchronize UI header pills immediately
        self._refresh_ai_provider_button()
        self._refresh_status_pill()

    def _on_ai_provider_switched(self, old_prov: str, new_prov: str):
        """Updates AI provider pill when failover occurs and shows a small status notice."""
        self._refresh_ai_provider_button()
        self._refresh_status_pill()
        self.add_message(f"Failover: Switched from {old_prov} to {new_prov}", sender="assistant", action_tag="FAILOVER", animate=False)

    def _on_camera_state_change(self, state: str):
        self.after(0, lambda: self.update_camera_state(state))

    def update_camera_state(self, state: str):
        """
        Updates camera indicator pill and preview overlay with managed states:
        CAMERA_OFF, CAMERA_STARTING, CAMERA_READY, CAMERA_ACTIVE, VISION_ANALYZING,
        CAMERA_ERROR, CAMERA_NOT_DETECTED, CAMERA_IN_USE
        """
        state_map = {
            "CAMERA_OFF": ("● CAMERA OFF", "#1e293b", "#334155", "#94a3b8"),
            "CAMERA_STARTING": ("● CAMERA STARTING", "#713f12", "#854d0e", "#fde047"),
            "CAMERA_READY": ("● CAMERA READY", "#14532d", "#166534", "#86efac"),
            "CAMERA_ACTIVE": ("● CAMERA ACTIVE", "#059669", "#047857", "#ffffff"),
            "VISION_ANALYZING": ("VISION ● ANALYZING", "#581c87", "#6b21a8", "#e9d5ff"),
            "CAMERA_ERROR": ("⚠️ CAMERA ERROR", "#7f1d1d", "#991b1b", "#fca5a5"),
            "CAMERA_NOT_DETECTED": ("⚠️ NO CAMERA", "#7f1d1d", "#991b1b", "#fca5a5"),
            "CAMERA_IN_USE": ("⚠️ CAMERA IN USE", "#854d0e", "#a16207", "#fef08a"),
        }
        text, bg_col, hov_col, text_col = state_map.get(state, ("● CAMERA OFF", "#1e293b", "#334155", "#94a3b8"))

        if hasattr(self, "btn_camera"):
            self.btn_camera.configure(text=text, fg_color=bg_col, hover_color=hov_col, text_color=text_col)

        if hasattr(self, "status_pill") and state == "VISION_ANALYZING":
            self.status_pill.configure(text="● VISION ANALYZING", fg_color="#7c3aed")

        # Show or hide preview window/frame based on state
        if state == "CAMERA_ACTIVE":
            self.show_camera_preview()
        elif state in ["CAMERA_OFF", "CAMERA_ERROR", "CAMERA_NOT_DETECTED"]:
            self.hide_camera_preview()

    def _on_camera_frame_received(self, pil_img: Image.Image):
        """Streams live frames directly into the floating camera preview widget."""
        self.after(0, lambda: self._update_camera_preview_image(pil_img))

    def show_camera_preview(self):
        """Opens or reveals the unified live camera preview and camera mouse container."""
        if hasattr(self, "camera_preview_win") and self.camera_preview_win is not None and self.camera_preview_win.winfo_exists():
            self.camera_preview_win.deiconify()
            self.camera_preview_win.lift()
            self._update_cam_mouse_panel_state()
            return

        self.camera_preview_win = ctk.CTkToplevel(self)
        self.camera_preview_win.title("V.E.D.A. — Camera & Camera Mouse")
        self.camera_preview_win.geometry("380x480")
        self.camera_preview_win.minsize(360, 420)
        self.camera_preview_win.attributes("-topmost", True)
        self.camera_preview_win.configure(fg_color="#07090e")
        self.camera_preview_win.protocol("WM_DELETE_WINDOW", self.toggle_camera)

        box = ctk.CTkFrame(self.camera_preview_win, fg_color="#0b101b", corner_radius=10, border_width=1, border_color="#059669")
        box.pack(fill="both", expand=True, padx=8, pady=8)

        # Header bar
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(6, 4))
        self.lbl_cam_title = ctk.CTkLabel(head, text="📷 CAMERA [ON]", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#10b981")
        self.lbl_cam_title.pack(side="left")
        
        btn_stop = ctk.CTkButton(head, text="Turn Off", width=65, height=22, font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), fg_color="#7f1d1d", hover_color="#991b1b", command=self.toggle_camera)
        btn_stop.pack(side="right")

        # Orientation Controls Toolbar
        toolbar = ctk.CTkFrame(box, fg_color="#080c14", corner_radius=6)
        toolbar.pack(fill="x", padx=8, pady=(2, 4))

        def _set_mode_normal():
            camera_subsystem.set_orientation(mirror=False, rotation=0)
            self._update_preview_mode_label()

        def _toggle_mirror():
            camera_subsystem.set_orientation(mirror=not camera_subsystem.mirror)
            self._update_preview_mode_label()

        def _rotate_90():
            next_rot = (camera_subsystem.rotation + 90) % 360
            camera_subsystem.set_orientation(rotation=next_rot)
            self._update_preview_mode_label()

        btn_norm = ctk.CTkButton(toolbar, text="Normal", width=55, height=20, font=ctk.CTkFont(family="Consolas", size=10), fg_color="#1e293b", hover_color="#334155", command=_set_mode_normal)
        btn_norm.pack(side="left", padx=2, pady=2)

        btn_mir = ctk.CTkButton(toolbar, text="Mirror", width=50, height=20, font=ctk.CTkFont(family="Consolas", size=10), fg_color="#1e293b", hover_color="#334155", command=_toggle_mirror)
        btn_mir.pack(side="left", padx=2, pady=2)

        btn_rot = ctk.CTkButton(toolbar, text="Rotate 90°", width=65, height=20, font=ctk.CTkFont(family="Consolas", size=10), fg_color="#1e293b", hover_color="#334155", command=_rotate_90)
        btn_rot.pack(side="left", padx=2, pady=2)

        self.lbl_preview_mode = ctk.CTkLabel(toolbar, text="Normal", font=ctk.CTkFont(family="Consolas", size=10), text_color="#38bdf8")
        self.lbl_preview_mode.pack(side="right", padx=6)
        self._update_preview_mode_label()

        # Center Video Canvas
        canvas_card = ctk.CTkFrame(box, fg_color="#05080e", corner_radius=8, border_width=1, border_color="#161f30")
        canvas_card.pack(fill="both", expand=True, padx=8, pady=4)

        self.camera_canvas_label = ctk.CTkLabel(canvas_card, text="Acquiring camera feed...", font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8")
        self.camera_canvas_label.pack(fill="both", expand=True, padx=4, pady=4)

        # Bottom Dedicated Section: Camera Mouse Sub-panel
        cm_panel = ctk.CTkFrame(box, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        cm_panel.pack(fill="x", padx=8, pady=(4, 6))

        # Row 1: Section Header & Mode Toggle Button
        cm_top_row = ctk.CTkFrame(cm_panel, fg_color="transparent")
        cm_top_row.pack(fill="x", padx=8, pady=(6, 4))

        ctk.CTkLabel(cm_top_row, text="✋ CAMERA MOUSE", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#38bdf8").pack(side="left")

        self.btn_panel_cam_mouse = ctk.CTkButton(
            cm_top_row,
            text="CAMERA MOUSE [ OFF ]",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#94a3b8",
            width=150,
            height=24,
            corner_radius=12,
            command=self.toggle_camera_mouse
        )
        self.btn_panel_cam_mouse.pack(side="right")

        # Row 2: Real-time Telemetry Status
        cm_telemetry_row = ctk.CTkFrame(cm_panel, fg_color="#05080e", corner_radius=6)
        cm_telemetry_row.pack(fill="x", padx=8, pady=(2, 4))

        self.lbl_cm_hand = ctk.CTkLabel(cm_telemetry_row, text="HAND: NOT DETECTED", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color="#64748b")
        self.lbl_cm_hand.pack(side="left", padx=6, pady=3)

        self.lbl_cm_gesture = ctk.CTkLabel(cm_telemetry_row, text="GESTURE: NONE", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color="#38bdf8")
        self.lbl_cm_gesture.pack(side="left", padx=6, pady=3)

        self.lbl_cm_tracking = ctk.CTkLabel(cm_telemetry_row, text="TRACKING: OFF", font=ctk.CTkFont(family="Consolas", size=9), text_color="#64748b")
        self.lbl_cm_tracking.pack(side="left", padx=6, pady=3)

        self.lbl_cm_fps = ctk.CTkLabel(cm_telemetry_row, text="FPS: 0", font=ctk.CTkFont(family="Consolas", size=9), text_color="#64748b")
        self.lbl_cm_fps.pack(side="right", padx=6, pady=3)

        # Row 3: CPU Mode & Controls Legend
        cm_legend_row = ctk.CTkFrame(cm_panel, fg_color="transparent")
        cm_legend_row.pack(fill="x", padx=8, pady=(0, 4))

        self.lbl_cm_cpu = ctk.CTkLabel(cm_legend_row, text="CPU MODE: LOW PERFORMANCE (2-CORE)", font=ctk.CTkFont(family="Consolas", size=9), text_color="#475569")
        self.lbl_cm_cpu.pack(side="left")

        ctk.CTkLabel(cm_panel, text="Index=Move • Fist=Click • 2-Fingers=Right-Click • Pinch=Drag • Palm=Pause • ESC=Stop", font=ctk.CTkFont(family="Consolas", size=8), text_color="#64748b").pack(fill="x", padx=6, pady=(0, 4))

        self._update_cam_mouse_panel_state()

    def _update_cam_mouse_panel_state(self):
        """Updates the embedded Camera Mouse panel state and telemetry badges."""
        if not hasattr(self, "btn_panel_cam_mouse") or self.btn_panel_cam_mouse is None:
            return
        try:
            if not self.btn_panel_cam_mouse.winfo_exists():
                return
            cam_active = camera_subsystem.is_streaming
            cm_active = camera_mouse_controller.is_active

            if not cam_active:
                self.btn_panel_cam_mouse.configure(text="CAMERA [OFF]", fg_color="#1e293b", text_color="#64748b", state="disabled")
                if hasattr(self, "lbl_cam_title") and self.lbl_cam_title.winfo_exists():
                    self.lbl_cam_title.configure(text="📷 CAMERA [OFF]", text_color="#64748b")
                if hasattr(self, "lbl_cm_tracking") and self.lbl_cm_tracking.winfo_exists():
                    self.lbl_cm_tracking.configure(text="TRACKING: OFF", text_color="#64748b")
            else:
                self.btn_panel_cam_mouse.configure(state="normal")
                if hasattr(self, "lbl_cam_title") and self.lbl_cam_title.winfo_exists():
                    self.lbl_cam_title.configure(text="📷 CAMERA [ON]", text_color="#10b981")
                if cm_active:
                    self.btn_panel_cam_mouse.configure(text="CAMERA MOUSE [ ON ]", fg_color="#059669", hover_color="#047857", text_color="#ffffff")
                    if hasattr(self, "lbl_cm_tracking") and self.lbl_cm_tracking.winfo_exists():
                        self.lbl_cm_tracking.configure(text="TRACKING: ACTIVE", text_color="#10b981")
                else:
                    self.btn_panel_cam_mouse.configure(text="CAMERA MOUSE [ OFF ]", fg_color="#1e293b", hover_color="#334155", text_color="#94a3b8")
                    if hasattr(self, "lbl_cm_tracking") and self.lbl_cm_tracking.winfo_exists():
                        self.lbl_cm_tracking.configure(text="TRACKING: WAITING", text_color="#eab308")
                    if hasattr(self, "lbl_cm_hand") and self.lbl_cm_hand.winfo_exists():
                        self.lbl_cm_hand.configure(text="HAND: NOT DETECTED", text_color="#64748b")
                    if hasattr(self, "lbl_cm_gesture") and self.lbl_cm_gesture.winfo_exists():
                        self.lbl_cm_gesture.configure(text="GESTURE: NONE", text_color="#64748b")
                    if hasattr(self, "lbl_cm_fps") and self.lbl_cm_fps.winfo_exists():
                        self.lbl_cm_fps.configure(text="FPS: 0")
        except Exception:
            pass

    def _update_preview_mode_label(self):
        if hasattr(self, "lbl_preview_mode") and self.lbl_preview_mode and self.lbl_preview_mode.winfo_exists():
            desc = "Normal"
            if camera_subsystem.mirror and camera_subsystem.rotation:
                desc = f"Mirrored ({camera_subsystem.rotation}°)"
            elif camera_subsystem.mirror:
                desc = "Mirrored"
            elif camera_subsystem.rotation:
                desc = f"{camera_subsystem.rotation}°"
            self.lbl_preview_mode.configure(text=desc)

    def hide_camera_preview(self):
        """Safely hides and closes camera preview window."""
        if hasattr(self, "camera_preview_win") and self.camera_preview_win is not None:
            try:
                if self.camera_preview_win.winfo_exists():
                    self.camera_preview_win.destroy()
            except Exception:
                pass
            self.camera_preview_win = None

    def _update_camera_preview_image(self, pil_img: Image.Image):
        """Displays standard camera frames when Camera Mouse is not streaming overlaid frames."""
        if camera_mouse_controller.is_active:
            return  # The skeleton-annotated frames take precedence
        self._render_canvas_image(pil_img)

    def _render_canvas_image(self, pil_img: Image.Image):
        """Maintains aspect ratio and renders image onto camera canvas."""
        if not hasattr(self, "camera_canvas_label") or self.camera_canvas_label is None:
            return
        try:
            if not self.camera_canvas_label.winfo_exists():
                return
            w, h = pil_img.size
            if w <= 0 or h <= 0:
                return
            target_w = 340
            target_h = int(target_w * (h / w))
            if target_h > 240:
                target_h = 240
                target_w = int(target_h * (w / h))

            display_img = pil_img.resize((target_w, target_h), Image.Resampling.BILINEAR)
            ctk_img = ctk.CTkImage(light_image=display_img, dark_image=display_img, size=(target_w, target_h))
            self.camera_canvas_label.configure(image=ctk_img, text="")
        except Exception:
            pass

    def _handle_emergency_stop(self):
        if camera_mouse_controller.is_active:
            camera_mouse_controller.emergency_stop()
            self._update_cam_mouse_panel_state()
            self.add_message("✋ Camera Mouse: EMERGENCY STOP triggered (ESC pressed). Mouse control released.", sender="assistant", action_tag="EMERGENCY_STOP", animate=False)

    def toggle_camera_mouse(self):
        """Toggles offline camera-based hand tracking mouse control."""
        if camera_mouse_controller.is_active:
            camera_mouse_controller.stop()
            self._update_cam_mouse_panel_state()
            self.add_message("Camera Mouse deactivated.", sender="assistant", animate=False)
        else:
            perms = VedaConfig.get_permissions()
            if not perms.get("camera", False):
                self.add_message("Camera permission required for Camera Mouse. Please enable Camera in Settings -> Permissions.", sender="assistant", action_tag="PERMISSION", animate=False)
                self.open_settings_modal(initial_tab="Permissions")
                return

            # Ensure camera preview / camera feed is active
            if not camera_subsystem.is_streaming:
                started_cam = camera_subsystem.start_preview()
                if not started_cam:
                    self.add_message("Could not activate camera for Camera Mouse.", sender="assistant", animate=False)
                    return

            started = camera_mouse_controller.start()
            if started:
                self.show_camera_preview()
                self._update_cam_mouse_panel_state()
                self.add_message("✋ Camera Mouse ACTIVATED (Offline 2-Core CPU Mode). Point with index finger to move, fist to click, two fingers to right-click, pinch thumb+middle to drag, open palm to pause. Press ESC to stop.", sender="assistant", action_tag="CAM_MOUSE", animate=False)
            else:
                self.add_message("Could not activate Camera Mouse. Check webcam availability.", sender="assistant", animate=False)

    def _on_cam_mouse_state_change(self, state: str):
        self._update_cam_mouse_panel_state()

    def show_cam_mouse_preview(self):
        """Directs to unified Camera & Camera Mouse preview."""
        self.show_camera_preview()

    def hide_cam_mouse_preview(self):
        """Updates panel state when camera mouse stops."""
        self._update_cam_mouse_panel_state()

    def _on_cam_mouse_preview_frame(self, pil_img: Image.Image, gesture: str, hand_detected: bool, fps: float):
        """Receives live frames with hand skeleton overlay and updates panel telemetry."""
        # Update canvas with skeleton overlay frame
        self._render_canvas_image(pil_img)

        try:
            # Update HUD Labels
            if hasattr(self, "lbl_cm_hand") and self.lbl_cm_hand.winfo_exists():
                if hand_detected:
                    self.lbl_cm_hand.configure(text="HAND: DETECTED", text_color="#10b981")
                else:
                    self.lbl_cm_hand.configure(text="HAND: NOT DETECTED", text_color="#64748b")

            if hasattr(self, "lbl_cm_gesture") and self.lbl_cm_gesture.winfo_exists():
                g_col = "#38bdf8"
                if gesture == "CLICK": g_col = "#22c55e"
                elif gesture == "RIGHT_CLICK": g_col = "#ec4899"
                elif gesture == "DRAG": g_col = "#f97316"
                elif gesture == "PAUSED": g_col = "#eab308"
                elif gesture in ["NO_HAND", "NONE"]: g_col = "#64748b"
                self.lbl_cm_gesture.configure(text=f"GESTURE: {gesture}", text_color=g_col)

            if hasattr(self, "lbl_cm_tracking") and self.lbl_cm_tracking.winfo_exists():
                if camera_mouse_controller.is_active:
                    self.lbl_cm_tracking.configure(text="TRACKING: ACTIVE", text_color="#10b981")
                else:
                    self.lbl_cm_tracking.configure(text="TRACKING: WAITING", text_color="#eab308")

            if hasattr(self, "lbl_cm_fps") and self.lbl_cm_fps.winfo_exists():
                self.lbl_cm_fps.configure(text=f"FPS: {fps}")
        except Exception:
            pass

    def toggle_camera(self):
        """Toggles the camera active state and live preview."""
        if camera_subsystem.is_streaming:
            if camera_mouse_controller.is_active:
                camera_mouse_controller.stop()
            camera_subsystem.stop_preview()
            self.add_message("Webcam deactivated.", sender="assistant", animate=False)
        else:
            started = camera_subsystem.start_preview()
            if started:
                self.add_message("Webcam activated with live preview.", sender="assistant", animate=False)
            else:
                self.add_message(f"Could not activate webcam: {camera_subsystem.state}", sender="assistant", animate=False)

    def _start_ambient_glow(self):
        """Dynamic pulsing breathing animation on status pill and border accents."""
        def _glow_tick():
            if not self.winfo_exists():
                return
            self._status_glow_phase = (self._status_glow_phase + 1) % 40
            # Subtle pulsation when listening or thinking
            if self._is_agent_busy:
                alpha = 0.5 + 0.5 * math.sin(self._status_glow_phase * 0.25)
                pulse_col = "#a855f7" if alpha > 0.5 else "#7c3aed"
                self.status_pill.configure(fg_color=pulse_col)
            elif microphone_subsystem.is_listening:
                alpha = 0.5 + 0.5 * math.sin(self._status_glow_phase * 0.3)
                pulse_col = "#ef4444" if alpha > 0.5 else "#b91c1c"
                self.status_pill.configure(fg_color=pulse_col)
            elif tts_engine.is_speaking:
                alpha = 0.5 + 0.5 * math.sin(self._status_glow_phase * 0.25)
                pulse_col = "#10b981" if alpha > 0.5 else "#059669"
                self.status_pill.configure(fg_color=pulse_col)

            self.after(80, _glow_tick)

        self.after(200, _glow_tick)

    def _build_header(self):
        # Outer Glass Container with sleek illuminated border
        self.header = ctk.CTkFrame(
            self,
            fg_color="#0b101b",
            height=66,
            corner_radius=12,
            border_width=1,
            border_color="#1e293b"
        )
        self.header.pack(fill="x", padx=14, pady=(12, 6))
        self.header.pack_propagate(False)

        # Left Branding Group with Glowing Dot
        brand_frame = ctk.CTkFrame(self.header, fg_color="transparent")
        brand_frame.pack(side="left", padx=16, pady=10)

        # Ambient Glowing Core Indicator
        self.core_dot = ctk.CTkLabel(
            brand_frame,
            text="◈",
            font=ctk.CTkFont(family="Consolas", size=18, weight="bold"),
            text_color="#38bdf8"
        )
        self.core_dot.pack(side="left", padx=(0, 6))

        title_lbl = ctk.CTkLabel(
            brand_frame,
            text="V.E.D.A.",
            font=ctk.CTkFont(family="Consolas", size=20, weight="bold"),
            text_color="#38bdf8"
        )
        title_lbl.pack(side="left")

        sub_lbl = ctk.CTkLabel(
            brand_frame,
            text=' "Virtual Executive Desktop Assistant"',
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#64748b"
        )
        sub_lbl.pack(side="left", padx=(4, 0))

        # Right Action Group: Live Screen Toggle, Status Pill, History, Made by Shreyas
        right_frame = ctk.CTkFrame(self.header, fg_color="transparent")
        right_frame.pack(side="right", padx=14, pady=10)

        # AI Provider Indicator Pill (Clickable AI Switcher)
        self.btn_ai_provider = ctk.CTkButton(
            right_frame,
            text="◆ V.E.D.A. • Gemini",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#ffffff",
            fg_color="#0284c7",
            hover=True,
            hover_color="#0369a1",
            cursor="hand2",
            height=30,
            width=165,
            corner_radius=15,
            command=self.toggle_provider_menu
        )
        self.btn_ai_provider.pack(side="left", padx=(0, 6))
        self.tip_ai_provider = CTkToolTip(self.btn_ai_provider, "Click to switch AI provider")

        # Live Screen Privacy Indicator & Toggle Button
        self.btn_live_screen = ctk.CTkButton(
            right_frame,
            text="● SCREEN OFF",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#94a3b8",
            fg_color="#1e293b",
            hover_color="#334155",
            height=30,
            width=116,
            corner_radius=15,
            command=self.toggle_live_screen
        )
        self.btn_live_screen.pack(side="left", padx=(0, 6))

        # Camera Privacy Indicator & Toggle Button
        self.btn_camera = ctk.CTkButton(
            right_frame,
            text="● CAMERA OFF",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#94a3b8",
            fg_color="#1e293b",
            hover_color="#334155",
            height=30,
            width=116,
            corner_radius=15,
            command=self.toggle_camera
        )
        self.btn_camera.pack(side="left", padx=(0, 6))

        # Dynamic Status Pill (Clickable Real-Time Reload)
        self.status_pill = ctk.CTkButton(
            right_frame,
            text="Checking connection...",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color="#ffffff",
            fg_color="#475569",
            hover=True,
            hover_color="#334155",
            cursor="hand2",
            height=30,
            width=200,
            corner_radius=15,
            command=self.trigger_health_refresh
        )
        self.status_pill.pack(side="left", padx=(0, 6))
        self.tip_status_pill = CTkToolTip(self.status_pill, "Click to refresh Internet and AI provider status")

        # In-App Notification Bell Button with Unread Badge
        self.btn_notifications = ctk.CTkButton(
            right_frame,
            text="🔔 0",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#94a3b8",
            fg_color="#0f172a",
            hover_color="#1e293b",
            height=30,
            width=54,
            corner_radius=15,
            command=self.toggle_notification_menu
        )
        self.btn_notifications.pack(side="left", padx=(0, 6))
        self.tip_notifications = CTkToolTip(self.btn_notifications, "System & Update Notifications")

        # Consolidated Settings & Configuration Center Button
        self.btn_settings = ctk.CTkButton(
            right_frame,
            text="⚙ Settings",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#38bdf8",
            fg_color="#0f172a",
            hover_color="#1e293b",
            height=30,
            width=96,
            corner_radius=15,
            command=self.open_settings_modal
        )
        self.btn_settings.pack(side="left")
        self.tip_settings = CTkToolTip(self.btn_settings, "Open unified Settings, Permissions, Automations & Voice Center")

    def _build_chat_stream(self):
        self.chat_container = ctk.CTkFrame(
            self,
            fg_color="#080c14",
            corner_radius=12,
            border_width=1,
            border_color="#161f30"
        )
        self.chat_container.pack(fill="both", expand=True, padx=14, pady=6)

        self.chat_frame = ctk.CTkScrollableFrame(self.chat_container, fg_color="transparent")
        self.chat_frame.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_input_dock(self):
        dock = ctk.CTkFrame(
            self,
            fg_color="#0b101b",
            corner_radius=12,
            border_width=1,
            border_color="#1e293b",
            height=66
        )
        dock.pack(fill="x", padx=14, pady=(6, 14))
        dock.pack_propagate(False)

        dock_content = ctk.CTkFrame(dock, fg_color="transparent")
        dock_content.pack(fill="both", expand=True, padx=10, pady=10)

        # Mode Indicator / Desktop Mode Toggle Shortcut
        self.btn_mode = ctk.CTkButton(
            dock_content,
            text="Desktop Mode" if not self.is_desktop_mode else "Main Window",
            width=100,
            height=40,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#38bdf8",
            corner_radius=8,
            command=self.toggle_desktop_mode
        )
        self.btn_mode.pack(side="left", padx=(0, 8))

        # Real-time Audio Waveform Visualizer
        self.waveform = AudioWaveformCanvas(dock_content, width=80, height=36)
        self.waveform.pack(side="left", padx=(0, 8))

        self.input_field = ctk.CTkEntry(
            dock_content,
            placeholder_text="Talk to V.E.D.A. naturally in English, Hindi, or Hinglish...",
            placeholder_text_color="#475569",
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color="#05080e",
            border_color="#1e293b",
            border_width=1,
            text_color="#f8fafc",
            height=40
        )
        self.input_field.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.input_field.bind("<Return>", lambda e: self.send_request())

        self.btn_send = ctk.CTkButton(
            dock_content,
            text="Send",
            width=68,
            height=40,
            command=self.send_request,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            corner_radius=8
        )
        self.btn_send.pack(side="left", padx=(0, 6))

        # Microphone Mode Selector: "🎙 Always On" vs "🎙 Mic Toggle"
        mode_label = "🎙 Always On" if self.mic_mode == "always_on" else "🎙 Mic Toggle"
        self.btn_mic_mode = ctk.CTkButton(
            dock_content,
            text=mode_label,
            width=118,
            height=40,
            command=self.toggle_mic_mode,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#38bdf8",
            corner_radius=8
        )
        self.btn_mic_mode.pack(side="left", padx=(0, 6))

        # Dedicated 7-State Hearing & Microphone Action Indicator
        self.btn_mic = ctk.CTkButton(
            dock_content,
            text="🔴 MIC OFF",
            width=135,
            height=40,
            command=self.toggle_mic_action,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#94a3b8",
            corner_radius=8
        )
        self.btn_mic.pack(side="left", padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            dock_content,
            text="Stop",
            width=62,
            height=40,
            command=self.abort_request,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            fg_color="#991b1b",
            hover_color="#7f1d1d",
            corner_radius=8
        )
        self.btn_stop.pack(side="right")

    def _load_persisted_history(self):
        history = VedaConfig.load_history()
        if history:
            for item in history:
                self.render_message_bubble(
                    text=item.get("text", ""),
                    sender=item.get("sender", "assistant"),
                    action_tag=item.get("action_tag"),
                    animate=False
                )
        else:
            welcome_text = (
                f"Hello! I am V.E.D.A. (Virtual Executive Desktop Assistant), created by Shreyas.\n\n"
                f"Ready for natural interaction and computer tasks:\n"
                f"• 'Open Microsoft Edge'\n"
                f"• 'Notepad khol aur Hello from VEDA likh'\n"
                f"• 'Who created you?'\n"
                f"• 'Take a screenshot'\n"
                f"• 'Check my Downloads folder'\n\n"
                f"• Download & Updates Link:\n  https://drive.google.com/drive/folders/1nqnjiPY1IRwolYZNuxkpFuP_VHTm7Ja0?usp=drive_link\n\n"
                f"Running autonomously with real Windows capabilities."
            )
            self.add_message(welcome_text, sender="assistant", animate=False)

    def add_message(self, text: str, sender: str = "assistant", action_tag: Optional[str] = None, animate: bool = True):
        VedaConfig.append_history(sender, text, action_tag or "")
        self.render_message_bubble(text, sender, action_tag, animate=animate)

    def render_message_bubble(self, text: str, sender: str = "assistant", action_tag: Optional[str] = None, animate: bool = False):
        is_user = sender == "user"
        frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        frame.pack(fill="x", pady=5)

        container = ctk.CTkFrame(frame, fg_color="transparent")
        container.pack(side="right" if is_user else "left", padx=10)

        if action_tag and not is_user:
            pill = ctk.CTkLabel(
                container,
                text=f"⚡ {action_tag}",
                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
                text_color="#38bdf8",
                fg_color="#0f172a",
                corner_radius=6,
                padx=8,
                pady=2
            )
            pill.pack(anchor="w", pady=(0, 3))

        bubble_bg = "#0369a1" if is_user else "#0f172a"
        border_col = "#0284c7" if is_user else "#1e293b"

        bubble = ctk.CTkLabel(
            container,
            text="",
            fg_color=bubble_bg,
            text_color="#f8fafc",
            corner_radius=12,
            wraplength=560,
            justify="left",
            font=ctk.CTkFont(family="Consolas", size=12),
            padx=14,
            pady=10
        )
        bubble.pack(side="right" if is_user else "left")

        # Smooth Typewriter Streaming Animation for live assistant responses
        if animate and not is_user and len(text) > 5:
            def _stream_typewriter(idx=0, chunk_size=4):
                if not bubble.winfo_exists():
                    return
                current = text[:idx]
                bubble.configure(text=current)
                self.chat_frame._parent_canvas.yview_moveto(1.0)
                if idx < len(text):
                    self.after(15, lambda: _stream_typewriter(idx + chunk_size, chunk_size))
                else:
                    bubble.configure(text=text)

            _stream_typewriter()
        else:
            bubble.configure(text=text)
            self.after(40, lambda: self.chat_frame._parent_canvas.yview_moveto(1.0))

    def update_status_safe(self, text: str, color: str = "#0284c7"):
        self.after(0, lambda: self._update_status_impl(text, color))

    def _update_status_impl(self, text: str, color: str):
        self.status_pill.configure(text=f"● {text}", fg_color=color)
        if hasattr(self, "waveform"):
            if "HEAR" in text or "LISTEN" in text:
                self.waveform.set_level(0.75, "#ef4444")
            elif "THINK" in text:
                self.waveform.set_level(0.5, "#a855f7")
            elif "SPEAK" in text:
                self.waveform.set_level(0.8, "#10b981")
            elif "ONLINE" in text or "READY" in text:
                self.waveform.set_level(0.05, "#38bdf8")

    def log_action_safe(self, action_text: str):
        self.after(0, lambda: self.add_message(action_text, sender="assistant", action_tag="ACTION EXECUTED", animate=False))

    def send_request(self, language_mode: Optional[str] = None):
        if self.is_paused:
            self.add_message("V.E.D.A. is currently PAUSED. Resume via the system tray or settings.", sender="assistant", animate=False)
            return

        user_text = self.input_field.get().strip()
        if not user_text:
            return

        self.input_field.delete(0, "end")
        
        # Detect language if not provided
        detected_lang = language_mode or detect_language(user_text)
        action_tag = f"VOICE [{detected_lang}]" if language_mode else None
        self.add_message(user_text, sender="user", action_tag=action_tag, animate=False)

        self.worker_thread = threading.Thread(
            target=self._run_agent_thread,
            args=(user_text, detected_lang),
            daemon=True
        )
        self.worker_thread.start()

    def abort_request(self):
        tts_engine.stop()
        microphone_subsystem.stop_listening()
        self._is_agent_busy = False
        self.update_status_safe("ONLINE", "#0284c7")
        self.add_message("[Action halted by user]", sender="assistant", animate=False)

    def _run_agent_thread(self, user_text: str, language_mode: Optional[str] = None):
        self._is_agent_busy = True
        self.update_status_safe("THINKING...", "#8b5cf6")

        # Create assistant bubble container early for real-time streaming tokens
        bubble_ref = {"widget": None, "accumulated": ""}

        def _init_bubble():
            is_user = False
            row = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
            row.pack(fill="x", pady=5)
            bubble_bg = "#0f172a"
            container = ctk.CTkFrame(row, fg_color=bubble_bg, corner_radius=12, border_width=1, border_color="#1e293b")
            container.pack(side="left")
            head_row = ctk.CTkFrame(container, fg_color="transparent")
            head_row.pack(fill="x", padx=12, pady=(6, 2))
            ctk.CTkLabel(head_row, text="◈ V.E.D.A.", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color="#38bdf8").pack(side="left")
            b_label = ctk.CTkLabel(
                container,
                text="",
                fg_color=bubble_bg,
                text_color="#f8fafc",
                corner_radius=12,
                wraplength=560,
                justify="left",
                font=ctk.CTkFont(family="Consolas", size=12),
                padx=14,
                pady=10
            )
            b_label.pack(side="left")
            bubble_ref["widget"] = b_label

        self.after(0, _init_bubble)

        # Sentence chunker for immediate streaming TTS
        sentence_buffer = ""
        spoken_sentences = []

        def _on_chunk_received(chunk: str):
            nonlocal sentence_buffer
            bubble_ref["accumulated"] += chunk
            # Stream token to UI immediately
            if bubble_ref["widget"] and bubble_ref["widget"].winfo_exists():
                self.after(0, lambda t=bubble_ref["accumulated"]: (
                    bubble_ref["widget"].configure(text=t),
                    self.chat_frame._parent_canvas.yview_moveto(1.0)
                ))

            # Check for complete speakable phrase/sentence
            sentence_buffer += chunk
            term_match = re.search(r"([.!?\n]+)", sentence_buffer)
            if term_match:
                end_idx = term_match.end()
                phrase = sentence_buffer[:end_idx].strip()
                sentence_buffer = sentence_buffer[end_idx:]
                if phrase and len(phrase) > 3:
                    spoken_sentences.append(phrase)
                    eff_lang = language_mode or detect_language(phrase)
                    tts_engine.speak(phrase, language_mode=eff_lang)

        try:
            full_reply = self.agent.send_message_stream(
                user_text,
                language_mode=language_mode,
                on_chunk=_on_chunk_received
            )
            # Final remaining phrase
            if sentence_buffer.strip():
                rem_phrase = sentence_buffer.strip()
                eff_lang = language_mode or detect_language(rem_phrase)
                if rem_phrase not in spoken_sentences:
                    spoken_sentences.append(rem_phrase)
                    tts_engine.speak(rem_phrase, language_mode=eff_lang)
        finally:
            self._is_agent_busy = False
            self.after(2000, lambda: (self._refresh_status_pill(), self._refresh_ai_provider_button()))

    # ==========================================
    # SYSTEM TRAY & BACKGROUND PERSISTENCE
    # ==========================================
    def _create_tray_image(self):
        # 64x64 sleek cyan logo
        img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((4, 4, 60, 60), fill="#07090e", outline="#38bdf8", width=4)
        draw.text((14, 18), "V", fill="#38bdf8")
        return img

    def _init_system_tray(self):
        tray_menu = pystray.Menu(
            pystray.MenuItem("Open V.E.D.A.", self.show_window, default=True),
            pystray.MenuItem("⚡ Reload V.E.D.A. (Apply Changes)", lambda icon, item: self.restart_veda()),
            pystray.MenuItem("Live Screen Mode", pystray.Menu(
                pystray.MenuItem("Live Screen OFF", lambda: self.set_live_screen_mode("OFF")),
                pystray.MenuItem("Live Screen ON", lambda: self.set_live_screen_mode("LIVE")),
                pystray.MenuItem("Focus Active Window", lambda: self.set_live_screen_mode("FOCUS_WINDOW")),
            )),
            pystray.MenuItem("Toggle Webcam Preview", lambda: self.after(0, self.toggle_camera)),
            pystray.MenuItem("Pause", self.pause_veda, checked=lambda item: self.is_paused),
            pystray.MenuItem("Resume", self.resume_veda, visible=lambda item: self.is_paused),
            pystray.MenuItem("Desktop Mode", self.toggle_desktop_mode, checked=lambda item: self.is_desktop_mode),
            pystray.MenuItem("Settings", lambda icon, item: self.open_settings_modal()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit V.E.D.A.", self.exit_app)
        )
        self.tray_icon = pystray.Icon("VEDA", self._create_tray_image(), "V.E.D.A. Assistant", tray_menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def toggle_live_screen(self):
        """Cycles through Live Screen states: OFF -> LIVE -> FOCUS_WINDOW -> OFF."""
        current = live_screen_manager.get_mode()
        if current == "OFF":
            next_mode = "LIVE"
        elif current == "LIVE":
            next_mode = "FOCUS_WINDOW"
        else:
            next_mode = "OFF"
        self.set_live_screen_mode(next_mode)

    def set_live_screen_mode(self, mode: str):
        self.after(0, lambda: self._set_live_screen_mode_impl(mode))

    def _set_live_screen_mode_impl(self, mode: str):
        clean_mode = mode.upper().strip()
        live_screen_manager.set_mode(clean_mode)

        if clean_mode == "LIVE":
            self.btn_live_screen.configure(
                text="● LIVE SCREEN ON",
                fg_color="#059669",
                hover_color="#047857",
                text_color="#ffffff"
            )
            self.add_message("Live Screen observation enabled (full screen, adaptive perception).", sender="assistant", animate=False)
        elif clean_mode == "FOCUS_WINDOW":
            self.btn_live_screen.configure(
                text="● FOCUS WINDOW",
                fg_color="#7c3aed",
                hover_color="#6d28d9",
                text_color="#ffffff"
            )
            self.add_message("Live Screen focused on active window only.", sender="assistant", animate=False)
        else:
            self.btn_live_screen.configure(
                text="● LIVE SCREEN OFF",
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#94a3b8"
            )
            self.add_message("Live Screen observation disabled.", sender="assistant", animate=False)

    def on_close_window(self):
        """Minimize to system tray rather than terminating when background mode is active."""
        self.withdraw()

    def show_window(self, icon=None, item=None):
        self.after(0, self._restore_window)

    def _restore_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def pause_veda(self, icon=None, item=None):
        self.is_paused = True
        self.update_status_safe("PAUSED", "#f59e0b")

    def resume_veda(self, icon=None, item=None):
        self.is_paused = False
        self.update_status_safe("ONLINE", "#0284c7")

    def exit_app(self, icon=None, item=None):
        safely_teardown_all_subsystems()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.quit()
        sys.exit(0)

    def restart_veda(self, icon=None, item=None):
        """Force reloads / restarts V.E.D.A. in-place to apply all code and configuration changes immediately."""
        import subprocess
        safely_teardown_all_subsystems()
        try:
            if self.tray_icon:
                self.tray_icon.stop()
            self.quit()
        except Exception:
            pass

        # Spawn clean new instance with identical arguments
        python_exe = sys.executable
        script_args = [python_exe] + sys.argv
        subprocess.Popen(script_args, cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        sys.exit(0)

    # ==========================================
    # DESKTOP MODE (OVERLAY HUD)
    # ==========================================
    def toggle_desktop_mode(self, icon=None, item=None):
        self.after(0, self._toggle_desktop_mode_impl)

    def _toggle_desktop_mode_impl(self):
        self.is_desktop_mode = not self.is_desktop_mode
        VedaConfig.update_setting("desktop_mode", self.is_desktop_mode)

        if self.is_desktop_mode:
            # HUD Overlay: Frameless, Topmost, Glass style
            self.overrideredirect(True)
            self.attributes("-topmost", True)
            self.attributes("-alpha", 0.92)
            saved_geom = self.settings.get("desktop_geometry", "380x560+100+100")
            self.geometry(saved_geom)
            self.btn_mode.configure(text="Main Window")
            # Bind dragging
            self.header.bind("<Button-1>", self._start_drag)
            self.header.bind("<B1-Motion>", self._do_drag)
        else:
            # Restore standard window
            self.overrideredirect(False)
            self.attributes("-topmost", False)
            self.attributes("-alpha", 1.0)
            self.geometry("780x680")
            self.btn_mode.configure(text="Desktop Mode")
            self.header.unbind("<Button-1>")
            self.header.unbind("<B1-Motion>")

    def _start_drag(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _do_drag(self, event):
        x = self.winfo_x() + (event.x - self._drag_start_x)
        y = self.winfo_y() + (event.y - self._drag_start_y)
        self.geometry(f"+{x}+{y}")
        VedaConfig.update_setting("desktop_geometry", f"{self.winfo_width()}x{self.winfo_height()}+{x}+{y}")

    # ==========================================
    # CONVERSATION HISTORY MODAL
    # ==========================================
    def open_history_modal(self):
        """Unified navigation: routes directly into the History tab of Settings."""
        self.open_settings_modal(initial_tab="History")

    def _clear_history(self, modal):
        VedaConfig.save_history([])
        for widget in self.chat_frame.winfo_children():
            widget.destroy()
        modal.destroy()
        self.add_message("Conversation history cleared.", sender="assistant", animate=False)

    # ==========================================
    # KOKORO TTS DIAGNOSTICS MODAL
    # ==========================================
    def open_api_diagnostics_dialog(self, parent_window=None):
        """
        Opens a dedicated, professional Kokoro Local TTS Diagnostics modal.
        Displays:
        - Engine: Kokoro ONNX
        - Status: OFFLINE READY / READY / NOT INSTALLED / ERROR
        - Model file & path
        - Voice weight binary & path
        - Execution device & CPU thread allocation
        - Selected voice & speed
        - Output audio device
        - Last synthesis latency & audio duration
        - Zero API key guarantee notice
        """
        parent = parent_window if parent_window and parent_window.winfo_exists() else self
        diag_win = ctk.CTkToplevel(parent)
        diag_win.title("Kokoro TTS — Local Engine Diagnostics")
        diag_win.geometry("640x580")
        diag_win.minsize(580, 500)
        diag_win.configure(fg_color="#07090e")
        diag_win.attributes("-topmost", True)

        root_box = ctk.CTkFrame(diag_win, fg_color="#07090e")
        root_box.pack(fill="both", expand=True, padx=14, pady=14)

        # Header bar
        header_bar = ctk.CTkFrame(root_box, fg_color="#0b101b", height=50, corner_radius=8, border_width=1, border_color="#1e293b")
        header_bar.pack(fill="x", pady=(0, 10))
        header_bar.pack_propagate(False)

        ctk.CTkLabel(
            header_bar,
            text="🎙️ KOKORO LOCAL TTS DIAGNOSTICS",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            text_color="#38bdf8"
        ).pack(side="left", padx=14)

        ctk.CTkButton(
            header_bar,
            text="✕ Close",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#94a3b8",
            width=65,
            height=28,
            command=diag_win.destroy
        ).pack(side="right", padx=12)

        scroll_area = ctk.CTkScrollableFrame(root_box, fg_color="transparent")
        scroll_area.pack(fill="both", expand=True, pady=(0, 10))

        # Main Info Card
        card_info = ctk.CTkFrame(scroll_area, fg_color="#0b101b", corner_radius=8, border_width=1, border_color="#1e293b")
        card_info.pack(fill="x", pady=4)

        info_box = ctk.CTkFrame(card_info, fg_color="#05080e", corner_radius=6, border_width=1, border_color="#161f30")
        info_box.pack(fill="both", expand=True, padx=12, pady=12)

        lbl_text = ctk.CTkLabel(
            info_box,
            text="Loading diagnostics...",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#e2e8f0",
            justify="left"
        )
        lbl_text.pack(anchor="w", padx=12, pady=10)

        # Alert / Explanation Card
        card_notice = ctk.CTkFrame(scroll_area, fg_color="#0b101b", corner_radius=8, border_width=1, border_color="#1e293b")
        card_notice.pack(fill="x", pady=4)
        lbl_notice = ctk.CTkLabel(
            card_notice,
            text="",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#94a3b8",
            justify="left",
            wraplength=560
        )
        lbl_notice.pack(anchor="w", padx=12, pady=10)

        def _update_view():
            data = tts_engine.get_diagnostics()
            st = data.get("status", "NOT INITIALIZED")
            inst_str = "Installed" if data.get("is_installed") else "Not Installed"

            details = (
                f"Kokoro TTS Local Engine Diagnostics\n"
                f"─────────────────────────────────────────────────────────────\n"
                f"Engine Architecture  : Kokoro ONNX (Local Inference)\n"
                f"Status               : {st}\n"
                f"Model Installation   : {inst_str}\n"
                f"Model Path           : {data.get('model_path')}\n"
                f"Inference Device     : {data.get('device')} Mode\n"
                f"Output Audio Device  : {data.get('output_device')}\n"
                f"Selected Voice       : {data.get('voice')}\n"
                f"Speech Speed         : {data.get('speed')}x\n"
                f"Available Voices     : {len(data.get('available_voices', []))} voices ready\n\n"
                f"Performance & Synthesis\n"
                f"─────────────────────────────────────────────────────────────\n"
                f"Last Latency         : {data.get('last_latency_ms') or '--'} ms\n"
                f"Last Audio Duration  : {data.get('last_audio_duration_sec') or '--'} sec\n"
                f"Last Error Detail    : {data.get('last_error') or 'None'}\n"
                f"Storage / Cache      : RAM WAV Stream (Zero disk writes)"
            )
            lbl_text.configure(text=details)

            if "OFFLINE READY" in st or "READY" in st:
                lbl_notice.configure(
                    text="✓ Kokoro TTS is fully operational. Runs 100% locally on your computer with zero internet requirement.",
                    text_color="#34d399"
                )
            elif "NOT INSTALLED" in st:
                lbl_notice.configure(
                    text="ℹ Kokoro model assets are not installed yet. Click [Install / Repair Model] in Voice Settings.",
                    text_color="#eab308"
                )
            else:
                lbl_notice.configure(
                    text=f"Status: {st}. Details: {data.get('last_error')}",
                    text_color="#f87171"
                )

        _update_view()

        # Action Buttons Row
        action_bar = ctk.CTkFrame(root_box, fg_color="#0b101b", height=46, corner_radius=8, border_width=1, border_color="#1e293b")
        action_bar.pack(fill="x")

        lbl_action_msg = ctk.CTkLabel(action_bar, text="", font=ctk.CTkFont(family="Consolas", size=10), text_color="#38bdf8")
        lbl_action_msg.pack(side="left", padx=12)

        def _on_test_kokoro():
            lbl_action_msg.configure(text="Synthesizing test speech with Kokoro...", text_color="#38bdf8")
            def _w():
                ok, msg = tts_engine.test_voice("english")
                def _done():
                    if not diag_win.winfo_exists():
                        return
                    _update_view()
                    if ok:
                        lbl_action_msg.configure(text=f"✓ Real playback succeeded", text_color="#10b981")
                    else:
                        lbl_action_msg.configure(text=f"✕ Test failed: {msg[:40]}", text_color="#ef4444")
                diag_win.after(0, _done)
            threading.Thread(target=_w, daemon=True).start()

        def _on_copy_diagnostics():
            data = tts_engine.get_diagnostics()
            text_to_copy = (
                f"Kokoro TTS Diagnostics Export\n"
                f"Engine: Kokoro ONNX Local\n"
                f"Status: {data.get('status')}\n"
                f"Installed: {data.get('is_installed')}\n"
                f"Model Path: {data.get('model_path')}\n"
                f"Voice: {data.get('voice')}\n"
                f"Speed: {data.get('speed')}\n"
                f"Device: {data.get('device')}\n"
                f"Output Device: {data.get('output_device')}\n"
                f"Last Latency: {data.get('last_latency_ms')} ms\n"
                f"Last Duration: {data.get('last_audio_duration_sec')} s\n"
                f"Last Error: {data.get('last_error')}\n"
            )
            try:
                diag_win.clipboard_clear()
                diag_win.clipboard_append(text_to_copy)
                lbl_action_msg.configure(text="✓ Diagnostics copied to clipboard", text_color="#10b981")
            except Exception as e:
                lbl_action_msg.configure(text=f"Copy failed: {e}", text_color="#ef4444")

        ctk.CTkButton(
            action_bar,
            text="🗣 Test Kokoro",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            width=110,
            height=28,
            command=_on_test_kokoro
        ).pack(side="right", padx=6, pady=8)

        ctk.CTkButton(
            action_bar,
            text="📋 Copy Diagnostics",
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#94a3b8",
            width=130,
            height=28,
            command=_on_copy_diagnostics
        ).pack(side="right", padx=4, pady=8)

    # ==========================================
    # UPDATE READY RESTART PROMPT MODAL
    # ==========================================
    def prompt_restart_modal(self, new_version: str):
        """Displays modal asking user whether to Restart & Update or postpone (Later)."""
        prompt_win = ctk.CTkToplevel(self)
        prompt_win.title("V.E.D.A. — Update Ready")
        prompt_win.geometry("440x250")
        prompt_win.resizable(False, False)
        prompt_win.configure(fg_color="#07090e")
        prompt_win.attributes("-topmost", True)

        try:
            # Center modal relative to main app
            self.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - 220
            y = self.winfo_y() + (self.winfo_height() // 2) - 125
            prompt_win.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        box = ctk.CTkFrame(prompt_win, fg_color="#0b101b", corner_radius=10, border_width=1, border_color="#1e293b")
        box.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(
            box,
            text="🚀 V.E.D.A. Update Ready",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            text_color="#38bdf8"
        ).pack(anchor="w", padx=16, pady=(14, 6))

        msg = (
            f"V.E.D.A. version {new_version} has been downloaded and verified.\n\n"
            f"Would you like to restart V.E.D.A. now to apply the update?\n"
            f"All your settings and data will remain intact."
        )
        ctk.CTkLabel(
            box,
            text=msg,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#cbd5e1",
            justify="left",
            wraplength=380
        ).pack(anchor="w", padx=16, pady=(0, 14))

        btn_row = ctk.CTkFrame(box, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(4, 12))

        def _on_later():
            production_updater.postpone_update(new_version)
            prompt_win.destroy()

        def _on_restart():
            prompt_win.destroy()
            production_updater.apply_update_and_restart()

        ctk.CTkButton(
            btn_row,
            text="Later",
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#94a3b8",
            width=100,
            height=32,
            command=_on_later
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row,
            text="⚡ Restart & Update",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            width=160,
            height=32,
            command=_on_restart
        ).pack(side="right")

    # ==========================================
    # SETTINGS MODAL (Start with Windows & Overlay)
    # ==========================================
    def open_settings_modal(self, icon=None, item=None, initial_tab=None):
        self.after(0, lambda: self._open_settings_modal_impl(initial_tab))

    def _open_settings_modal_impl(self, initial_tab=None):
        """
        Unified, single-instance, constrained, and scrollable Settings & Configuration Center for V.E.D.A.
        Consolidates:
        - General Preferences & Autostart
        - AI Provider & Router Diagnostics (2-tier Gemini -> Offline AI)
        - Neural Voice (Kokoro TTS Local Engine, voice selection, speed, diagnostics, and test)
        - Hardware Subsystems (Audio outputs, monitors, camera preview & orientation, mic mode)
        - Permissions Dashboard (Independently toggled capabilities)
        - Natural-Language Automations (Active rules cards, live Windows state, Add/Delete/Test)
        - Conversation History & Clearing
        - About V.E.D.A.
        """
        # Guard: Single-Window Guarantee
        if hasattr(self, "_settings_window") and self._settings_window is not None:
            try:
                if self._settings_window.winfo_exists():
                    self._settings_window.deiconify()
                    self._settings_window.lift()
                    self._settings_window.focus_force()
                    if initial_tab and hasattr(self._settings_window, "_switch_tab"):
                        self._settings_window._switch_tab(initial_tab)
                    return
            except Exception:
                pass

        settings_win = ctk.CTkToplevel(self)
        self._settings_window = settings_win
        settings_win.title("V.E.D.A. — Configuration & Settings Center")
        settings_win.geometry("820x750")
        settings_win.minsize(640, 480)
        settings_win.configure(fg_color="#07090e")
        settings_win.attributes("-topmost", True)

        def _on_settings_close():
            self._settings_window = None
            try:
                settings_win.destroy()
            except Exception:
                pass

        settings_win.protocol("WM_DELETE_WINDOW", _on_settings_close)

        # Root Outer Container
        root_box = ctk.CTkFrame(settings_win, fg_color="#07090e")
        root_box.pack(fill="both", expand=True, padx=12, pady=12)

        # Top Header Bar
        header_bar = ctk.CTkFrame(root_box, fg_color="#0b101b", height=54, corner_radius=10, border_width=1, border_color="#1e293b")
        header_bar.pack(fill="x", padx=4, pady=(0, 10))
        header_bar.pack_propagate(False)

        title_lbl = ctk.CTkLabel(
            header_bar,
            text="⚙ V.E.D.A. SETTINGS & CONFIGURATION",
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            text_color="#38bdf8"
        )
        title_lbl.pack(side="left", padx=16)

        btn_top_close = ctk.CTkButton(
            header_bar,
            text="✕ Close",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#94a3b8",
            width=70,
            height=28,
            corner_radius=6,
            command=_on_settings_close
        )
        btn_top_close.pack(side="right", padx=14)

        # Main Body: Navigation Sidebar + Content Area
        body_frame = ctk.CTkFrame(root_box, fg_color="transparent")
        body_frame.pack(fill="both", expand=True, padx=2, pady=(0, 6))

        # Tab configuration list
        tab_names = [
            ("General", "⚙️ General"),
            ("Updates", "📦 Updates"),
            ("Notifications", "🔔 Notifications"),
            ("AI Provider", "🧠 AI Provider"),
            ("Voice", "🎙️ Voice (Kokoro TTS)"),
            ("Hardware", "💻 Hardware"),
            ("Permissions", "🔒 Permissions"),
            ("Automations", "⚡ Automations"),
            ("History", "📜 History"),
            ("About", "◈ About")
        ]

        # Tab Navigation Strip (Segmented buttons container)
        # Tab Navigation Strip (Segmented buttons container with smooth horizontal scroll on narrow viewports)
        nav_bar_container = ctk.CTkFrame(body_frame, fg_color="#0b101b", height=44, corner_radius=8, border_width=1, border_color="#1e293b")
        nav_bar_container.pack(fill="x", pady=(0, 8))
        nav_bar_container.pack_propagate(False)

        nav_canvas = tk.Canvas(nav_bar_container, bg="#0b101b", highlightthickness=0, bd=0, height=38)
        nav_canvas.pack(fill="both", expand=True, padx=4, pady=3)

        nav_inner = ctk.CTkFrame(nav_canvas, fg_color="transparent")
        nav_window_id = nav_canvas.create_window((0, 0), window=nav_inner, anchor="nw")

        def _update_nav_scroll_region(event=None):
            nav_canvas.configure(scrollregion=nav_canvas.bbox("all"))

        nav_inner.bind("<Configure>", _update_nav_scroll_region)
        nav_canvas.bind("<Configure>", lambda e: nav_canvas.itemconfig(nav_window_id, height=e.height))

        def _on_nav_wheel(event):
            if nav_inner.winfo_reqwidth() > nav_canvas.winfo_width():
                delta = event.delta if event.delta else (-120 if event.num == 5 else 120)
                nav_canvas.xview_scroll(-1 if delta > 0 else 1, "units")
                return "break"

        nav_canvas.bind("<MouseWheel>", _on_nav_wheel)
        nav_inner.bind("<MouseWheel>", _on_nav_wheel)

        # Content frame host
        content_host = ctk.CTkFrame(body_frame, fg_color="#0b101b", corner_radius=10, border_width=1, border_color="#1e293b")
        content_host.pack(fill="both", expand=True)

        tab_frames = {}
        tab_buttons = {}
        active_tab_ref = {"id": "General", "frame": None}

        # Pre-create dedicated scrollable frame for each tab with customized futuristic scrollbar
        for tab_id, _ in tab_names:
            sf = ctk.CTkScrollableFrame(
                content_host,
                fg_color="transparent",
                scrollbar_fg_color="#080c14",
                scrollbar_button_color="#0284c7",
                scrollbar_button_hover_color="#38bdf8"
            )
            try:
                sf._scrollbar.configure(width=8)
            except Exception:
                pass
            tab_frames[tab_id] = sf

        def switch_to_tab(selected_id):
            # Normalize target tab ID
            matched_id = "General"
            for tid, _ in tab_names:
                if tid.lower() == selected_id.lower() or selected_id.lower() in tid.lower():
                    matched_id = tid
                    break

            active_tab_ref["id"] = matched_id
            active_tab_ref["frame"] = tab_frames.get(matched_id)

            for tid, frame in tab_frames.items():
                if tid == matched_id:
                    frame.pack(fill="both", expand=True, padx=8, pady=8)
                else:
                    frame.pack_forget()

            for tid, btn in tab_buttons.items():
                if tid == matched_id:
                    btn.configure(fg_color="#0284c7", text_color="#ffffff")
                else:
                    btn.configure(fg_color="#1e293b", text_color="#94a3b8")

            # Scroll selected tab button into view if navigation bar overflows
            btn_target = tab_buttons.get(matched_id)
            if btn_target and nav_inner.winfo_reqwidth() > nav_canvas.winfo_width():
                try:
                    btn_x = btn_target.winfo_x()
                    btn_w = btn_target.winfo_width()
                    total_w = nav_inner.winfo_reqwidth()
                    if total_w > 0:
                        nav_canvas.xview_moveto(max(0.0, min(1.0, (btn_x - 10) / total_w)))
                except Exception:
                    pass

        settings_win._switch_tab = switch_to_tab

        # Keyboard Navigation Handlers for Settings Content Area
        def _on_key_page_up(e):
            if isinstance(e.widget, (tk.Entry, tk.Text, ctk.CTkEntry)):
                return
            curr_sf = active_tab_ref.get("frame")
            if curr_sf and hasattr(curr_sf, "_parent_canvas"):
                curr_sf._parent_canvas.yview_scroll(-1, "pages")
                return "break"

        def _on_key_page_down(e):
            if isinstance(e.widget, (tk.Entry, tk.Text, ctk.CTkEntry)):
                return
            curr_sf = active_tab_ref.get("frame")
            if curr_sf and hasattr(curr_sf, "_parent_canvas"):
                curr_sf._parent_canvas.yview_scroll(1, "pages")
                return "break"

        def _on_key_home(e):
            if isinstance(e.widget, (tk.Entry, tk.Text, ctk.CTkEntry)):
                return
            curr_sf = active_tab_ref.get("frame")
            if curr_sf and hasattr(curr_sf, "_parent_canvas"):
                curr_sf._parent_canvas.yview_moveto(0.0)
                return "break"

        def _on_key_end(e):
            if isinstance(e.widget, (tk.Entry, tk.Text, ctk.CTkEntry)):
                return
            curr_sf = active_tab_ref.get("frame")
            if curr_sf and hasattr(curr_sf, "_parent_canvas"):
                curr_sf._parent_canvas.yview_moveto(1.0)
                return "break"

        settings_win.bind("<Prior>", _on_key_page_up)
        settings_win.bind("<Next>", _on_key_page_down)
        settings_win.bind("<Home>", _on_key_home)
        settings_win.bind("<End>", _on_key_end)

        # Build responsive navigation buttons inside nav_inner
        for tid, label in tab_names:
            btn = ctk.CTkButton(
                nav_inner,
                text=label,
                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
                fg_color="#1e293b",
                hover_color="#0369a1",
                text_color="#94a3b8",
                height=28,
                corner_radius=6,
                command=lambda t=tid: switch_to_tab(t)
            )
            btn.pack(side="left", padx=3, pady=4)
            btn.bind("<MouseWheel>", _on_nav_wheel)
            tab_buttons[tid] = btn

        # ====================================================
        # TAB 1: GENERAL
        # ====================================================
        scroll_gen = tab_frames["General"]

        card_gen = ctk.CTkFrame(scroll_gen, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_gen.pack(fill="x", pady=6)
        ctk.CTkLabel(card_gen, text="System Startup & Display Preferences", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 6))

        current_autostart = bool(VedaConfig.get_settings().get("start_with_windows", False))
        sw_auto = ctk.CTkSwitch(
            card_gen,
            text="Start V.E.D.A. automatically with Windows",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#f8fafc",
            command=lambda: VedaConfig.set_start_with_windows(bool(sw_auto.get()))
        )
        if current_autostart:
            sw_auto.select()
        else:
            sw_auto.deselect()
        sw_auto.pack(anchor="w", padx=14, pady=8)

        sw_desk = ctk.CTkSwitch(
            card_gen,
            text="Desktop Mode (Futuristic Glass HUD Overlay)",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#f8fafc",
            command=self.toggle_desktop_mode
        )
        if self.is_desktop_mode:
            sw_desk.select()
        else:
            sw_desk.deselect()
        sw_desk.pack(anchor="w", padx=14, pady=8)

        card_hud = ctk.CTkFrame(scroll_gen, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_hud.pack(fill="x", pady=6)
        ctk.CTkLabel(card_hud, text="First-Run Setup & Calibration", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(card_hud, text="Replay the introductory onboarding walkthrough covering permissions and features.", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8").pack(anchor="w", padx=12, pady=(0, 6))
        btn_replay = ctk.CTkButton(
            card_hud,
            text="Replay Welcome Screen",
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#38bdf8",
            height=28,
            command=lambda: (VedaConfig.reset_first_run(), _on_settings_close(), self.open_first_run_onboarding())
        )
        btn_replay.pack(anchor="w", padx=12, pady=(0, 10))

        # ====================================================
        # TAB 2: GITHUB RELEASES OTA UPDATES
        # ====================================================
        scroll_updates_tab = tab_frames["Updates"]

        card_gh_ota = ctk.CTkFrame(scroll_updates_tab, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_gh_ota.pack(fill="x", pady=6)

        ctk.CTkLabel(card_gh_ota, text="📦 Real GitHub Releases OTA Updater", font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(12, 4))

        gh_info_box = ctk.CTkFrame(card_gh_ota, fg_color="#05080e", corner_radius=6, border_width=1, border_color="#161f30")
        gh_info_box.pack(fill="x", padx=14, pady=(0, 10))

        lbl_gh_details = ctk.CTkLabel(gh_info_box, text="", font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", justify="left")
        lbl_gh_details.pack(anchor="w", padx=12, pady=10)

        def _refresh_updates_tab_info():
            st_text = production_updater.state.replace("_", " ")
            last_chk = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(production_updater.last_check_time)) if production_updater.last_check_time else "Never"
            rem_ver = production_updater.latest_release.clean_version if production_updater.latest_release else "--"
            asset_info = production_updater.selected_asset.name if production_updater.selected_asset else "None"
            text = (
                f"• Installed Version:   {VERSION} (Build {BUILD})\n"
                f"• Latest Release:      {rem_ver}\n"
                f"• Update Status:       {st_text}\n"
                f"• GitHub Repository:   shreyasbro/V.E.D.A\n"
                f"• Matched Asset:       {asset_info}\n"
                f"• Last Checked:        {last_chk}"
            )
            lbl_gh_details.configure(text=text)

        _refresh_updates_tab_info()

        # Telemetry / Progress Bar Container
        prog_frame = ctk.CTkFrame(card_gh_ota, fg_color="transparent")
        prog_frame.pack(fill="x", padx=14, pady=(0, 8))

        lbl_dl_telemetry = ctk.CTkLabel(prog_frame, text="", font=ctk.CTkFont(family="Consolas", size=10), text_color="#38bdf8", justify="left")
        lbl_dl_telemetry.pack(anchor="w", pady=(0, 2))

        prog_bar = ctk.CTkProgressBar(prog_frame, height=8, corner_radius=4, fg_color="#1e293b", progress_color="#0284c7")
        prog_bar.set(0.0)

        def _on_cancel_download_click():
            production_updater.cancel_download()
            prog_bar.pack_forget()
            btn_cancel_dl.pack_forget()
            lbl_dl_telemetry.configure(text="Download cancelled.", text_color="#f59e0b")
            btn_dl_update.configure(state="normal")
            _refresh_updates_tab_info()

        btn_cancel_dl = ctk.CTkButton(
            prog_frame,
            text="✕ Cancel Download",
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color="#334155",
            hover_color="#475569",
            height=22,
            width=120,
            command=_on_cancel_download_click
        )

        # Release Notes Preview Card
        card_notes = ctk.CTkFrame(scroll_updates_tab, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_notes.pack(fill="x", pady=6)

        ctk.CTkLabel(card_notes, text="📝 GitHub Release Notes", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(10, 4))
        txt_notes = ctk.CTkTextbox(card_notes, fg_color="#05080e", font=ctk.CTkFont(family="Consolas", size=10), text_color="#e2e8f0", height=100)
        txt_notes.pack(fill="x", padx=14, pady=(0, 10))
        txt_notes.insert("end", "Check GitHub releases to view latest changelog.\n")

        # Ensure mousewheel on notes bubbles up to the tab scroll container when bounds reached
        def _on_notes_mousewheel(e):
            try:
                first, last = txt_notes._textbox.yview()
                if (e.delta > 0 and first <= 0.0) or (e.delta < 0 and last >= 1.0):
                    if hasattr(scroll_updates_tab, "_parent_canvas"):
                        scroll_updates_tab._parent_canvas.yview_scroll(-int(e.delta / 6), "units")
                        return "break"
            except Exception:
                pass

        try:
            txt_notes._textbox.bind("<MouseWheel>", _on_notes_mousewheel)
        except Exception:
            pass

        def _update_notes_display():
            txt_notes.delete("1.0", "end")
            if production_updater.latest_release and production_updater.latest_release.body:
                txt_notes.insert("end", f"Release: {production_updater.latest_release.name or production_updater.latest_release.tag_name}\nPublished: {production_updater.latest_release.published_at}\n\n{production_updater.latest_release.body}")
            else:
                txt_notes.insert("end", "No release notes loaded.\n")

        # Action Buttons Row
        gh_act_row = ctk.CTkFrame(card_gh_ota, fg_color="transparent")
        gh_act_row.pack(fill="x", padx=14, pady=(0, 12))

        lbl_gh_action_msg = ctk.CTkLabel(gh_act_row, text="", font=ctk.CTkFont(family="Consolas", size=10), text_color="#38bdf8")
        lbl_gh_action_msg.pack(side="left", fill="x", expand=True)

        def _on_check_github_now():
            lbl_gh_action_msg.configure(text="Querying GitHub API (shreyasbro/V.E.D.A)...", text_color="#38bdf8")
            def _w():
                res = production_updater.check_for_updates()
                def _d():
                    if not settings_win.winfo_exists():
                        return
                    _refresh_updates_tab_info()
                    _update_notes_display()
                    self._refresh_notification_badge()
                    if res.get("update_available"):
                        if res.get("has_asset"):
                            lbl_gh_action_msg.configure(text=f"✓ Update v{res.get('latest_version')} ready to download.", text_color="#10b981")
                            btn_dl_update.pack(side="right", padx=(6, 0))
                        else:
                            lbl_gh_action_msg.configure(text=f"⚠️ {res.get('error')}", text_color="#f59e0b")
                    elif res.get("success"):
                        lbl_gh_action_msg.configure(text="✓ V.E.D.A. is up to date with GitHub.", text_color="#10b981")
                    else:
                        lbl_gh_action_msg.configure(text=f"✕ {res.get('error')}", text_color="#ef4444")
                self.after(0, _d)
            threading.Thread(target=_w, daemon=True).start()

        def _on_download_github_update():
            lbl_gh_action_msg.configure(text="Starting background download...", text_color="#38bdf8")
            btn_dl_update.configure(state="disabled")
            prog_bar.set(0.0)
            prog_bar.pack(fill="x", pady=(4, 6))
            btn_cancel_dl.pack(anchor="w", pady=(0, 4))

            def _prog(pct, done, total, speed, eta):
                if settings_win.winfo_exists():
                    p_str = f"Downloading: {int(pct*100)}% ({done // (1024*1024)} MB / {total // (1024*1024)} MB) • {speed:.1f} MB/s"
                    if eta:
                        p_str += f" • ETA {eta}s"
                    def _update_ui():
                        lbl_dl_telemetry.configure(text=p_str)
                        prog_bar.set(pct)
                        _refresh_updates_tab_info()
                    self.after(0, _update_ui)

            def _err(msg):
                if settings_win.winfo_exists():
                    self.after(0, lambda: (
                        lbl_gh_action_msg.configure(text=f"✕ {msg}", text_color="#ef4444"),
                        btn_dl_update.configure(state="normal"),
                        prog_bar.pack_forget(),
                        btn_cancel_dl.pack_forget(),
                        _refresh_updates_tab_info()
                    ))

            def _ready_restart():
                if settings_win.winfo_exists():
                    def _show_restart_prompt():
                        lbl_gh_action_msg.configure(text="✓ Verified! Ready to restart and install.", text_color="#10b981")
                        btn_dl_update.pack_forget()
                        prog_bar.pack_forget()
                        btn_cancel_dl.pack_forget()
                        btn_restart_install.pack(side="right", padx=(6, 0))
                    self.after(0, _show_restart_prompt)

            production_updater.download_and_install_async(progress_callback=_prog, on_error=_err, on_ready_to_restart=_ready_restart)

        def _on_restart_and_install():
            lbl_gh_action_msg.configure(text="Launching external updater process...", text_color="#38bdf8")
            production_updater.apply_update_and_restart()

        btn_chk_gh = ctk.CTkButton(
            gh_act_row,
            text="🔄 Check for Updates",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            height=28,
            command=_on_check_github_now
        )
        btn_chk_gh.pack(side="right")

        btn_dl_update = ctk.CTkButton(
            gh_act_row,
            text="⬇ Download Update",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=28,
            command=_on_download_github_update
        )

        btn_restart_install = ctk.CTkButton(
            gh_act_row,
            text="⚡ Restart & Install",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#ea580c",
            hover_color="#c2410c",
            height=28,
            command=_on_restart_and_install
        )

        if production_updater.state == "UPDATE_AVAILABLE" and production_updater.selected_asset:
            btn_dl_update.pack(side="right", padx=(6, 0))

        # Card 3: Updates Configuration
        card_upd_prefs = ctk.CTkFrame(scroll_updates_tab, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_upd_prefs.pack(fill="x", pady=6)

        ctk.CTkLabel(card_upd_prefs, text="Automatic Update Settings", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(12, 6))

        cur_settings = VedaConfig.get_settings()

        sw_auto_chk = ctk.CTkSwitch(
            card_upd_prefs,
            text="Automatically check for updates (quiet background check on startup)",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#f8fafc",
            command=lambda: VedaConfig.update_setting("update_auto_check", bool(sw_auto_chk.get()))
        )
        if cur_settings.get("update_auto_check", True):
            sw_auto_chk.select()
        else:
            sw_auto_chk.deselect()
        sw_auto_chk.pack(anchor="w", padx=16, pady=6)

        sw_auto_dl = ctk.CTkSwitch(
            card_upd_prefs,
            text="Automatically download updates when detected",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#f8fafc",
            command=lambda: VedaConfig.update_setting("update_auto_download", bool(sw_auto_dl.get()))
        )
        if cur_settings.get("update_auto_download", False):
            sw_auto_dl.select()
        else:
            sw_auto_dl.deselect()
        sw_auto_dl.pack(anchor="w", padx=16, pady=6)

        sw_auto_inst = ctk.CTkSwitch(
            card_upd_prefs,
            text="Automatically install updates",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#f8fafc",
            command=lambda: VedaConfig.update_setting("update_auto_install", bool(sw_auto_inst.get()))
        )
        if cur_settings.get("update_auto_install", False):
            sw_auto_inst.select()
        else:
            sw_auto_inst.deselect()
        sw_auto_inst.pack(anchor="w", padx=16, pady=6)

        sw_ask_restart = ctk.CTkSwitch(
            card_upd_prefs,
            text="Ask before restarting V.E.D.A. (Recommended)",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#f8fafc",
            command=lambda: VedaConfig.update_setting("update_ask_before_restart", bool(sw_ask_restart.get()))
        )
        if cur_settings.get("update_ask_before_restart", True):
            sw_ask_restart.select()
        else:
            sw_ask_restart.deselect()
        sw_ask_restart.pack(anchor="w", padx=16, pady=(6, 12))

        # ====================================================
        # TAB 3: IN-APP NOTIFICATIONS CENTER
        # ====================================================
        scroll_notif_tab = tab_frames["Notifications"]

        card_notif_mgmt = ctk.CTkFrame(scroll_notif_tab, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_notif_mgmt.pack(fill="x", pady=6)

        ctk.CTkLabel(card_notif_mgmt, text="🔔 Notification Preferences & Alert Sounds", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(12, 6))

        sw_upd_notifs = ctk.CTkSwitch(
            card_notif_mgmt,
            text="Show In-App Notifications for Detected Updates",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#f8fafc",
            command=lambda: VedaConfig.update_setting("update_notifications", bool(sw_upd_notifs.get()))
        )
        if cur_settings.get("update_notifications", True):
            sw_upd_notifs.select()
        else:
            sw_upd_notifs.deselect()
        sw_upd_notifs.pack(anchor="w", padx=16, pady=6)

        sw_notif_snd = ctk.CTkSwitch(
            card_notif_mgmt,
            text="Play Windows Notification Sound on Alerts",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#f8fafc",
            command=lambda: VedaConfig.update_setting("notification_sounds", bool(sw_notif_snd.get()))
        )
        if cur_settings.get("notification_sounds", False):
            sw_notif_snd.select()
        else:
            sw_notif_snd.deselect()
        sw_notif_snd.pack(anchor="w", padx=16, pady=(6, 12))

        # ====================================================
        # TAB 3: USER-OWNED AI PROVIDERS & REAL NETWORK DIAGNOSTICS
        # ====================================================
        scroll_ai = tab_frames["AI Provider"]

        # Top Bar with Info & [+ Add Provider]
        card_ai_top = ctk.CTkFrame(scroll_ai, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_ai_top.pack(fill="x", pady=(2, 6))

        top_row = ctk.CTkFrame(card_ai_top, fg_color="transparent")
        top_row.pack(fill="x", padx=12, pady=10)

        left_info = ctk.CTkFrame(top_row, fg_color="transparent")
        left_info.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(left_info, text="🧠 User-Owned AI Providers", font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color="#38bdf8").pack(anchor="w")

        lbl_ai_summary = ctk.CTkLabel(
            left_info,
            text="",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#94a3b8"
        )
        lbl_ai_summary.pack(anchor="w", pady=(2, 0))

        def _refresh_ai_summary():
            diag = self.agent.router.get_diagnostics()
            primary = api_manager.get_primary_provider()
            p_name = primary.name if primary else "None"
            r_count = len(api_manager.get_ready_providers())
            tot_count = len(api_manager.providers)
            lbl_ai_summary.configure(text=f"Primary: {p_name} | Verified Ready: {r_count}/{tot_count} | Fallback: Offline Local AI")

        _refresh_ai_summary()

        # Dynamic Providers Container
        providers_container = ctk.CTkFrame(scroll_ai, fg_color="transparent")
        providers_container.pack(fill="both", expand=True, pady=2)

        def _open_provider_modal(provider_id: Optional[str] = None):
            is_edit = provider_id is not None
            existing = api_manager.get_provider(provider_id) if is_edit else None

            modal = ctk.CTkToplevel(settings_win)
            modal.title("Edit AI Provider" if is_edit else "Add New AI Provider")
            modal.geometry("560x540")
            modal.minsize(500, 480)
            modal.configure(fg_color="#07090e")
            modal.attributes("-topmost", True)

            m_box = ctk.CTkFrame(modal, fg_color="#0b101b", corner_radius=10, border_width=1, border_color="#1e293b")
            m_box.pack(fill="both", expand=True, padx=12, pady=12)

            ctk.CTkLabel(
                m_box,
                text="Configure AI Provider" if is_edit else "Add Custom AI Provider",
                font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                text_color="#38bdf8"
            ).pack(anchor="w", padx=14, pady=(12, 6))

            # Preset Template Selector
            row_p = ctk.CTkFrame(m_box, fg_color="transparent")
            row_p.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(row_p, text="Template / Preset:", font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", width=130, anchor="w").pack(side="left")
            preset_names = list(PRESET_TEMPLATES.keys())
            opt_preset = ctk.CTkOptionMenu(
                row_p,
                values=preset_names,
                font=ctk.CTkFont(family="Consolas", size=11),
                height=26,
                fg_color="#1e293b",
                button_color="#334155"
            )
            opt_preset.pack(side="left", fill="x", expand=True)

            # Name
            row_n = ctk.CTkFrame(m_box, fg_color="transparent")
            row_n.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(row_n, text="Provider Name:", font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", width=130, anchor="w").pack(side="left")
            entry_name = ctk.CTkEntry(row_n, font=ctk.CTkFont(family="Consolas", size=11), height=26, fg_color="#05080e", border_color="#1e293b")
            if existing:
                entry_name.insert(0, existing.name)
            entry_name.pack(side="left", fill="x", expand=True)

            # Protocol
            row_prot = ctk.CTkFrame(m_box, fg_color="transparent")
            row_prot.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(row_prot, text="Protocol:", font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", width=130, anchor="w").pack(side="left")
            opt_protocol = ctk.CTkOptionMenu(
                row_prot,
                values=["openai_compatible", "gemini", "custom_http"],
                font=ctk.CTkFont(family="Consolas", size=11),
                height=26,
                fg_color="#1e293b",
                button_color="#334155"
            )
            if existing:
                opt_protocol.set(existing.protocol)
            opt_protocol.pack(side="left", fill="x", expand=True)

            # Base URL
            row_u = ctk.CTkFrame(m_box, fg_color="transparent")
            row_u.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(row_u, text="Base URL:", font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", width=130, anchor="w").pack(side="left")
            entry_url = ctk.CTkEntry(row_u, font=ctk.CTkFont(family="Consolas", size=11), height=26, fg_color="#05080e", border_color="#1e293b")
            if existing:
                entry_url.insert(0, existing.base_url)
            entry_url.pack(side="left", fill="x", expand=True)

            # Model
            row_m = ctk.CTkFrame(m_box, fg_color="transparent")
            row_m.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(row_m, text="Model Name:", font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", width=130, anchor="w").pack(side="left")
            entry_model = ctk.CTkEntry(row_m, font=ctk.CTkFont(family="Consolas", size=11), height=26, fg_color="#05080e", border_color="#1e293b")
            if existing:
                entry_model.insert(0, existing.model)
            entry_model.pack(side="left", fill="x", expand=True)

            # API Key
            row_k = ctk.CTkFrame(m_box, fg_color="transparent")
            row_k.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(row_k, text="API Key:", font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", width=130, anchor="w").pack(side="left")
            entry_key = ctk.CTkEntry(row_k, font=ctk.CTkFont(family="Consolas", size=11), height=26, fg_color="#05080e", border_color="#1e293b", show="•")
            if existing:
                entry_key.insert(0, existing.api_key)
            entry_key.pack(side="left", fill="x", expand=True, padx=(0, 6))

            is_showing = [False]
            def _toggle_key():
                is_showing[0] = not is_showing[0]
                entry_key.configure(show="" if is_showing[0] else "•")
                btn_eye.configure(text="Hide" if is_showing[0] else "Show")

            btn_eye = ctk.CTkButton(row_k, text="Show", font=ctk.CTkFont(family="Consolas", size=10), width=50, height=26, fg_color="#1e293b", hover_color="#334155", command=_toggle_key)
            btn_eye.pack(side="right")

            def _on_preset_picked(choice):
                if choice in PRESET_TEMPLATES:
                    t = PRESET_TEMPLATES[choice]
                    entry_name.delete(0, 'end')
                    entry_name.insert(0, t["name"])
                    entry_url.delete(0, 'end')
                    entry_url.insert(0, t["base_url"])
                    entry_model.delete(0, 'end')
                    entry_model.insert(0, t["default_model"])
                    opt_protocol.set(t["protocol"])
            opt_preset.configure(command=_on_preset_picked)

            lbl_test_res = ctk.CTkLabel(m_box, text="", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8", wraplength=500, justify="left")
            lbl_test_res.pack(anchor="w", padx=14, pady=(10, 4))

            # Action Buttons inside Modal
            row_act = ctk.CTkFrame(m_box, fg_color="transparent")
            row_act.pack(fill="x", padx=14, pady=(12, 10))

            def _test_current_modal():
                name = entry_name.get().strip() or "Provider"
                prot = opt_protocol.get()
                b_url = entry_url.get().strip()
                mod = entry_model.get().strip()
                k = entry_key.get().strip()

                lbl_test_res.configure(text=f"Probing {name} endpoint...", text_color="#38bdf8")

                def _w():
                    # Temporary in-memory provider for isolated probe
                    temp_p = UserAIProvider(
                        id="temp_probe",
                        name=name,
                        protocol=prot,
                        base_url=b_url,
                        model=mod
                    )
                    temp_p.api_key = k
                    # Register temporarily with manager for testing
                    with api_manager._lock:
                        api_manager.providers.append(temp_p)
                    ok, msg, lat = api_manager.test_provider(temp_p.id)
                    with api_manager._lock:
                        api_manager.providers = [p for p in api_manager.providers if p.id != "temp_probe"]

                    def _d():
                        if not modal.winfo_exists():
                            return
                        if ok:
                            lbl_test_res.configure(text=f"✓ Validated ({lat}ms): {msg}", text_color="#10b981")
                        else:
                            lbl_test_res.configure(text=f"✕ Connection Failed: {msg}", text_color="#ef4444")
                    modal.after(0, _d)

                threading.Thread(target=_w, daemon=True).start()

            def _save_modal():
                name = entry_name.get().strip()
                prot = opt_protocol.get()
                b_url = entry_url.get().strip()
                mod = entry_model.get().strip()
                k = entry_key.get().strip()

                if not name:
                    lbl_test_res.configure(text="✕ Provider Name is required", text_color="#ef4444")
                    return

                if is_edit and existing:
                    api_manager.update_provider(
                        existing.id,
                        name=name,
                        protocol=prot,
                        base_url=b_url,
                        model=mod,
                        api_key=k
                    )
                else:
                    api_manager.add_provider(
                        name=name,
                        protocol=prot,
                        base_url=b_url,
                        model=mod,
                        api_key=k
                    )

                modal.destroy()
                _refresh_providers_list()
                _refresh_ai_summary()
                self._refresh_ai_provider_button()
                self._refresh_status_pill()

            ctk.CTkButton(
                row_act,
                text="⚡ Test API Connection",
                font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#38bdf8",
                command=_test_current_modal
            ).pack(side="left")

            ctk.CTkButton(
                row_act,
                text="💾 Save Provider",
                font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                fg_color="#0284c7",
                hover_color="#0369a1",
                text_color="#ffffff",
                command=_save_modal
            ).pack(side="right")

        btn_add = ctk.CTkButton(
            top_row,
            text="+ Add AI Provider",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            height=28,
            command=lambda: _open_provider_modal(None)
        )
        btn_add.pack(side="right")

        def _refresh_providers_list():
            for child in providers_container.winfo_children():
                child.destroy()

            providers = api_manager.get_providers()
            if not providers:
                # Clean slate prompt: ZERO preconfigured providers
                empty_card = ctk.CTkFrame(providers_container, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
                empty_card.pack(fill="x", pady=12)

                ctk.CTkLabel(
                    empty_card,
                    text="Configure Your AI Provider",
                    font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                    text_color="#38bdf8"
                ).pack(anchor="w", padx=16, pady=(16, 4))

                ctk.CTkLabel(
                    empty_card,
                    text="V.E.D.A. does not include preloaded AI API keys. Add your own AI provider configuration to use online AI services.",
                    font=ctk.CTkFont(family="Consolas", size=11),
                    text_color="#94a3b8",
                    wraplength=640,
                    justify="left"
                ).pack(anchor="w", padx=16, pady=(0, 14))

                ctk.CTkButton(
                    empty_card,
                    text="+ Add AI Provider",
                    font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                    fg_color="#0284c7",
                    hover_color="#0369a1",
                    height=30,
                    width=150,
                    command=lambda: _open_provider_modal(None)
                ).pack(anchor="w", padx=16, pady=(0, 16))
                return

            for prov in providers:
                card = ctk.CTkFrame(providers_container, fg_color="#080c14", corner_radius=6, border_width=1, border_color="#1e293b")
                card.pack(fill="x", pady=3)

                row = ctk.CTkFrame(card, fg_color="transparent")
                row.pack(fill="x", padx=10, pady=8)

                # Enable toggle
                def _make_toggle(pid=prov.id, cur=prov.enabled):
                    return lambda: (api_manager.update_provider(pid, enabled=not cur), _refresh_providers_list(), _refresh_ai_summary(), self._refresh_ai_provider_button(), self._refresh_status_pill())

                sw = ctk.CTkSwitch(
                    row,
                    text="",
                    command=_make_toggle(),
                    width=42
                )
                if prov.enabled:
                    sw.select()
                else:
                    sw.deselect()
                sw.pack(side="left", padx=(0, 6))

                # Info Column
                info_col = ctk.CTkFrame(row, fg_color="transparent")
                info_col.pack(side="left", fill="x", expand=True)

                p_title = f"{prov.name} [{prov.model or 'No model'}]"
                if prov.is_primary:
                    p_title += " ★ PRIMARY"
                ctk.CTkLabel(info_col, text=p_title, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#38bdf8" if prov.enabled else "#64748b", anchor="w").pack(anchor="w")

                key_masked = mask_key(prov.api_key)
                ctk.CTkLabel(info_col, text=f"Protocol: {prov.protocol} | Key: {key_masked} | Base: {prov.base_url[:30]}", font=ctk.CTkFont(family="Consolas", size=9), text_color="#64748b", anchor="w").pack(anchor="w")

                # Status Badge
                st_color = "#10b981" if prov.status == "READY" else ("#ef4444" if "ERROR" in prov.status or "40" in prov.status else "#64748b")
                st_text = prov.status
                if prov.last_latency_ms is not None:
                    st_text += f" ({prov.last_latency_ms}ms)"
                ctk.CTkLabel(row, text=st_text, font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=st_color, width=120, anchor="e").pack(side="left", padx=6)

                # Test Button
                def _make_test(pid=prov.id):
                    def _t():
                        def _w():
                            api_manager.test_provider(pid)
                            self.after(0, lambda: (_refresh_providers_list(), _refresh_ai_summary(), self._refresh_ai_provider_button(), self._refresh_status_pill()))
                        threading.Thread(target=_w, daemon=True).start()
                    return _t

                ctk.CTkButton(
                    row,
                    text="⚡ Test",
                    font=ctk.CTkFont(family="Consolas", size=10),
                    fg_color="#1e293b",
                    hover_color="#334155",
                    text_color="#38bdf8",
                    width=52,
                    height=24,
                    command=_make_test()
                ).pack(side="left", padx=2)

                # Set Primary Button
                if not prov.is_primary:
                    def _make_primary(pid=prov.id):
                        return lambda: (api_manager.set_primary(pid), _refresh_providers_list(), _refresh_ai_summary(), self._refresh_ai_provider_button(), self._refresh_status_pill())

                    ctk.CTkButton(
                        row,
                        text="★ Primary",
                        font=ctk.CTkFont(family="Consolas", size=10),
                        fg_color="#1e293b",
                        hover_color="#334155",
                        text_color="#f59e0b",
                        width=68,
                        height=24,
                        command=_make_primary()
                    ).pack(side="left", padx=2)

                # Edit Button
                ctk.CTkButton(
                    row,
                    text="⚙ Edit",
                    font=ctk.CTkFont(family="Consolas", size=10),
                    fg_color="#1e293b",
                    hover_color="#334155",
                    text_color="#f8fafc",
                    width=50,
                    height=24,
                    command=lambda pid=prov.id: _open_provider_modal(pid)
                ).pack(side="left", padx=2)

                # Remove Button
                def _make_del(pid=prov.id):
                    return lambda: (api_manager.remove_provider(pid), _refresh_providers_list(), _refresh_ai_summary(), self._refresh_ai_provider_button(), self._refresh_status_pill())

                ctk.CTkButton(
                    row,
                    text="✕",
                    font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
                    fg_color="#1e293b",
                    hover_color="#991b1b",
                    text_color="#ef4444",
                    width=32,
                    height=24,
                    command=_make_del()
                ).pack(side="left", padx=2)

        _refresh_providers_list()


        # ====================================================
        # TAB 3: VOICE (Kokoro Primary & Default Local TTS)
        # ====================================================
        scroll_voice = tab_frames["Voice"]

        tts_diag = tts_engine.get_diagnostics()

        card_voice_info = ctk.CTkFrame(scroll_voice, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_voice_info.pack(fill="x", pady=6)

        vh_hdr = ctk.CTkFrame(card_voice_info, fg_color="transparent")
        vh_hdr.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkLabel(vh_hdr, text="🎙️ Kokoro TTS Engine (Primary / Local / Offline)", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(side="left")

        def _get_kokoro_status_color(st):
            if "OFFLINE READY" in st or "READY" in st:
                return "#10b981"
            elif "ERROR" in st:
                return "#ef4444"
            elif "INITIALIZING" in st or "DOWNLOADING" in st:
                return "#38bdf8"
            return "#eab308"

        k_st = tts_diag.get("status", "NOT INITIALIZED")
        lbl_v_badge = ctk.CTkLabel(vh_hdr, text=f"[{k_st}]", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color=_get_kokoro_status_color(k_st))
        lbl_v_badge.pack(side="right")

        voice_box = ctk.CTkFrame(card_voice_info, fg_color="#05080e", corner_radius=6, border_width=1, border_color="#161f30")
        voice_box.pack(fill="x", padx=12, pady=(0, 10))

        lbl_v_details = ctk.CTkLabel(voice_box, text="", font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", justify="left")
        lbl_v_details.pack(anchor="w", padx=10, pady=8)

        def _refresh_voice_display():
            diag = tts_engine.get_diagnostics()
            st = diag.get("status", "NOT INITIALIZED")
            lbl_v_badge.configure(text=f"[{st}]", text_color=_get_kokoro_status_color(st))
            inst_str = "Installed & Verified" if diag.get("is_installed") else "Not Installed Yet"
            v_text = (
                f"• TTS Engine:          Kokoro ONNX (Local / Offline Primary)\n"
                f"• Engine Status:       {st}\n"
                f"• Model Status:        {inst_str}\n"
                f"• Execution Mode:      {diag.get('device')} Mode\n"
                f"• Audio Output Device: {diag.get('output_device')}\n"
                f"• Active Voice:        {diag.get('voice')}\n"
                f"• Speed Multiplier:    {diag.get('speed')}x\n"
                f"• Offline Ready:       YES (Operates 100% without internet)\n"
                f"• Last Latency:        {diag.get('last_latency_ms') or '--'} ms ({diag.get('last_audio_duration_sec') or '--'}s synthesized audio)\n"
                f"• Diagnostics Detail:  {diag.get('last_error') or 'None'}"
            )
            lbl_v_details.configure(text=v_text)

        _refresh_voice_display()

        # TOP ACTION BAR: Kokoro Diagnostics Quick-Access
        card_diag_action = ctk.CTkFrame(scroll_voice, fg_color="#0b101b", corner_radius=8, border_width=1, border_color="#1e293b")
        card_diag_action.pack(fill="x", pady=(0, 6))

        top_act_inner = ctk.CTkFrame(card_diag_action, fg_color="transparent")
        top_act_inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            top_act_inner,
            text="Kokoro TTS Diagnostics & Hardware Status",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#f8fafc"
        ).pack(side="left")

        btn_view_api = ctk.CTkButton(
            top_act_inner,
            text="🔍 View Engine Diagnostics",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            height=30,
            command=lambda: self.open_api_diagnostics_dialog(parent_window=settings_win)
        )
        btn_view_api.pack(side="right")

        # Voice & Speed Configuration Card
        card_voice_cfg = ctk.CTkFrame(scroll_voice, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_voice_cfg.pack(fill="x", pady=6)
        ctk.CTkLabel(card_voice_cfg, text="Kokoro Voice & Synthesis Preferences", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(card_voice_cfg, text="Select from installed Kokoro neural voice profiles and customize speech rate.", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8").pack(anchor="w", padx=12, pady=(0, 8))

        cfg_row = ctk.CTkFrame(card_voice_cfg, fg_color="transparent")
        cfg_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(cfg_row, text="Voice:", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#f8fafc").pack(side="left", padx=(0, 6))

        kokoro_voices = tts_engine.kokoro_provider.get_voices() if tts_engine.kokoro_provider else ["af_heart"]
        current_voice = VedaConfig.get_settings().get("kokoro_voice", "af_heart")

        def _on_voice_change(new_voice):
            VedaConfig.update_setting("kokoro_voice", new_voice)
            if tts_engine.kokoro_provider:
                tts_engine.kokoro_provider.selected_voice = new_voice
            _refresh_voice_display()

        opt_voice = ctk.CTkOptionMenu(
            cfg_row,
            values=kokoro_voices if kokoro_voices else ["af_heart"],
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#1e293b",
            button_color="#0284c7",
            command=_on_voice_change,
            width=130
        )
        opt_voice.set(current_voice if current_voice in kokoro_voices else (kokoro_voices[0] if kokoro_voices else "af_heart"))
        opt_voice.pack(side="left", padx=(0, 16))

        # Speed Dropdown (0.75x to 1.50x)
        ctk.CTkLabel(cfg_row, text="Speed:", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#f8fafc").pack(side="left", padx=(0, 6))

        speed_options = ["0.75x", "0.90x", "1.00x", "1.15x", "1.25x", "1.50x"]
        curr_spd_val = float(VedaConfig.get_settings().get("kokoro_speed", 1.0))
        curr_spd_str = f"{curr_spd_val:.2f}x"
        if curr_spd_str not in speed_options:
            curr_spd_str = "1.00x"

        def _on_speed_change(new_spd_str):
            try:
                spd_val = float(new_spd_str.replace("x", ""))
                VedaConfig.update_setting("kokoro_speed", spd_val)
                if tts_engine.kokoro_provider:
                    tts_engine.kokoro_provider.speed = spd_val
                _refresh_voice_display()
            except Exception:
                pass

        opt_speed = ctk.CTkOptionMenu(
            cfg_row,
            values=speed_options,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#1e293b",
            button_color="#0284c7",
            command=_on_speed_change,
            width=90
        )
        opt_speed.set(curr_spd_str)
        opt_speed.pack(side="left", padx=(0, 16))

        # Language handling indicator
        ctk.CTkLabel(cfg_row, text="Language:", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#f8fafc").pack(side="left", padx=(0, 6))
        opt_lang = ctk.CTkOptionMenu(
            cfg_row,
            values=["Auto (EN/HI)", "English", "Hindi", "Hinglish"],
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#1e293b",
            button_color="#0284c7",
            width=120
        )
        opt_lang.set("Auto (EN/HI)")
        opt_lang.pack(side="left")

        # Model Installation & Management Actions
        card_model_mgmt = ctk.CTkFrame(scroll_voice, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_model_mgmt.pack(fill="x", pady=6)
        ctk.CTkLabel(card_model_mgmt, text="Kokoro Model Management & First-Run Setup", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(card_model_mgmt, text="Model weights are cached locally in ~/.veda/models/kokoro. Downloads occur only once.", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8").pack(anchor="w", padx=12, pady=(0, 6))

        lbl_k_msg = ctk.CTkLabel(card_model_mgmt, text="", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8")
        lbl_k_msg.pack(anchor="w", padx=12, pady=(0, 6))

        def _install_kokoro_model():
            if not tts_engine.kokoro_provider:
                return
            lbl_k_msg.configure(text="Downloading Kokoro model assets (in background)...", text_color="#38bdf8")
            lbl_v_badge.configure(text="[DOWNLOADING]", text_color="#38bdf8")

            def _progress(msg, p):
                def _u():
                    if not settings_win.winfo_exists():
                        return
                    lbl_k_msg.configure(text=f"{msg} ({int(p*100)}%)", text_color="#38bdf8")
                    if p >= 1.0:
                        tts_engine.reload_config()
                        _refresh_voice_display()
                        lbl_k_msg.configure(text="✓ Kokoro TTS installed and ready for offline speech.", text_color="#10b981")
                settings_win.after(0, _u)

            tts_engine.kokoro_provider.model_manager.download_models_async(progress_callback=_progress)

        k_actions_row = ctk.CTkFrame(card_model_mgmt, fg_color="transparent")
        k_actions_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkButton(
            k_actions_row,
            text="📥 Install / Repair Model",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            height=30,
            command=_install_kokoro_model
        ).pack(side="left", padx=(0, 8))

        def _reload_kokoro():
            tts_engine.reload_config()
            _refresh_voice_display()
            lbl_k_msg.configure(text="Kokoro engine reloaded.", text_color="#38bdf8")

        ctk.CTkButton(
            k_actions_row,
            text="↻ Reload Engine",
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#94a3b8",
            height=30,
            command=_reload_kokoro
        ).pack(side="left")

        # Multi-Lingual Voice Synthesis Probe (English, Hindi, Hinglish)
        card_voice_test = ctk.CTkFrame(scroll_voice, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_voice_test.pack(fill="x", pady=6)
        ctk.CTkLabel(card_voice_test, text="Multi-Lingual Voice Synthesis Test", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(card_voice_test, text="Generates authentic audio locally with Kokoro and plays through your default audio hardware.", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8").pack(anchor="w", padx=12, pady=(0, 6))

        lbl_v_res = ctk.CTkLabel(card_voice_test, text="", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8")
        lbl_v_res.pack(anchor="w", padx=12, pady=(0, 6))

        def _run_voice_test(lang_choice):
            lbl_v_res.configure(text=f"Synthesizing {lang_choice.title()} audio with Kokoro...", text_color="#38bdf8")
            def _w():
                ok, msg = tts_engine.test_voice(lang_choice)
                def _u():
                    if not settings_win.winfo_exists():
                        return
                    _refresh_voice_display()
                    if ok:
                        lbl_v_res.configure(text=f"✓ {msg}", text_color="#10b981")
                    else:
                        lbl_v_res.configure(text=f"✕ Speech test failed: {msg}", text_color="#ef4444")
                self.after(0, _u)
            threading.Thread(target=_w, daemon=True).start()

        btn_test_row = ctk.CTkFrame(card_voice_test, fg_color="transparent")
        btn_test_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkButton(btn_test_row, text="🗣 Test English", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), fg_color="#0284c7", hover_color="#0369a1", text_color="#ffffff", height=28, command=lambda: _run_voice_test("english")).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_test_row, text="🗣 Test Hindi", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), fg_color="#0284c7", hover_color="#0369a1", text_color="#ffffff", height=28, command=lambda: _run_voice_test("hindi")).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_test_row, text="🗣 Test Hinglish", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), fg_color="#0284c7", hover_color="#0369a1", text_color="#ffffff", height=28, command=lambda: _run_voice_test("hinglish")).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_test_row, text="⏹ Stop", font=ctk.CTkFont(family="Consolas", size=10), fg_color="#7f1d1d", hover_color="#991b1b", text_color="#ffffff", height=28, width=60, command=tts_engine.stop).pack(side="right")

        # Volume control slider
        card_vol = ctk.CTkFrame(scroll_voice, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_vol.pack(fill="x", pady=6)
        ctk.CTkLabel(card_vol, text="Voice Output Volume", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 4))

        vol_row = ctk.CTkFrame(card_vol, fg_color="transparent")
        vol_row.pack(fill="x", padx=12, pady=(0, 10))
        slider_vol = ctk.CTkSlider(vol_row, from_=0.0, to=1.0, number_of_steps=20)
        slider_vol.set(tts_engine.volume)
        slider_vol.pack(side="left", fill="x", expand=True, padx=(0, 10))
        lbl_vol_num = ctk.CTkLabel(vol_row, text=f"{int(tts_engine.volume * 100)}%", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#f8fafc", width=45)
        lbl_vol_num.pack(side="right")
        slider_vol.configure(command=lambda v: (tts_engine.set_volume(v), lbl_vol_num.configure(text=f"{int(v * 100)}%")))

        # ====================================================
        # TAB 4: HARDWARE (Audio Output, Screen Displays, Camera & Mic)
        # ====================================================
        scroll_hw = tab_frames["Hardware"]

        # Audio Output Subsystem card
        card_audio_hw = ctk.CTkFrame(scroll_hw, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_audio_hw.pack(fill="x", pady=6)
        ctk.CTkLabel(card_audio_hw, text="🔊 Audio Hardware & Output Subsystem", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 4))

        audio_box = ctk.CTkFrame(card_audio_hw, fg_color="#05080e", corner_radius=6, border_width=1, border_color="#161f30")
        audio_box.pack(fill="x", padx=12, pady=(0, 10))

        audio_info = "• Engine: Pygame Mixer (In-Memory Streaming)\n• Sample Rate: 24,000Hz (Kokoro TTS Native)\n• Channels: 2 (Stereo DirectSound / WASAPI)\n• Buffer Mode: Zero persistent disk cache"
        ctk.CTkLabel(audio_box, text=audio_info, font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", justify="left").pack(anchor="w", padx=10, pady=8)

        # Displays / Monitor Card
        card_mon = ctk.CTkFrame(scroll_hw, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_mon.pack(fill="x", pady=6)
        ctk.CTkLabel(card_mon, text="🖥️ Display & Monitor Geometry", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 4))

        mon_box = ctk.CTkFrame(card_mon, fg_color="#05080e", corner_radius=6, border_width=1, border_color="#161f30")
        mon_box.pack(fill="x", padx=12, pady=(0, 10))

        mon_text = f"• Primary Window Resolution: {self.winfo_width()}x{self.winfo_height()}\n• Desktop Perception: Active in RAM (0 Disk Writes)\n• Observation Mode: {live_screen_manager.mode}"
        try:
            import mss
            with mss.mss() as sct:
                mon_count = len(sct.monitors) - 1
                mon_text += f"\n• Connected Monitors Detected: {mon_count}"
                for i, m in enumerate(sct.monitors[1:], 1):
                    mon_text += f"\n  - Display {i}: {m['width']}x{m['height']} at ({m['left']},{m['top']})"
        except Exception:
            pass

        ctk.CTkLabel(mon_box, text=mon_text, font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", justify="left").pack(anchor="w", padx=10, pady=8)

        # Microphone card
        card_mic = ctk.CTkFrame(scroll_hw, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_mic.pack(fill="x", pady=6)
        ctk.CTkLabel(card_mic, text="🎙️ Microphone Subsystem", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 4))

        mic_mode_row = ctk.CTkFrame(card_mic, fg_color="transparent")
        mic_mode_row.pack(fill="x", padx=12, pady=(2, 8))
        ctk.CTkLabel(mic_mode_row, text="Microphone Mode:", font=ctk.CTkFont(family="Consolas", size=11), text_color="#cbd5e1").pack(side="left")
        
        lbl_mic_curr = ctk.CTkLabel(mic_mode_row, text="Always On" if self.mic_mode == "always_on" else "Toggle ON/OFF", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#10b981" if self.mic_mode == "always_on" else "#38bdf8")
        lbl_mic_curr.pack(side="left", padx=8)

        def _switch_mic_mode():
            self.toggle_mic_mode()
            lbl_mic_curr.configure(text="Always On" if self.mic_mode == "always_on" else "Toggle ON/OFF", text_color="#10b981" if self.mic_mode == "always_on" else "#38bdf8")

        ctk.CTkButton(mic_mode_row, text="Switch Mode", font=ctk.CTkFont(family="Consolas", size=10), fg_color="#1e293b", hover_color="#334155", text_color="#38bdf8", height=24, command=_switch_mic_mode).pack(side="right")

        # Camera Subsystem card
        cam_diag = camera_subsystem.get_diagnostics()
        card_cam = ctk.CTkFrame(scroll_hw, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_cam.pack(fill="x", pady=6)
        ctk.CTkLabel(card_cam, text="📷 Camera Vision Subsystem", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 4))

        cam_box = ctk.CTkFrame(card_cam, fg_color="#05080e", corner_radius=6, border_width=1, border_color="#161f30")
        cam_box.pack(fill="x", padx=12, pady=(0, 8))
        cam_info_text = (
            f"• Camera State:       {camera_subsystem.state}\n"
            f"• Active Resolution:  {cam_diag.get('resolution', '640x480')} | Target FPS: {cam_diag.get('fps', 0.0)}\n"
            f"• Orientation:        {'Mirrored' if camera_subsystem.mirror else 'Normal'} ({camera_subsystem.rotation}°)\n"
            f"• Multimodal Vision:  Gemini Vision In-RAM Inspection"
        )
        ctk.CTkLabel(cam_box, text=cam_info_text, font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", justify="left").pack(anchor="w", padx=10, pady=8)

        cam_act_row = ctk.CTkFrame(card_cam, fg_color="transparent")
        cam_act_row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(cam_act_row, text="Toggle Camera Preview", font=ctk.CTkFont(family="Consolas", size=11), fg_color="#1e293b", hover_color="#334155", text_color="#38bdf8", height=28, command=self.toggle_camera).pack(side="left")

        # Offline Camera Mouse Control Subsystem Card
        card_cam_mouse = ctk.CTkFrame(scroll_hw, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_cam_mouse.pack(fill="x", pady=6)
        
        cm_hdr = ctk.CTkFrame(card_cam_mouse, fg_color="transparent")
        cm_hdr.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(cm_hdr, text="✋ Offline Camera Mouse Control (2-Core CPU)", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(side="left")
        
        cm_status_badge = ctk.CTkLabel(cm_hdr, text="[ACTIVE]" if camera_mouse_controller.is_active else "[OFF]", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#10b981" if camera_mouse_controller.is_active else "#64748b")
        cm_status_badge.pack(side="right")

        cm_box = ctk.CTkFrame(card_cam_mouse, fg_color="#05080e", corner_radius=6, border_width=1, border_color="#161f30")
        cm_box.pack(fill="x", padx=12, pady=(0, 8))
        
        cm_diag = camera_mouse_controller.get_diagnostics()
        cm_desc = (
            f"• Tracking Engine:   MediaPipe Tasks (TFLite XNNPACK CPU-Only)\n"
            f"• Privacy / Network: 100% Offline (Strictly in-RAM, 0 disk writes)\n"
            f"• CPU Mode:          {cm_diag['cpu_mode']}\n"
            f"• Emergency Stop:    Press ESC at any time to immediately disable"
        )
        lbl_cm_desc = ctk.CTkLabel(cm_box, text=cm_desc, font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", justify="left")
        lbl_cm_desc.pack(anchor="w", padx=10, pady=8)

        # Sensitivity & Smoothing Sliders Row
        slider_row = ctk.CTkFrame(card_cam_mouse, fg_color="transparent")
        slider_row.pack(fill="x", padx=12, pady=(2, 6))

        ctk.CTkLabel(slider_row, text="Sensitivity:", font=ctk.CTkFont(family="Consolas", size=11), text_color="#cbd5e1").pack(side="left", padx=(0, 6))
        sl_sens = ctk.CTkSlider(slider_row, from_=1.0, to=3.0, number_of_steps=20, width=120)
        sl_sens.set(camera_mouse_controller.sensitivity)
        sl_sens.pack(side="left", padx=(0, 15))
        lbl_sens_val = ctk.CTkLabel(slider_row, text=f"{camera_mouse_controller.sensitivity:.1f}x", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color="#38bdf8", width=35)
        lbl_sens_val.pack(side="left", padx=(0, 15))
        sl_sens.configure(command=lambda v: (setattr(camera_mouse_controller, "sensitivity", round(v, 2)), lbl_sens_val.configure(text=f"{v:.1f}x"), VedaConfig.update_setting("camera_mouse_sensitivity", round(v, 2))))

        ctk.CTkLabel(slider_row, text="Smoothing:", font=ctk.CTkFont(family="Consolas", size=11), text_color="#cbd5e1").pack(side="left", padx=(0, 6))
        sl_smooth = ctk.CTkSlider(slider_row, from_=0.2, to=0.8, number_of_steps=12, width=100)
        sl_smooth.set(camera_mouse_controller.smoothing)
        sl_smooth.pack(side="left", padx=(0, 8))
        lbl_sm_val = ctk.CTkLabel(slider_row, text=f"{camera_mouse_controller.smoothing:.2f}", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color="#38bdf8", width=35)
        lbl_sm_val.pack(side="left")
        sl_smooth.configure(command=lambda v: (setattr(camera_mouse_controller, "smoothing", round(v, 2)), lbl_sm_val.configure(text=f"{v:.2f}"), VedaConfig.update_setting("camera_mouse_smoothing", round(v, 2))))

        # Buttons row
        cm_btn_row = ctk.CTkFrame(card_cam_mouse, fg_color="transparent")
        cm_btn_row.pack(fill="x", padx=12, pady=(2, 10))

        def _toggle_cm_settings():
            self.toggle_camera_mouse()
            cm_status_badge.configure(text="[ACTIVE]" if camera_mouse_controller.is_active else "[OFF]", text_color="#10b981" if camera_mouse_controller.is_active else "#64748b")

        ctk.CTkButton(cm_btn_row, text="✋ Toggle Camera Mouse", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), fg_color="#0284c7", hover_color="#0369a1", text_color="#ffffff", height=28, command=_toggle_cm_settings).pack(side="left", padx=(0, 8))

        lbl_cm_test_res = ctk.CTkLabel(card_cam_mouse, text="", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8")
        lbl_cm_test_res.pack(anchor="w", padx=12, pady=(0, 4))

        def _test_cm_offline():
            diag = camera_mouse_controller.get_diagnostics()
            if diag["model_exists"]:
                lbl_cm_test_res.configure(text=f"✓ Model verified offline: {os.path.basename(diag['model_path'])} | Resolution: {diag['resolution']} | CPU: 2-Core Optimized", text_color="#10b981")
            else:
                lbl_cm_test_res.configure(text=f"✕ Model asset missing at {diag['model_path']}", text_color="#ef4444")

        ctk.CTkButton(cm_btn_row, text="🔍 Test Offline Tracker", font=ctk.CTkFont(family="Consolas", size=11), fg_color="#1e293b", hover_color="#334155", text_color="#38bdf8", height=28, command=_test_cm_offline).pack(side="left")

        # Live Screen card
        card_scr = ctk.CTkFrame(scroll_hw, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_scr.pack(fill="x", pady=6)
        ctk.CTkLabel(card_scr, text="👁️ Live Screen Perception", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(card_scr, text=f"• Current Observation Mode: {live_screen_manager.mode}\n• In-Memory Capture: Active (0 Disk Writes)", font=ctk.CTkFont(family="Consolas", size=11), text_color="#94a3b8", justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        ctk.CTkButton(card_scr, text="Toggle Live Screen Mode", font=ctk.CTkFont(family="Consolas", size=11), fg_color="#1e293b", hover_color="#334155", text_color="#38bdf8", height=28, command=self.toggle_live_screen).pack(anchor="w", padx=12, pady=(0, 10))

        # ====================================================
        # TAB 5: PERMISSIONS DASHBOARD
        # ====================================================
        scroll_perms = tab_frames["Permissions"]

        ctk.CTkLabel(scroll_perms, text="Capability Permissions", font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=8, pady=(4, 2))
        ctk.CTkLabel(scroll_perms, text="Independently enable or revoke permissions. Revoked features are blocked at runtime across all tools.", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8").pack(anchor="w", padx=8, pady=(0, 8))

        perms = VedaConfig.get_permissions()
        perm_items = [
            ("computer_control", "🖥️ Computer Control", "Allows window inspection, app launching, mouse/keyboard and Windows UI Automation."),
            ("file_access", "📁 File Access", "Allows filesystem read/write/edit/search within the user directory boundary."),
            ("live_screen", "👁️ Live Screen Observation", "Allows temporary in-RAM desktop perception (0 disk writes)."),
            ("microphone", "🎙️ Microphone Access", "Allows speech-to-text recognition and voice conversation."),
            ("camera", "📷 Camera Access", "Allows webcam frames in RAM for physical object inspection."),
            ("gemini_network", "🌐 Cloud Reasoning Connection", "Allows high-level multimodal reasoning with Google GenAI.")
        ]

        for p_key, p_name, p_desc in perm_items:
            pf = ctk.CTkFrame(scroll_perms, fg_color="#0f172a", corner_radius=8)
            pf.pack(fill="x", pady=4, padx=4)

            p_left = ctk.CTkFrame(pf, fg_color="transparent")
            p_left.pack(side="left", fill="both", expand=True, padx=10, pady=8)
            ctk.CTkLabel(p_left, text=p_name, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#f8fafc").pack(anchor="w")
            ctk.CTkLabel(p_left, text=p_desc, font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8", wraplength=440, justify="left").pack(anchor="w")

            psw = ctk.CTkSwitch(pf, text="", width=45)
            if perms.get(p_key, False):
                psw.select()
            else:
                psw.deselect()
            psw.configure(command=lambda k=p_key, s=psw: self._on_perm_toggle(k, s))
            psw.pack(side="right", padx=12, pady=8)

        elev_f = ctk.CTkFrame(scroll_perms, fg_color="#0f172a", corner_radius=8)
        elev_f.pack(fill="x", pady=4, padx=4)
        e_left = ctk.CTkFrame(elev_f, fg_color="transparent")
        e_left.pack(side="left", padx=10, pady=8)
        ctk.CTkLabel(e_left, text="⚙️ Elevated Operations", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#f8fafc").pack(anchor="w")
        ctk.CTkLabel(e_left, text="Runs administrator tasks via native Windows UAC prompts.", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8").pack(anchor="w")
        ctk.CTkLabel(elev_f, text="● Ask Every Time", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#38bdf8").pack(side="right", padx=12)

        # ====================================================
        # TAB 6: AUTOMATIONS (Natural Language Windows Automation)
        # ====================================================
        scroll_auto = tab_frames["Automations"]

        ctk.CTkLabel(scroll_auto, text="Natural-Language Windows Automations", font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=8, pady=(4, 2))
        ctk.CTkLabel(scroll_auto, text="Real-time condition monitoring with edge-triggered hysteresis (triggers once without spamming).", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8").pack(anchor="w", padx=8, pady=(0, 6))

        # Real Windows Live Metrics Bar
        metrics_bar = ctk.CTkFrame(scroll_auto, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        metrics_bar.pack(fill="x", pady=4)
        
        curr_state = self.automation_engine.get_system_state()
        bat_str = f"{curr_state['battery_percent']}% ({'Plugged' if curr_state['battery_plugged'] else 'Battery'})" if curr_state['battery_percent'] is not None else "No Battery"
        wifi_str = "Connected" if curr_state['network_connected'] else "Disconnected"
        cpu_str = f"{curr_state['cpu_percent']}%"

        lbl_metrics = ctk.CTkLabel(
            metrics_bar,
            text=f"Live Windows State:  🔋 Battery: {bat_str}  |  ⚡ CPU: {cpu_str}  |  📶 Network: {wifi_str}",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color="#10b981"
        )
        lbl_metrics.pack(padx=10, pady=6)

        # Container for automation cards
        auto_cards_frame = ctk.CTkFrame(scroll_auto, fg_color="transparent")
        auto_cards_frame.pack(fill="both", expand=True, pady=4)

        def _refresh_automation_cards():
            for w in auto_cards_frame.winfo_children():
                w.destroy()

            rules = self.automation_engine.list_rules()
            if not rules:
                ctk.CTkLabel(auto_cards_frame, text="No active automation rules. Speak or type conditions to create them,\ne.g., 'Jab meri battery 30% ho jaye to mujhe bata dena'", font=ctk.CTkFont(family="Consolas", size=11), text_color="#64748b", justify="center").pack(pady=20)
                return

            for rule in rules:
                rf = ctk.CTkFrame(auto_cards_frame, fg_color="#0f172a", corner_radius=8, border_width=1, border_color="#1e293b")
                rf.pack(fill="x", pady=4, padx=2)

                rh = ctk.CTkFrame(rf, fg_color="transparent")
                rh.pack(fill="x", padx=10, pady=(6, 2))

                ctk.CTkLabel(rh, text=f"⚡ {rule.name}", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#38bdf8").pack(side="left")
                st_color = "#10b981" if rule.enabled else "#64748b"
                ctk.CTkLabel(rh, text="[ACTIVE]" if rule.enabled else "[PAUSED]", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color=st_color).pack(side="right")

                cond_txt = f"Condition: {rule.metric.upper()} {rule.operator} {rule.threshold}  |  Triggered: {'YES (armed)' if rule.is_triggered else 'NO (ready)'}\nAlert: {rule.alert_message}"
                ctk.CTkLabel(rf, text=cond_txt, font=ctk.CTkFont(family="Consolas", size=10), text_color="#cbd5e1", justify="left").pack(anchor="w", padx=10, pady=(2, 6))

                rb_bar = ctk.CTkFrame(rf, fg_color="transparent")
                rb_bar.pack(fill="x", padx=10, pady=(0, 6))

                def _toggle(rid=rule.rule_id):
                    self.automation_engine.toggle_rule(rid)
                    _refresh_automation_cards()

                def _delete(rid=rule.rule_id):
                    self.automation_engine.delete_rule(rid)
                    _refresh_automation_cards()

                def _test(rid=rule.rule_id):
                    self.automation_engine.test_rule(rid)

                btn_tog = ctk.CTkButton(rb_bar, text="Pause" if rule.enabled else "Enable", width=60, height=22, font=ctk.CTkFont(family="Consolas", size=10), fg_color="#1e293b", hover_color="#334155", command=_toggle)
                btn_tog.pack(side="left", padx=(0, 6))

                btn_tst = ctk.CTkButton(rb_bar, text="Test Trigger", width=80, height=22, font=ctk.CTkFont(family="Consolas", size=10), fg_color="#0284c7", hover_color="#0369a1", command=_test)
                btn_tst.pack(side="left", padx=(0, 6))

                btn_del = ctk.CTkButton(rb_bar, text="Delete", width=55, height=22, font=ctk.CTkFont(family="Consolas", size=10), fg_color="#7f1d1d", hover_color="#991b1b", command=_delete)
                btn_del.pack(side="right")

        _refresh_automation_cards()

        # Add rule directly via natural language entry in modal
        card_add_auto = ctk.CTkFrame(scroll_auto, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        card_add_auto.pack(fill="x", pady=8)
        ctk.CTkLabel(card_add_auto, text="Add Automation via Natural Language", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=10, pady=(8, 4))

        row_nl = ctk.CTkFrame(card_add_auto, fg_color="transparent")
        row_nl.pack(fill="x", padx=10, pady=(0, 8))

        entry_nl = ctk.CTkEntry(row_nl, placeholder_text="e.g., Jab battery 20% se kam ho to bol dena...", font=ctk.CTkFont(family="Consolas", size=11), fg_color="#05080e", border_color="#1e293b")
        entry_nl.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _on_add_nl():
            txt = entry_nl.get().strip()
            if not txt:
                return
            rule = self.automation_engine.parse_natural_language_rule(txt)
            if rule:
                self.automation_engine.create_rule(rule)
                entry_nl.delete(0, "end")
                _refresh_automation_cards()
            else:
                entry_nl.delete(0, "end")
                entry_nl.insert(0, "Could not extract rule. Try: 'battery below 20%'")

        ctk.CTkButton(row_nl, text="+ Create Rule", width=95, height=28, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), fg_color="#059669", hover_color="#047857", command=_on_add_nl).pack(side="right")

        # ====================================================
        # TAB 7: CONVERSATION HISTORY
        # ====================================================
        scroll_hist = tab_frames["History"]

        hist_h = ctk.CTkFrame(scroll_hist, fg_color="transparent")
        hist_h.pack(fill="x", padx=4, pady=(4, 8))

        ctk.CTkLabel(hist_h, text="Conversation History", font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color="#38bdf8").pack(side="left")

        def _clear_chat():
            self._clear_history(settings_win)

        ctk.CTkButton(hist_h, text="Clear History", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), fg_color="#7f1d1d", hover_color="#991b1b", height=24, width=90, command=_clear_chat).pack(side="right")

        history_items = VedaConfig.load_history()
        if not history_items:
            ctk.CTkLabel(scroll_hist, text="No saved conversation history.", font=ctk.CTkFont(family="Consolas", size=11), text_color="#64748b").pack(pady=20)
        else:
            for item in reversed(history_items[-30:]):
                sender = item.get("sender", "assistant")
                txt = item.get("text", "")
                tag = item.get("action_tag", "")
                hf = ctk.CTkFrame(scroll_hist, fg_color="#0f172a" if sender == "assistant" else "#0369a1", corner_radius=6)
                hf.pack(fill="x", pady=3, padx=2)
                hdr = f"{'V.E.D.A.' if sender == 'assistant' else 'You'}"
                if tag:
                    hdr += f" [{tag}]"
                ctk.CTkLabel(hf, text=hdr, font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color="#94a3b8").pack(anchor="w", padx=8, pady=(4, 0))
                ctk.CTkLabel(hf, text=txt, font=ctk.CTkFont(family="Consolas", size=11), text_color="#f8fafc", wraplength=540, justify="left").pack(anchor="w", padx=8, pady=(2, 6))

        # ====================================================
        # TAB 8: ABOUT
        # ====================================================
        scroll_about = tab_frames["About"]

        about_card = ctk.CTkFrame(scroll_about, fg_color="#080c14", corner_radius=8, border_width=1, border_color="#1e293b")
        about_card.pack(fill="x", pady=6)
        ctk.CTkLabel(about_card, text="◈ V.E.D.A. Desktop AI", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=12, pady=(12, 4))

        last_chk = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(production_updater.last_check_time)) if production_updater.last_check_time else "Never"
        info_str = (
            f"• Assistant:            V.E.D.A. (Virtual Executive Desktop Assistant)\n"
            f"• Installed Version:    {VERSION}\n"
            f"• Build Number:         {BUILD}\n"
            f"• Update Channel:       {RELEASE_CHANNEL}\n"
            f"• Update Status:        {production_updater.state.replace('_', ' ')}\n"
            f"• Last Update Check:    {last_chk}\n"
            f"• GitHub Repository:    shreyasbro/V.E.D.A\n"
            f"• Created by:           Shreyas\n"
            f"• Architecture:         Autonomous Agent Loop with User-Owned AI Providers\n"
            f"• Security Boundary:    Windows DPAPI Encrypted Local Storage"
        )
        lbl_about_info = ctk.CTkLabel(about_card, text=info_str, font=ctk.CTkFont(family="Consolas", size=11), text_color="#cbd5e1", justify="left")
        lbl_about_info.pack(anchor="w", padx=12, pady=(0, 10))

        about_act_row = ctk.CTkFrame(about_card, fg_color="transparent")
        about_act_row.pack(fill="x", padx=12, pady=(0, 12))

        lbl_about_msg = ctk.CTkLabel(about_act_row, text="", font=ctk.CTkFont(family="Consolas", size=10), text_color="#38bdf8")
        lbl_about_msg.pack(side="left", fill="x", expand=True)

        def _on_about_chk_updates():
            lbl_about_msg.configure(text="Checking for updates on GitHub...", text_color="#38bdf8")
            def _w():
                res = production_updater.check_for_updates()
                def _d():
                    if not settings_win.winfo_exists():
                        return
                    chk_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(production_updater.last_check_time)) if production_updater.last_check_time else "Never"
                    new_info = (
                        f"• Assistant:            V.E.D.A. (Virtual Executive Desktop Assistant)\n"
                        f"• Installed Version:    {VERSION}\n"
                        f"• Build Number:         {BUILD}\n"
                        f"• Update Channel:       {RELEASE_CHANNEL}\n"
                        f"• Update Status:        {production_updater.state.replace('_', ' ')}\n"
                        f"• Last Update Check:    {chk_time}\n"
                        f"• GitHub Repository:    shreyasbro/V.E.D.A\n"
                        f"• Created by:           Shreyas\n"
                        f"• Architecture:         Autonomous Agent Loop with User-Owned AI Providers\n"
                        f"• Security Boundary:    Windows DPAPI Encrypted Local Storage"
                    )
                    lbl_about_info.configure(text=new_info)
                    self._refresh_notification_badge()
                    if res.get("update_available"):
                        lbl_about_msg.configure(text=f"✓ Update available: v{res.get('latest_version')}", text_color="#10b981")
                    elif res.get("success"):
                        lbl_about_msg.configure(text="✓ V.E.D.A. is up to date with GitHub.", text_color="#10b981")
                    else:
                        lbl_about_msg.configure(text=f"✕ {res.get('error', 'Check failed')}", text_color="#ef4444")
                self.after(0, _d)
            threading.Thread(target=_w, daemon=True).start()

        ctk.CTkButton(
            about_act_row,
            text="🔄 Check for Updates",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            height=26,
            command=_on_about_chk_updates
        ).pack(side="right")

        # Bottom Bar of Settings Window: Quick Reload & Close
        bot_bar = ctk.CTkFrame(root_box, fg_color="transparent", height=42)
        bot_bar.pack(fill="x", padx=4, pady=(6, 0))

        ctk.CTkButton(
            bot_bar,
            text="⚡ Reload V.E.D.A. (Apply Changes)",
            width=210,
            height=32,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=self.restart_veda
        ).pack(side="left")

        ctk.CTkButton(
            bot_bar,
            text="Done",
            width=80,
            height=32,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=_on_settings_close
        ).pack(side="right")

        # Set initial tab
        target_tab = initial_tab or "General"
        switch_to_tab(target_tab)

    def _on_autostart_toggle(self):
        is_enabled = bool(self.switch_autostart.get())
        VedaConfig.set_start_with_windows(is_enabled)

    # ==========================================
    # 1. ONE-TIME WELCOME / FIRST-RUN SCREEN
    # ==========================================
    def open_first_run_onboarding(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Welcome to V.E.D.A.")
        modal.geometry("680x640")
        modal.minsize(600, 520)
        modal.configure(fg_color="#07090e")
        modal.attributes("-topmost", True)

        box = ctk.CTkFrame(modal, fg_color="#0b101b", corner_radius=12, border_width=1, border_color="#1e293b")
        box.pack(fill="both", expand=True, padx=14, pady=14)

        # Welcome Hero Banner
        head_frame = ctk.CTkFrame(box, fg_color="transparent")
        head_frame.pack(fill="x", padx=16, pady=(18, 6))

        title_row = ctk.CTkFrame(head_frame, fg_color="transparent")
        title_row.pack(anchor="w")

        ctk.CTkLabel(
            title_row,
            text="◈ V.E.D.A.",
            font=ctk.CTkFont(family="Consolas", size=22, weight="bold"),
            text_color="#38bdf8"
        ).pack(side="left")

        ctk.CTkLabel(
            title_row,
            text=" — Virtual Executive Desktop Assistant",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color="#94a3b8"
        ).pack(side="left", padx=(6, 0))

        subtitle = ctk.CTkLabel(
            head_frame,
            text="Your intelligent desktop assistant for voice, screen, camera, files and Windows control.",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color="#cbd5e1",
            wraplength=620,
            justify="left"
        )
        subtitle.pack(anchor="w", pady=(6, 0))

        # Fixed Bottom Action Area with [ Get Started ]
        bottom_frame = ctk.CTkFrame(box, fg_color="transparent")
        bottom_frame.pack(side="bottom", fill="x", padx=16, pady=14)

        btn_finish = ctk.CTkButton(
            bottom_frame,
            text="Get Started",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            height=42,
            corner_radius=8,
            command=lambda: self._finish_onboarding(modal)
        )
        btn_finish.pack(fill="x")

        # Scrollable Capabilities Grid
        scroll = ctk.CTkScrollableFrame(box, fg_color="#080c14", corner_radius=8)
        scroll.pack(fill="both", expand=True, padx=14, pady=6)

        capabilities_list = [
            ("🎙️ Voice Assistant", "Real-time, low-latency conversational AI supporting natural English, Hindi, and Hinglish with Microsoft Ravi Neural voice synthesis and instant barge-in."),
            ("👁️ Live Screen Understanding", "In-RAM visual perception of your desktop or active window. V.E.D.A. understands what you're working on, detects errors, and answers visual queries without screen recording."),
            ("📷 Webcam / Camera Vision", "Real-time webcam integration with live camera preview. Point physical objects or papers at your camera for instant multimodal inspection."),
            ("🖥️ Windows Automation & Control", "Launch and focus applications, manage windows, click buttons semantically, and type text directly via Windows UI Automation."),
            ("📁 Filesystem Operations", "Create, edit, inspect, search, and manage files under the Windows user security model with zero intrusive terminal popups."),
            ("🌐 Advanced Gemini Intelligence", "Powered by Google GenAI for deep multimodal reasoning, planning, coding, and autonomous workflow execution.")
        ]

        for cap_title, cap_desc in capabilities_list:
            card = ctk.CTkFrame(scroll, fg_color="#0f172a", corner_radius=8)
            card.pack(fill="x", pady=5, padx=6)
            ctk.CTkLabel(
                card,
                text=cap_title,
                font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                text_color="#38bdf8"
            ).pack(anchor="w", padx=12, pady=(8, 2))
            ctk.CTkLabel(
                card,
                text=cap_desc,
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color="#cbd5e1",
                wraplength=570,
                justify="left"
            ).pack(anchor="w", padx=12, pady=(0, 8))

        # Privacy Notice Banner
        priv_banner = ctk.CTkFrame(scroll, fg_color="#05080e", corner_radius=8, border_width=1, border_color="#1e293b")
        priv_banner.pack(fill="x", pady=(8, 4), padx=6)
        ctk.CTkLabel(
            priv_banner,
            text="🔒 Privacy & Transparency Guarantee",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#10b981"
        ).pack(anchor="w", padx=12, pady=(6, 2))
        ctk.CTkLabel(
            priv_banner,
            text="All screen and camera perceptions are processed strictly in RAM with zero background disk writes. The camera and screen never activate silently. Every capability can be toggled anytime in 🛡️ Permissions Dashboard.",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#94a3b8",
            wraplength=570,
            justify="left"
        ).pack(anchor="w", padx=12, pady=(0, 6))

    def _finish_onboarding(self, modal):
        VedaConfig.mark_first_run_completed()
        modal.destroy()
        self.add_message("Welcome to V.E.D.A.! All systems are online and ready.", sender="assistant", animate=False)

    # ==========================================
    # 2. PERMISSIONS DASHBOARD
    # ==========================================
    def open_permissions_dashboard(self, icon=None, item=None):
        """Unified navigation: routes directly into the Permissions tab of Settings."""
        self.open_settings_modal(initial_tab="Permissions")

    def _open_permissions_dashboard_impl(self):
        dash = ctk.CTkToplevel(self)
        dash.title("V.E.D.A. — Permissions Dashboard")
        dash.geometry("580x560")
        dash.minsize(500, 420)
        dash.configure(fg_color="#07090e")
        dash.attributes("-topmost", True)

        box = ctk.CTkFrame(dash, fg_color="#0b101b", corner_radius=12, border_width=1, border_color="#1e293b")
        box.pack(fill="both", expand=True, padx=14, pady=14)

        # Fixed Header
        head_f = ctk.CTkFrame(box, fg_color="transparent")
        head_f.pack(fill="x", padx=16, pady=(16, 6))

        title = ctk.CTkLabel(
            head_f,
            text="Permissions Dashboard",
            font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
            text_color="#38bdf8"
        )
        title.pack(anchor="w")

        ctk.CTkLabel(
            head_f,
            text="Independently toggle capabilities. Disabled capabilities are blocked at runtime across all tools.",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#94a3b8",
            wraplength=520,
            justify="left"
        ).pack(anchor="w", pady=(2, 0))

        # Fixed Bottom Action Bar
        bottom_f = ctk.CTkFrame(box, fg_color="transparent")
        bottom_f.pack(side="bottom", fill="x", padx=16, pady=12)

        btn_close = ctk.CTkButton(
            bottom_f,
            text="Done",
            width=90,
            height=34,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=dash.destroy
        )
        btn_close.pack(side="right")

        # Scrollable Middle Content (smooth scrolling for all screen resolutions)
        scroll = ctk.CTkScrollableFrame(box, fg_color="#080c14", corner_radius=8)
        scroll.pack(fill="both", expand=True, padx=14, pady=6)

        perms = VedaConfig.get_permissions()

        toggles = [
            ("computer_control", "🖥️ Computer Control", "Allows window inspection, app launching, mouse/keyboard and UI Automation."),
            ("file_access", "📁 File Access", "Allows filesystem read/write/edit/search under user security boundary."),
            ("live_screen", "👁️ Live Screen Observation", "Allows temporary in-RAM desktop perception (0 disk writes)."),
            ("microphone", "🎙️ Microphone Access", "Allows speech-to-text recognition, voice input and Push-to-Talk."),
            ("camera", "📷 Camera Access", "Allows temporary webcam frames in RAM for physical object inspection."),
            ("gemini_network", "🌐 Gemini Network Connection", "Allows cloud reasoning and multimodal analysis.")
        ]

        switches = {}
        for key, name, desc in toggles:
            f = ctk.CTkFrame(scroll, fg_color="#0f172a", corner_radius=8)
            f.pack(fill="x", pady=4, padx=6)

            left_f = ctk.CTkFrame(f, fg_color="transparent")
            left_f.pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(left_f, text=name, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#f8fafc").pack(anchor="w")
            ctk.CTkLabel(left_f, text=desc, font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8", wraplength=380, justify="left").pack(anchor="w")

            sw = ctk.CTkSwitch(
                f,
                text="",
                width=45,
                command=lambda k=key: self._on_perm_toggle(k, switches[k])
            )
            if perms.get(key, False):
                sw.select()
            else:
                sw.deselect()
            sw.pack(side="right", padx=12, pady=8)
            switches[key] = sw

        # Elevated operations card
        elev_f = ctk.CTkFrame(scroll, fg_color="#0f172a", corner_radius=8)
        elev_f.pack(fill="x", pady=4, padx=6)
        elev_left = ctk.CTkFrame(elev_f, fg_color="transparent")
        elev_left.pack(side="left", padx=10, pady=8)
        ctk.CTkLabel(elev_left, text="⚙️ Elevated Operations", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#f8fafc").pack(anchor="w")
        ctk.CTkLabel(elev_left, text="Runs administrator tasks via native Windows UAC prompts.", font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8").pack(anchor="w")

        lbl_elev = ctk.CTkLabel(elev_f, text="● Ask Every Time", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#38bdf8")
        lbl_elev.pack(side="right", padx=12)

    def _on_perm_toggle(self, key: str, switch_widget):
        val = bool(switch_widget.get())
        VedaConfig.update_permission(key, val)
        # Synchronize live screen manager if toggled here
        if key == "live_screen":
            if not val:
                live_screen_manager.set_mode("OFF")
                self.btn_live_screen.configure(text="● SCREEN OFF", fg_color="#1e293b", text_color="#94a3b8")
            else:
                live_screen_manager.set_mode("LIVE")
                self.btn_live_screen.configure(text="● SCREEN ON", fg_color="#059669", text_color="#ffffff")

    # ==========================================
    # 3. DUAL-MODE MICROPHONE ENGINE
    # ==========================================
    def _handle_barge_in(self):
        """Instant barge-in: when user starts speaking, purge TTS playback immediately."""
        if tts_engine.is_speaking:
            tts_engine.stop()
            self.after(0, lambda: self.update_hearing_state("SPEECH_DETECTED"))

    def toggle_mic_mode(self):
        """Switches between '🎙 Always On' and '🎙 Mic Toggle'."""
        self._stop_all_mic_activity()

        if self.mic_mode == "mic_toggle":
            self.mic_mode = "always_on"
            self.btn_mic_mode.configure(text="🎙 Always On", text_color="#10b981")
            self.add_message("Switched microphone mode to: 🎙 Always On (Continuous VAD with barge-in).", sender="assistant", animate=False)
        else:
            self.mic_mode = "mic_toggle"
            self.btn_mic_mode.configure(text="🎙 Mic Toggle", text_color="#38bdf8")
            self.add_message("Switched microphone mode to: 🎙 Mic Toggle (Click to listen).", sender="assistant", animate=False)

        # Persist mode locally
        VedaConfig.update_setting("mic_mode", self.mic_mode)

    def toggle_mic_action(self):
        """Handles Mic button click according to current mode."""
        if not PermissionGuard.check_permission("microphone"):
            self.add_message("Permission Denied: Microphone Access is currently disabled. Enable it in 🛡️ Permissions.", sender="assistant", animate=False)
            return

        if self.mic_mode == "always_on":
            # In Always On mode, button toggles continuous streaming
            if microphone_subsystem.is_always_on:
                self._stop_all_mic_activity()
                self.update_hearing_state("MIC_OFF")
                self.add_message("Always-On listening paused.", sender="assistant", animate=False)
            else:
                self.update_hearing_state("MIC_READY")
                self.add_message("Always-On listening active. Speak anytime.", sender="assistant", animate=False)
                microphone_subsystem.start_always_on(
                    on_utterance=lambda payload: self.after(0, lambda: self._handle_voice_query(payload)),
                    is_busy_fn=lambda: self._is_agent_busy or tts_engine.is_speaking
                )
        else:
            # In Mic Toggle mode
            if microphone_subsystem.is_listening:
                self._stop_all_mic_activity()
                self.update_hearing_state("MIC_OFF")
            else:
                self.update_hearing_state("MIC_READY")
                threading.Thread(target=self._run_toggle_capture, daemon=True).start()

    def _stop_all_mic_activity(self):
        microphone_subsystem.stop_always_on()
        microphone_subsystem.stop_listening()
        self.update_hearing_state("MIC_OFF")
        if hasattr(self, "waveform"):
            self.waveform.set_level(0.0, "#38bdf8")

    def _run_toggle_capture(self):
        res = microphone_subsystem.listen_once_vad(timeout=7.0, phrase_time_limit=12.0)

        if hasattr(self, "waveform"):
            self.waveform.set_level(0.0, "#38bdf8")

        self.after(0, lambda: self.update_hearing_state("MIC_OFF"))

        if res.get("success"):
            self.after(0, lambda: self._handle_voice_query(res))
        else:
            err = res.get("error", "No speech detected.")
            diag = res.get("diagnostics", "")
            msg = f"Voice Input: {err}"
            if diag and "Speech: NO" not in diag:
                msg += f"\n[{diag}]"
            self.after(0, lambda: self.add_message(msg, sender="assistant", animate=False))

    def _handle_voice_query(self, query_data: Any):
        if isinstance(query_data, dict):
            text = query_data.get("clean_text") or query_data.get("text") or query_data.get("raw_text") or ""
            lang = query_data.get("language_mode", "ENGLISH")
        else:
            text = str(query_data)
            lang = detect_language(text)

        if not text.strip():
            return

        self.input_field.delete(0, "end")
        self.input_field.insert(0, text)
        self.send_request(language_mode=lang)


if __name__ == "__main__":
    app = VedaApp()
    app.mainloop()
