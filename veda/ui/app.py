import os
import threading
import time
from typing import Optional
import customtkinter as ctk

from veda.tools.registry import ToolRegistry
from veda.providers.gemini_provider import GeminiProvider
from veda.providers.local_provider import LocalOfflineProvider
from veda.core.agent_loop import AgentLoop

class VedaApp(ctk.CTk):
    """
    V.E.D.A. — Virtual Executive Desktop Assistant
    Lightweight, fast-startup Windows desktop interface with chat stream,
    model status, and live tool action logging.
    """

    def __init__(self):
        super().__init__()

        # Window Appearance & Geometry (740x620)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("V.E.D.A. — Virtual Executive Desktop Assistant")
        self.geometry("740x620")
        self.minsize(700, 560)
        self.configure(fg_color="#090b10")

        # Initialize Tool Registry & Provider
        self.tool_registry = ToolRegistry()
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.gemini_provider = GeminiProvider(api_key=self.api_key)

        if self.gemini_provider.is_available():
            self.provider = self.gemini_provider
            self.provider_name = "Gemini 2.5 Flash"
        else:
            self.provider = LocalOfflineProvider()
            self.provider_name = "Local Offline Fallback"

        self.agent = AgentLoop(self.provider, self.tool_registry)
        self.abort_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

        self._build_header()
        self._build_chat_stream()
        self._build_input_dock()

        # Welcome message
        self.add_message(
            f"Hello! Main V.E.D.A. hoon (Virtual Executive Desktop Assistant).\n"
            f"Active Provider: {self.provider_name}.\n\n"
            f"Aap naturally baat kar sakte hain:\n"
            f"• 'What window is currently active?'\n"
            f"• 'What applications are currently open?'\n"
            f"• 'Open Notepad and type Hello from VEDA'\n"
            f"• 'Create a text file on my Desktop called VEDA-test.txt containing Agent test successful'\n"
            f"• 'Bhai notepad khol ke ye likh de: hello world'\n\n"
            f"Main Gemini tool-calling loop ke through actual Windows OS tasks perform karunga!",
            sender="assistant"
        )

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="#10141e", height=56, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        brand_frame = ctk.CTkFrame(header, fg_color="transparent")
        brand_frame.pack(side="left", padx=18, pady=10)

        title = ctk.CTkLabel(
            brand_frame,
            text="V.E.D.A.",
            font=ctk.CTkFont(family="Consolas", size=18, weight="bold"),
            text_color="#38bdf8"
        )
        title.pack(side="left")

        sep = ctk.CTkLabel(brand_frame, text=" | ", font=ctk.CTkFont(size=14), text_color="#475569")
        sep.pack(side="left")

        self.lbl_model = ctk.CTkLabel(
            brand_frame,
            text=f"MODEL: {self.provider_name.upper()}",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color="#94a3b8"
        )
        self.lbl_model.pack(side="left")

        # Dynamic Status Badge
        self.status_pill = ctk.CTkButton(
            header,
            text="● IDLE",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#ffffff",
            fg_color="#10b981",
            hover=False,
            height=28,
            corner_radius=14
        )
        self.status_pill.pack(side="right", padx=18)

    def _build_chat_stream(self):
        self.chat_frame = ctk.CTkScrollableFrame(self, fg_color="#06080d")
        self.chat_frame.pack(fill="both", expand=True, padx=16, pady=(10, 8))

    def _build_input_dock(self):
        dock = ctk.CTkFrame(self, fg_color="#10141e", corner_radius=10, height=58)
        dock.pack(fill="x", padx=16, pady=(0, 14))
        dock.pack_propagate(False)

        dock_content = ctk.CTkFrame(dock, fg_color="transparent")
        dock_content.pack(fill="both", expand=True, padx=10, pady=8)

        self.input_field = ctk.CTkEntry(
            dock_content,
            placeholder_text="Tell V.E.D.A. what to do (e.g. 'Open notepad and write Hello from VEDA')...",
            placeholder_text_color="#64748b",
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color="#06080d",
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
            width=75,
            height=40,
            command=self.send_request,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            corner_radius=6
        )
        self.btn_send.pack(side="left", padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            dock_content,
            text="Stop",
            width=65,
            height=40,
            command=self.abort_request,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            corner_radius=6
        )
        self.btn_stop.pack(side="right")

    def add_message(self, text: str, sender: str = "assistant", action_pill: Optional[str] = None):
        is_user = sender == "user"
        frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        frame.pack(fill="x", pady=4)

        container = ctk.CTkFrame(frame, fg_color="transparent")
        container.pack(side="right" if is_user else "left", padx=8)

        if action_pill and not is_user:
            pill = ctk.CTkLabel(
                container,
                text=action_pill,
                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
                text_color="#38bdf8",
                fg_color="#1e293b",
                corner_radius=6,
                padx=8,
                pady=2
            )
            pill.pack(anchor="w", pady=(0, 2))

        bubble = ctk.CTkLabel(
            container,
            text=text,
            fg_color="#1d4ed8" if is_user else "#1f2937",
            text_color="#ffffff",
            corner_radius=12,
            wraplength=480,
            justify="left",
            font=ctk.CTkFont(size=13),
            padx=14,
            pady=10
        )
        bubble.pack(side="right" if is_user else "left")

        self.after(50, lambda: self.chat_frame._parent_canvas.yview_moveto(1.0))

    def update_status(self, text: str, color: str = "#10b981"):
        self.after(0, lambda: self.status_pill.configure(text=f"● {text}", fg_color=color))

    def send_request(self):
        user_text = self.input_field.get().strip()
        if not user_text:
            return

        self.input_field.delete(0, "end")
        self.add_message(user_text, sender="user")

        self.abort_event.clear()
        self.worker_thread = threading.Thread(
            target=self._run_agent_thread,
            args=(user_text,),
            daemon=True
        )
        self.worker_thread.start()

    def abort_request(self):
        self.abort_event.set()
        self.update_status("STOPPED", "#f59e0b")
        self.add_message("[Task sequence aborted by user]", sender="assistant")

    def _run_agent_thread(self, user_text: str):
        result = self.agent.run(
            user_request=user_text,
            status_callback=lambda s, c: self.update_status(s, c),
            action_callback=lambda a: self.after(0, lambda: self.add_message(f"Tool executed: {a}", sender="assistant", action_pill=a)),
            abort_event=self.abort_event
        )
        self.after(0, lambda: self.add_message(result, sender="assistant"))
        self.update_status("IDLE", "#10b981")

if __name__ == "__main__":
    app = VedaApp()
    app.mainloop()
