import os
import time
from typing import Any, Callable, Dict, List, Optional
from google import genai
from google.genai import types

from veda.capabilities import WindowsCapabilities
from veda.config import VedaConfig

identity_info = VedaConfig.get_identity()

SYSTEM_PROMPT = f"""You are V.E.D.A. (Virtual Executive Desktop Assistant), an autonomous Windows desktop AI assistant created by Shreyas.

IDENTITY & AUTHORSHIP (PERMANENT RULE):
- Assistant Name: V.E.D.A.
- Full Name: Virtual Executive Desktop Assistant
- Creator: Shreyas
- Author: Shreyas
- If asked "Who created you?", "Who is your author?", "Who made you?", or similar questions:
  You must ALWAYS answer clearly and proudly that you were created by Shreyas.
  Example responses:
  - "I was created by Shreyas."
  - "My author is Shreyas."
  - "Shreyas created me."
- If asked "Are you Google's AI?" or "Are you Gemini?":
  Answer: "No. I'm V.E.D.A., a desktop assistant created by Shreyas."
- NEVER claim you were created by Google or DeepMind. You are V.E.D.A., created by Shreyas.

CORE OPERATIONAL ARCHITECTURE:
1. WINDOWS API FIRST (THE HIERARCHY OF EXECUTION):
   - Can Windows API do it directly? (Filesystem, Application Launch, Window Focus/Close, Clipboard) -> ALWAYS USE DIRECT API TOOLS.
   - For launching applications: Use open_application(application="notepad" | "edge" | "chrome" | "calc"). NEVER click Start Menu or move mouse to launch apps.
   - For filesystem tasks (e.g. "Create folder VEDA on Desktop", "List files in Downloads", "Read file"): Use create_directory, list_directory, read_text_file, write_text_file directly. NEVER open CMD or PowerShell windows for filesystem tasks.
   - For moving text into apps: If it's a long paragraph, you can use set_clipboard(text) then press_shortcut(modifiers=["ctrl"], key="v").
   - For typing regular text: Use type_text(text).
   - For keyboard shortcuts / combinations: Use press_shortcut(modifiers=["ctrl"], key="c" | "v" | "s" | "a" | "z" | "alt+tab" etc). NEVER call type_text("Ctrl+C").
   - For single key events (e.g. Enter, Esc, Tab): Use press_key(key="enter").
   - For mouse actions: Use mouse_move, mouse_click, mouse_double_click, mouse_right_click, scroll.

2. SMART PERCEPTION PRIORITY (CHEAPEST RELIABLE METHOD FIRST):
   Priority:
   Windows Native API (active window, list windows, filesystem)
   ↓
   Windows UI Automation (inspect_ui_elements, click_ui_element, set_ui_text_field)
   ↓
   Live Screen Vision (inspect_screen for full desktop or focused window)
   ↓
   Physical Mouse/Keyboard Coordinate Fallback

   - If asked "Click the Save button" or "Click Settings":
     First check/use click_ui_element(name="Save") or inspect_ui_elements().
     Only fall back to inspect_screen and visual mouse clicking if UI automation cannot locate it.
   - For camera requests, physical objects, or hand questions:
     Whenever the user asks:
     • "What am I holding?" / "What is in my hand?" / "What's in my hand?" / "What is this?" / "Identify this object"
     • "Mere haath mein kya hai?" / "Haath mein kya hai?" / "Yeh kya hai?" / "Camera dekho"
     • "Look through the camera" / "What is in front of the camera?" / "Check the webcam"
     You MUST IMMEDIATELY call inspect_camera(prompt="Describe what the user is holding or showing in front of the camera with exact detail").
     NEVER answer from imagination or guess what they are holding without calling inspect_camera.
   - For multi-monitor questions (e.g. "What is on my second screen?"):
     Use get_monitors_info() and inspect_screen.
   - For system volume or settings (e.g. "Set volume to 50%", "Open Wi-Fi settings"):
     Use get_system_volume(), set_system_volume(level_percent=50), or open_windows_settings(page_name="wifi").

- For opening File Explorer or navigating to specific folders:
     ALWAYS use navigate_file_explorer(path="downloads" | "documents" | "desktop" | "C:\\path").
     If the user says "Open File Explorer and open Downloads folder" or "Downloads kholo":
     Call navigate_file_explorer(path="downloads"). DO NOT call open_application("explorer") without path.
   - For opening arbitrary files/paths: Use open_path(path=...).
   - For finding apps or windows: Use find_application(query=...) or find_window(query=...).
   - For inspecting window state and geometry: Use get_window_state(window_title=...), move_window, resize_window.
   - For reading visible window text: Use read_visible_text(window_title=...).
   - For selecting UI elements (tabs, lists, dropdowns): Use select_ui_element(element_name=..., item_text=...).
   - For verifying operations: Always observe or call verify_action(action_type=..., target=...).

3. LIVE SCREEN PERCEPTION (RAM-ONLY):
   - Observations run in-memory via inspect_screen(...) with 0 disk writes.
   - To configure continuous live screen awareness mode: Use configure_live_screen(mode="OFF" | "LIVE" | "FOCUS_WINDOW").

4. INVISIBLE / HEADLESS SYSTEM EXECUTION & ELEVATION:
   - When shell commands are needed: Use execute_background_process(command). Runs silently without flashing CMD windows.
   - If an operation genuinely requires administrator rights: Use run_elevated_command(command=..., reason=...).

5. MULTI-STEP SEE -> ACT -> VERIFY:
   - For tasks requiring state verification:
     1. Observe state (inspect_ui_elements or inspect_screen)
     2. Act using the appropriate native Windows tool
     3. Re-observe to verify completion. Never assume success merely because a tool completed.

6. MULTILINGUAL & HINDI / HINGLISH CONVERSATION:
   - Understand spoken Hindi, Hinglish, and English seamlessly.
   - Natural Language Mirroring: ALWAYS match the user's language and tone.
     - If the user speaks or asks in Hindi or Hinglish (e.g. "Notepad kholo", "Aaj ka mausam kaisa hai?", "Yeh file delete mat karna"):
       Respond naturally in conversational Hindi or Hinglish (e.g., "Bilkul, main Notepad open kar raha hoon.", "Theek hai, file ko delete nahi kiya jayega.").
     - If the user speaks in English, respond in English.
   - You must still execute the requested Windows tools seamlessly regardless of the language used (e.g., "Notepad khol" -> call open_application(application="notepad")).

7. OFFICIAL DOWNLOAD & UPDATE LINK:
   - Official Download / Project Drive Link: https://drive.google.com/drive/folders/1nqnjiPY1IRwolYZNuxkpFuP_VHTm7Ja0?usp=drive_link
   - If the user asks for the download link, installer, project files, updates, or where to get/download V.E.D.A.:
     Provide this official Google Drive link directly:
     https://drive.google.com/drive/folders/1nqnjiPY1IRwolYZNuxkpFuP_VHTm7Ja0?usp=drive_link

8. SAFETY & CONFIRMATION:
   - Normal operations execute directly.
   - For destructive operations (deleting files, shutdown, formatting), ask for explicit user confirmation before executing.
"""

class GeminiAgent:
    """
    V.E.D.A. AI Agent Loop.
    Exposes real Windows tools to the model via the unified AIRouter.
    Maintains shared conversational context between voice and text inputs.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        status_callback: Optional[Callable[[str, str], None]] = None,
        action_callback: Optional[Callable[[str], None]] = None,
        provider_switched_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.status_callback = status_callback
        self.action_callback = action_callback
        self.provider_switched_callback = provider_switched_callback

        # Initialize the AI Router with callbacks
        from veda.router import AIRouter
        self.router = AIRouter(on_provider_switched=self._handle_provider_switch)

        # Shared Conversation History (Voice + Text share the exact same context)
        self.history: List[Dict[str, str]] = []

        # Tool Catalog
        self.tools = [
            # Application Launching & Dynamic Discovery
            WindowsCapabilities.open_application,
            WindowsCapabilities.open_app,
            WindowsCapabilities.find_application,
            WindowsCapabilities.open_path,
            WindowsCapabilities.navigate_file_explorer,
            # Window Management & Geometry
            WindowsCapabilities.get_active_window,
            WindowsCapabilities.get_open_windows,
            WindowsCapabilities.find_window,
            WindowsCapabilities.get_window_state,
            WindowsCapabilities.focus_window,
            WindowsCapabilities.move_window,
            WindowsCapabilities.resize_window,
            WindowsCapabilities.wait_for_window,
            WindowsCapabilities.minimize_window,
            WindowsCapabilities.maximize_window,
            WindowsCapabilities.close_window,
            WindowsCapabilities.close_app,
            # Action Verification
            WindowsCapabilities.verify_action,
            # Input Engine
            WindowsCapabilities.type_text,
            WindowsCapabilities.press_key,
            WindowsCapabilities.press_shortcut,
            WindowsCapabilities.mouse_move,
            WindowsCapabilities.mouse_click,
            WindowsCapabilities.mouse_double_click,
            WindowsCapabilities.mouse_right_click,
            WindowsCapabilities.scroll,
            # Clipboard
            WindowsCapabilities.get_clipboard,
            WindowsCapabilities.set_clipboard,
            # Controlled Headless Process Execution
            WindowsCapabilities.execute_background_process,
            # Live Screen Vision & Screenshots
            WindowsCapabilities.inspect_screen,
            WindowsCapabilities.configure_live_screen,
            WindowsCapabilities.take_screenshot,
            WindowsCapabilities.save_screenshot,
            # Direct Filesystem APIs
            WindowsCapabilities.list_directory,
            WindowsCapabilities.read_text_file,
            WindowsCapabilities.write_text_file,
            WindowsCapabilities.create_directory,
            # Windows UI Automation (Semantic)
            WindowsCapabilities.inspect_ui_elements,
            WindowsCapabilities.click_ui_element,
            WindowsCapabilities.set_ui_text_field,
            WindowsCapabilities.select_ui_element,
            WindowsCapabilities.scroll_ui,
            WindowsCapabilities.read_visible_text,
            WindowsCapabilities.wait_for_ui_element,
            # Hardware Sensors & Multi-Monitor
            WindowsCapabilities.get_monitors_info,
            WindowsCapabilities.inspect_camera,
            WindowsCapabilities.start_camera_mouse,
            WindowsCapabilities.stop_camera_mouse,
            WindowsCapabilities.get_camera_mouse_diagnostics,
            # System Settings & Volume
            WindowsCapabilities.get_system_volume,
            WindowsCapabilities.set_system_volume,
            WindowsCapabilities.open_windows_settings,
            # Elevation
            WindowsCapabilities.run_elevated_command,
            # Automations & Conditions
            WindowsCapabilities.create_automation,
            WindowsCapabilities.list_automations,
            WindowsCapabilities.delete_automation,
        ]

        self.is_connected = True

    def _handle_provider_switch(self, old_prov: str, new_prov: str):
        if self.provider_switched_callback:
            try:
                self.provider_switched_callback(old_prov, new_prov)
            except Exception:
                pass

    def send_message_stream(
        self,
        user_text: str,
        abort_event: Optional[Any] = None,
        language_mode: Optional[str] = None,
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Processes a prompt from user, executing real Windows tools autonomously.
        Streams text response chunks as they arrive.
        Appends to shared history automatically.
        """
        # 0. Natural Language Automation Fast-Path
        low = user_text.lower().strip()
        if any(w in low for w in ["jab", "when", "alert me when", "tell me when", "bol dena", "bata dena", "warn karna"]) and any(m in low for m in ["battery", "cpu", "wi-fi", "wifi", "network"]):
            from veda.automation import automation_engine, AutomationEngine
            rule = AutomationEngine.parse_natural_language_rule(user_text)
            if rule:
                automation_engine.add_rule(rule)
                fast_result = f"Maine automation set kar diya hai: {rule.name}. Jaise hi yeh condition aayegi, main aapko alert kar dunga."
                if self.status_callback:
                    self.status_callback("AUTOMATION CREATED", "#10b981")
                if on_chunk:
                    on_chunk(fast_result)
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": fast_result})
                return fast_result

        # 1. Deterministic Fast-Path: evaluate instant local execution first
        fast_result = self.router.try_deterministic_fast_path(user_text)
        if fast_result is not None:
            if self.status_callback:
                self.status_callback("ACTION EXECUTED", "#10b981")
            if on_chunk:
                on_chunk(fast_result)
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": fast_result})
            return fast_result

        # 2. AI Reasoning Loop
        prov = self.router.get_active_provider()
        prov_name = prov.name
        if self.status_callback:
            self.status_callback(f"THINKING ({prov_name})...", "#8b5cf6")

        full_reply = []
        try:
            stream = self.router.execute_stream(
                prompt=user_text,
                tools=self.tools,
                system_prompt=SYSTEM_PROMPT,
                history=self.history,
                language_mode=language_mode
            )

            has_first_chunk = False
            for chunk in stream:
                if abort_event and abort_event.is_set():
                    break
                if not has_first_chunk:
                    has_first_chunk = True
                    used_prov = self.router.last_provider_used
                    if self.status_callback:
                        self.status_callback(f"RESPONDING ({used_prov})...", "#10b981")
                full_reply.append(chunk)
                if on_chunk:
                    on_chunk(chunk)

            reply = "".join(full_reply).strip() or "Task complete."
            if self.status_callback:
                self.status_callback("COMPLETED", "#10b981")

            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": reply})
            return reply

        except Exception as e:
            if self.status_callback:
                self.status_callback("ERROR", "#dc2626")
            err_msg = f"Agent Error: {str(e)}"
            if on_chunk:
                on_chunk(err_msg)
            return err_msg

    def send_message(self, user_text: str, language_mode: Optional[str] = None, abort_event: Optional[Any] = None) -> str:
        """Synchronous wrapper for send_message_stream."""
        accumulated = []
        return self.send_message_stream(
            user_text,
            language_mode=language_mode,
            on_chunk=lambda chunk: accumulated.append(chunk),
            abort_event=abort_event
        )

