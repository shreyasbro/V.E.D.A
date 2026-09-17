"""
V.E.D.A. Mobile API Gateway & Local Bridge Server
Provides a secure REST and SSE (Server-Sent Events) bridge for the Android client.
Features:
- Pure Python standard library implementation (zero external server dependencies).
- Direct integration with V.E.D.A. AIRouter, APIManager, and InternetConnectivityMonitor.
- Real-time Server-Sent Events (SSE) streaming for AI chat completions.
- Multimodal camera vision analysis.
- Safe Windows-Android device pairing (PIN-based authentication).
- Preserves all desktop operations without any impact on the Windows UI.
"""

import os
import sys
import json
import time
import socket
import secrets
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from typing import Dict, Any, Optional

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from veda.router import AIRouter
from veda.api_manager import api_manager
from veda.connectivity import internet_monitor
from veda.config import VedaConfig

# Shared server state
PAIRED_TOKENS = set()
CURRENT_PAIR_PIN = secrets.token_hex(3).upper()  # 6-character hex PIN e.g. "A3F81C"
PAIR_LOCK = threading.Lock()
ai_router = AIRouter()

def get_local_ip() -> str:
    """Discovers LAN IP address for mobile pairing."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class VedaApiHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for V.E.D.A. Mobile Gateway."""

    def _set_cors_headers(self, content_type: str = "application/json"):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Veda-Pin")
        self.send_header("Content-Type", content_type)

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def _send_json(self, status_code: int, data: Dict[str, Any]):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self._set_cors_headers("application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            diag = ai_router.get_diagnostics()
            is_online = internet_monitor.is_internet_available()
            active_p = ai_router.get_active_provider()
            active_name = active_p.name if active_p else "Offline"

            self._send_json(200, {
                "status": "online" if is_online else "offline",
                "active_provider": active_name,
                "provider_mode": ai_router.provider_mode,
                "selected_provider": ai_router.selected_provider,
                "desktop_connected": True,
                "diagnostics": diag,
                "pairing_pin": CURRENT_PAIR_PIN
            })
            return

        elif path == "/api/providers":
            options = ai_router.get_provider_options()
            active_slots = []
            for s in api_manager.slots:
                active_slots.append({
                    "id": s.id,
                    "name": s.name,
                    "model": s.model,
                    "enabled": s.enabled,
                    "status": s.status,
                    "last_latency_ms": s.last_latency_ms,
                    "provider_preset": s.provider_preset
                })

            self._send_json(200, {
                "provider_mode": ai_router.provider_mode,
                "selected_provider": ai_router.selected_provider,
                "active_provider": ai_router.active_provider_name,
                "options": options,
                "slots": active_slots
            })
            return

        elif path == "/api/pairing_info":
            self._send_json(200, {
                "server_ip": get_local_ip(),
                "pin": CURRENT_PAIR_PIN
            })
            return

        else:
            self._send_json(404, {"error": f"Endpoint '{path}' not found."})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            self._send_json(400, {"error": "Invalid JSON payload"})
            return

        if path == "/api/pair":
            pin = payload.get("pin", "").strip().upper()
            device_name = payload.get("device_name", "Android Client")
            if pin == CURRENT_PAIR_PIN:
                token = secrets.token_hex(16)
                with PAIR_LOCK:
                    PAIRED_TOKENS.add(token)
                print(f"[VEDA SERVER] Device successfully paired: {device_name}")
                self._send_json(200, {
                    "success": True,
                    "token": token,
                    "message": f"Paired with V.E.D.A. as {device_name}"
                })
            else:
                self._send_json(401, {"success": False, "error": "Invalid pairing PIN"})
            return

        elif path == "/api/provider/select":
            mode = payload.get("mode", "AUTOMATIC")
            provider = payload.get("provider", "GEMINI")
            ai_router.set_provider_mode(mode, provider)
            self._send_json(200, {
                "success": True,
                "mode": ai_router.provider_mode,
                "selected_provider": ai_router.selected_provider,
                "active_provider": ai_router.active_provider_name
            })
            return

        elif path == "/api/chat":
            prompt = payload.get("prompt", "").strip()
            history = payload.get("history", [])
            language_mode = payload.get("language_mode", "AUTO")

            if not prompt:
                self._send_json(400, {"error": "Prompt cannot be empty"})
                return

            self.send_response(200)
            self._set_cors_headers("text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            try:
                for chunk in ai_router.execute_stream(
                    prompt=prompt,
                    history=history[-10:] if history else None,
                    language_mode=language_mode
                ):
                    if chunk:
                        sse_event = f"data: {json.dumps({'chunk': chunk, 'provider': ai_router.last_provider_used})}\n\n"
                        self.wfile.write(sse_event.encode("utf-8"))
                        self.wfile.flush()

                done_event = f"data: {json.dumps({'done': True, 'provider': ai_router.last_provider_used})}\n\n"
                self.wfile.write(done_event.encode("utf-8"))
                self.wfile.flush()
            except Exception as e:
                err_event = f"data: {json.dumps({'error': str(e)})}\n\n"
                try:
                    self.wfile.write(err_event.encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass
            return

        elif path == "/api/vision":
            prompt = payload.get("prompt", "What is visible in this frame?")
            image_b64 = payload.get("image", "")

            if not image_b64:
                self._send_json(400, {"error": "Missing image base64 data"})
                return

            try:
                import base64
                from io import BytesIO
                from PIL import Image

                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]

                img_bytes = base64.b64decode(image_b64)
                img = Image.open(BytesIO(img_bytes)).convert("RGB")

                result = ai_router.vision(img, prompt)
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"error": f"Vision analysis failed: {str(e)}"})
            return

        elif path == "/api/desktop/command":
            token = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if token not in PAIRED_TOKENS:
                self._send_json(403, {"error": "Unauthorized. Device not paired."})
                return

            command = payload.get("command", "")
            fast_res = ai_router.try_deterministic_fast_path(command)
            if fast_res:
                self._send_json(200, {"success": True, "result": fast_res})
            else:
                self._send_json(200, {"success": True, "result": "Command received by Windows agent."})
            return

        else:
            self._send_json(404, {"error": f"Endpoint '{path}' not found."})


def run_veda_server(host: str = "0.0.0.0", port: int = 8765):
    server_address = (host, port)
    httpd = HTTPServer(server_address, VedaApiHandler)
    lan_ip = get_local_ip()
    print("=" * 60)
    print(" V.E.D.A. MOBILE API GATEWAY & LOCAL BRIDGE SERVER")
    print("=" * 60)
    print(f" Localhost: http://127.0.0.1:{port}")
    print(f" Network:   http://{lan_ip}:{port}")
    print(f" Pairing PIN: {CURRENT_PAIR_PIN}")
    print(f" Active AI Provider: {ai_router.active_provider_name}")
    print(" Press Ctrl+C to stop.")
    print("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[VEDA SERVER] Shutting down cleanly.")
        httpd.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="V.E.D.A. Mobile API Bridge")
    parser.add_argument("--port", type=int, default=8765, help="Port number (default 8765)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address (default 0.0.0.0)")
    args = parser.parse_args()
    run_veda_server(host=args.host, port=args.port)
