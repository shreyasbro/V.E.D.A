import re
from typing import Any, Dict, List
from veda.core.types import ToolDefinition
from veda.providers.base import AIProvider

class LocalOfflineProvider(AIProvider):
    """
    Offline fallback provider when Gemini API is offline or unconfigured.
    Uses pattern-free heuristic tool intent mapping.
    """

    def generate_response(
        self,
        messages: List[Dict[str, Any]],
        tools: List[ToolDefinition]
    ) -> Dict[str, Any]:
        # Last user message
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break

        cmd = user_msg.lower().strip()
        tool_calls = []
        content = ""

        # Check for open window inspection
        if any(w in cmd for w in ["what window", "active window", "kya chal raha", "kaunsa window"]):
            tool_calls.append({"name": "get_active_window", "arguments": {}})
        elif any(w in cmd for w in ["what is open", "open windows", "kya khula hai", "applications are open"]):
            tool_calls.append({"name": "get_open_windows", "arguments": {}})
        elif "notepad" in cmd and any(w in cmd for w in ["open", "khol", "chala"]):
            tool_calls.append({"name": "open_application", "arguments": {"application": "notepad"}})
            if any(w in cmd for w in ["write", "type", "likh"]):
                split_m = re.search(r"\b(?:type|write|likh(?:o|e|de| kar)?)\b", user_msg, re.IGNORECASE)
                text_to_type = user_msg[split_m.end():].strip() if split_m else "Hello from VEDA"
                text_to_type = re.sub(r"^(?:de|kar|aur|to)?[:\s]+", "", text_to_type, flags=re.IGNORECASE).strip()
                tool_calls.append({"name": "type_text", "arguments": {"text": text_to_type}})
        elif "chrome" in cmd and any(w in cmd for w in ["open", "khol"]):
            tool_calls.append({"name": "open_application", "arguments": {"application": "chrome"}})
        elif any(w in cmd for w in ["create a text file", "make a file", "file banao"]) or "veda-test.txt" in cmd:
            name = "VEDA-test.txt"
            content_str = "Agent test successful"
            m_text = re.search(r"containing\s+['\"](.*?)['\"]", user_msg, re.IGNORECASE)
            if m_text:
                content_str = m_text.group(1)
            tool_calls.append({"name": "write_text_file", "arguments": {"path": name, "content": content_str}})
        else:
            content = "Maine aapka sandesh suna. Offline mode me basic Windows tasks execute kar sakta hoon."

        return {
            "content": content,
            "tool_calls": tool_calls
        }
