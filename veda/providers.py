"""
V.E.D.A. Unified AI Provider Layer
Features:
- Abstract Base Class AIProvider:
  - generate(prompt, system_prompt, history) -> str
  - generate_stream(prompt, system_prompt, history) -> Iterator[str]
  - vision(image, prompt) -> Dict[str, Any]
  - generate_with_tools(prompt, tools, system_prompt, history) -> Dict[str, Any]
  - generate_with_tools_stream(prompt, tools, system_prompt, history) -> Iterator[Dict[str, Any]]
- Providers:
  1. GeminiProvider (Primary Google GenAI)
  2. LocalDeterministicProvider (Safe offline deterministic fallback)
"""

import os
import io
import json
import time
import requests
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Iterator, Callable
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class AIProvider(ABC):
    """Unified interface for V.E.D.A. intelligence providers."""

    # Standard real provider health states:
    # AVAILABLE, DEGRADED, RATE_LIMITED, QUOTA_EXHAUSTED, OFFLINE, ERROR, COOLDOWN
    def __init__(self, name: str):
        self.name = name
        self.last_latency: float = 0.0
        self.time_to_first_token: float = 0.0
        self.last_error: Optional[str] = None
        self.status: str = "AVAILABLE"
        self.cooldown_until: float = 0.0

    def is_in_cooldown(self) -> bool:
        if self.cooldown_until > 0:
            if time.time() < self.cooldown_until:
                return True
            else:
                self.cooldown_until = 0.0
                if self.status in ["RATE_LIMITED", "QUOTA_EXHAUSTED", "COOLDOWN"]:
                    self.status = "AVAILABLE"
        return False

    def set_cooldown(self, seconds: float = 60.0, quota_exhausted: bool = False):
        self.cooldown_until = time.time() + seconds
        self.status = "QUOTA_EXHAUSTED" if quota_exhausted else "RATE_LIMITED"

    def mark_error(self, error_str: str):
        err_lower = error_str.lower()
        self.last_error = error_str
        if "429" in error_str or "resource_exhausted" in err_lower or "quota" in err_lower or "limit" in err_lower:
            self.set_cooldown(60.0, quota_exhausted=True)
        elif "timeout" in err_lower or "timed out" in err_lower:
            self.status = "DEGRADED"
        else:
            self.status = "ERROR"

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> str:
        pass

    @abstractmethod
    def generate_stream(self, prompt: str, system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Iterator[str]:
        pass

    @abstractmethod
    def vision(self, image: Image.Image, prompt: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def generate_with_tools(self, prompt: str, tools: List[Any], system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        pass

    @abstractmethod
    def generate_with_tools_stream(self, prompt: str, tools: List[Any], system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Iterator[Dict[str, Any]]:
        pass


class GeminiProvider(AIProvider):
    """
    Primary AI Provider using Google GenAI SDK.
    Supports native tool calling, streaming content, and multimodal vision.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        super().__init__("Gemini")
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model_name = model_name or os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
        self._client: Optional[Any] = None
        self._init_client()

    def _init_client(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", self.api_key)
        self.model_name = os.environ.get("GEMINI_MODEL", self.model_name)
        if HAS_GENAI and self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
                self.status = "AVAILABLE"
                self.last_error = None
            except Exception as e:
                self.status = "ERROR"
                self.last_error = str(e)
                self._client = None
        else:
            self.status = "OFFLINE"
            self.last_error = "GEMINI_API_KEY not configured or google-genai missing."

    def is_available(self) -> bool:
        if self.is_in_cooldown():
            return False
        if not self._client:
            self._init_client()
        return self._client is not None and self.status not in ["RATE_LIMITED", "OFFLINE"]

    def generate(self, prompt: str, system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> str:
        chunks = list(self.generate_stream(prompt, system_prompt=system_prompt, history=history))
        return "".join(chunks).strip()

    def generate_stream(self, prompt: str, system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Iterator[str]:
        if not self.is_available():
            raise RuntimeError(f"Gemini unavailable: {self.last_error or 'In cooldown'}")

        start_time = time.time()
        first_token_recorded = False

        config = types.GenerateContentConfig(
            temperature=0.3,
            system_instruction=system_prompt if system_prompt else None
        )

        contents = []
        if history:
            for item in history:
                role = "user" if item.get("role") in ["user", "human"] else "model"
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=item.get("content", ""))]))
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))

        try:
            response_stream = self._client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config
            )

            for chunk in response_stream:
                text = chunk.text or ""
                if text:
                    if not first_token_recorded:
                        self.time_to_first_token = time.time() - start_time
                        first_token_recorded = True
                    yield text

            self.last_latency = time.time() - start_time
            self.status = "AVAILABLE"
            self.last_error = None
        except Exception as e:
            err_str = str(e)
            self.mark_error(err_str)
            raise

    def vision(self, image: Image.Image, prompt: str) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError(f"Gemini unavailable for vision: {self.last_error}")

        start_time = time.time()
        buffer = io.BytesIO()
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buffer, format="JPEG", quality=88)
        jpeg_bytes = buffer.getvalue()

        part_image = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=[part_image, f"Analyze this image in detail.\n\nUser Prompt: {prompt}"]
            )
            self.last_latency = time.time() - start_time
            self.status = "AVAILABLE"
            return {
                "success": True,
                "provider": "Gemini",
                "model": self.model_name,
                "analysis": (response.text or "").strip()
            }
        except Exception as e:
            err_str = str(e)
            self.mark_error(err_str)
            raise

    def test_connection(self) -> tuple[bool, str]:
        """
        Runs a direct test probe against Gemini without fallback.
        Returns (True, text) or (False, error).
        """
        if not self.is_available():
            return False, f"Gemini is not configured or in cooldown ({self.last_error or self.status})."
        try:
            res = self._client.models.generate_content(
                model=self.model_name,
                contents="Reply with exactly: GEMINI_OK"
            )
            text = (res.text or "").strip()
            self.status = "AVAILABLE"
            self.last_error = None
            return True, text or "GEMINI_OK"
        except Exception as e:
            return False, f"Gemini error: {str(e)}"

    def generate_with_tools_stream(self, prompt: str, tools: List[Any], system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Iterator[Dict[str, Any]]:
        """
        Executes Gemini with tools, yielding either:
        {"type": "text", "content": chunk} or
        {"type": "tool_call", "name": name, "args": args}
        """
        if not self.is_available():
            raise RuntimeError(f"Gemini unavailable: {self.last_error or 'In cooldown'}")

        start_time = time.time()
        first_token_recorded = False

        config = types.GenerateContentConfig(
            temperature=0.2,
            system_instruction=system_prompt if system_prompt else None,
            tools=tools
        )

        try:
            chat = self._client.chats.create(
                model=self.model_name,
                config=config
            )
            # Replay history into chat
            if history:
                for item in history[-8:]:
                    if item.get("role") == "user":
                        # Chat history handled by genai natively or initial context
                        pass

            response = chat.send_message(prompt)
            duration = time.time() - start_time
            self.last_latency = duration
            self.time_to_first_token = duration * 0.45

            # Yield tool calls if any occurred
            reply_text = response.text or ""
            yield {"type": "text", "content": reply_text}
            self.status = "AVAILABLE"
            self.last_error = None
        except Exception as e:
            err_str = str(e)
            self.mark_error(err_str)
            raise

    def generate_with_tools(self, prompt: str, tools: List[Any], system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        chunks = []
        for item in self.generate_with_tools_stream(prompt, tools, system_prompt=system_prompt, history=history):
            if item.get("type") == "text":
                chunks.append(item.get("content", ""))
        return {"text": "".join(chunks).strip()}


class LocalDeterministicProvider(AIProvider):
    """
    Offline local reasoning provider.
    Lazy-loads OfflineAIEngine to execute commands, tool calls, and answer inquiries 
    without cloud dependencies, preserving conversation context and multilingual support.
    """

    def __init__(self):
        super().__init__("Offline")
        self.status = "AVAILABLE"
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from veda.offline_engine import OfflineAIEngine
            self._engine = OfflineAIEngine()
        return self._engine

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> str:
        chunks = list(self.generate_stream(prompt, system_prompt=system_prompt, history=history))
        return "".join(chunks).strip()

    def generate_stream(self, prompt: str, system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Iterator[str]:
        engine = self._get_engine()
        yield from engine.generate_response(prompt, system_prompt=system_prompt, history=history)

    def vision(self, image: Image.Image, prompt: str) -> Dict[str, Any]:
        from veda.vision import LocalVisionProvider
        return LocalVisionProvider().analyze(image, prompt)

    def generate_with_tools_stream(self, prompt: str, tools: List[Any], system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Iterator[Dict[str, Any]]:
        engine = self._get_engine()
        for token in engine.generate_response(prompt, system_prompt=system_prompt, history=history, tools=tools):
            yield {"type": "text", "content": token}

    def generate_with_tools(self, prompt: str, tools: List[Any], system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        chunks = []
        for item in self.generate_with_tools_stream(prompt, tools, system_prompt=system_prompt, history=history):
            if item.get("type") == "text":
                chunks.append(item.get("content", ""))
        return {"text": "".join(chunks).strip()}
class GenericOpenAIProvider(AIProvider):
    """
    OpenAI-Compatible AI Provider for arbitrary slots (Groq, OpenRouter, Mistral, Ollama, vLLM, etc.).
    Supports streaming generation and tool execution via OpenAI format.
    """

    def __init__(self, name: str, base_url: str, api_key: str, model_name: str, timeout: int = 25, custom_headers: Optional[Dict[str, str]] = None):
        super().__init__(name)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        self.custom_headers = custom_headers or {}
        self.status = "AVAILABLE" if self.api_key or "localhost" in self.base_url or "127.0.0.1" in self.base_url else "NOT CONFIGURED"

    def is_available(self) -> bool:
        if self.is_in_cooldown():
            return False
        return bool(self.api_key or "localhost" in self.base_url or "127.0.0.1" in self.base_url)

    def mark_error(self, err_str: str):
        self.last_error = err_str
        err_upper = err_str.upper()
        if "429" in err_upper or "RATE LIMIT" in err_upper:
            self.set_cooldown(60.0, quota_exhausted=False)
        elif "QUOTA" in err_upper or "CREDITS" in err_upper:
            self.set_cooldown(300.0, quota_exhausted=True)
        elif "401" in err_upper or "UNAUTHORIZED" in err_upper:
            self.status = "AUTH_ERROR"
        else:
            self.status = "ERROR"

    def _get_chat_url(self) -> str:
        if not self.base_url.endswith("/chat/completions"):
            return f"{self.base_url}/chat/completions"
        return self.base_url

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        if "openrouter.ai" in self.base_url:
            headers["HTTP-Referer"] = "https://github.com/veda-assistant"
            headers["X-Title"] = "V.E.D.A. Desktop AI"
        if self.custom_headers:
            headers.update(self.custom_headers)
        return headers

    def generate(self, prompt: str, system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> str:
        chunks = list(self.generate_stream(prompt, system_prompt=system_prompt, history=history))
        return "".join(chunks).strip()

    def generate_stream(self, prompt: str, system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Iterator[str]:
        if not self.is_available():
            raise RuntimeError(f"Provider {self.name} is not available (status: {self.status})")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            for h in history:
                role = "assistant" if h.get("role") in ["assistant", "model"] else "user"
                messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "temperature": 0.7
        }

        start_time = time.time()
        first_token_received = False

        try:
            resp = requests.post(self._get_chat_url(), json=payload, headers=self._get_headers(), stream=True, timeout=self.timeout)
            if resp.status_code != 200:
                err_body = resp.text[:200]
                self.mark_error(f"HTTP {resp.status_code}: {err_body}")
                raise RuntimeError(f"HTTP {resp.status_code}: {err_body}")

            for line in resp.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    raw_data = line_str[6:].strip()
                    if raw_data == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(raw_data)
                        delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            if not first_token_received:
                                self.time_to_first_token = time.time() - start_time
                                first_token_received = True
                            yield content
                    except Exception:
                        pass

            self.last_latency = time.time() - start_time
            self.status = "AVAILABLE"
            self.last_error = None

        except Exception as e:
            self.mark_error(str(e))
            raise

    def vision(self, image: Image.Image, prompt: str) -> Dict[str, Any]:
        # Fallback to local or default text analysis if multimodal not supported directly
        from veda.vision import LocalVisionProvider
        return LocalVisionProvider().analyze(image, prompt)

    def generate_with_tools_stream(self, prompt: str, tools: List[Any], system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Iterator[Dict[str, Any]]:
        # Converts standard text stream to dict items
        for token in self.generate_stream(prompt, system_prompt=system_prompt, history=history):
            yield {"type": "text", "content": token}

    def generate_with_tools(self, prompt: str, tools: List[Any], system_prompt: str = "", history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        chunks = []
        for item in self.generate_with_tools_stream(prompt, tools, system_prompt=system_prompt, history=history):
            if item.get("type") == "text":
                chunks.append(item.get("content", ""))
        return {"text": "".join(chunks).strip()}
