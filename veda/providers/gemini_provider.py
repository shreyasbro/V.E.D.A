import os
from typing import Any, Dict, List, Optional
from veda.core.types import ToolDefinition
from veda.providers.base import AIProvider

class GeminiProvider(AIProvider):
    """
    Production-grade Google GenAI integration using official google-genai SDK.
    Handles structured tool calling, multi-turn reasoning, and execution interpretation.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        self._client = None
        self._init_client()

    def _init_client(self):
        if not self.api_key:
            return
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        except Exception as e:
            print(f"[GeminiProvider] Initialization error: {e}")
            self._client = None

    def is_available(self) -> bool:
        return self._client is not None

    def _convert_tools_to_gemini(self, tools: List[ToolDefinition]) -> List[Dict[str, Any]]:
        """Converts ToolDefinition schemas into Gemini function declarations."""
        declarations = []
        for t in tools:
            decl = {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters
            }
            declarations.append(decl)
        return [{"function_declarations": declarations}]

    def generate_response(
        self,
        messages: List[Dict[str, Any]],
        tools: List[ToolDefinition]
    ) -> Dict[str, Any]:
        if not self._client:
            raise RuntimeError("Gemini API key not configured or client failed to initialize.")

        try:
            from google.genai import types

            gemini_tools = self._convert_tools_to_gemini(tools) if tools else None

            # Prepare configuration with function declarations
            config = types.GenerateContentConfig(
                temperature=0.2,
                tools=gemini_tools if gemini_tools else None,
                system_instruction=(
                    "You are V.E.D.A. (Virtual Executive Desktop Assistant), an autonomous Windows AI desktop agent. "
                    "You interact with the user's real Windows computer using the provided tools. "
                    "Always choose the correct tool to inspect state, perform actions, and verify results. "
                    "When user speaks in English, Hindi, or Hinglish, understand their natural intent and execute the necessary tools. "
                    "Never guess or assume an action succeeded without verifying state. "
                    "When all tool actions are complete, provide a friendly, concise conversational confirmation to the user."
                )
            )

            # Format messages for google-genai
            # Map simplified {role, content, tool_calls, tool_results} into Contents
            contents = []
            for m in messages:
                role = m.get("role")
                if role == "user":
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=m.get("content", ""))]
                    ))
                elif role == "model":
                    parts = []
                    if m.get("content"):
                        parts.append(types.Part.from_text(text=m["content"]))
                    for tc in m.get("tool_calls", []):
                        parts.append(types.Part.from_function_call(
                            name=tc["name"],
                            args=tc.get("arguments", {})
                        ))
                    if parts:
                        contents.append(types.Content(role="model", parts=parts))
                elif role == "tool":
                    # Function response
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part.from_function_response(
                            name=m.get("name", "tool"),
                            response={"result": m.get("content", "")}
                        )]
                    ))

            response = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )

            result_content = ""
            tool_calls = []

            # Extract text and function calls from candidates
            if response.candidates and response.candidates[0].content:
                c = response.candidates[0].content
                for part in c.parts:
                    if hasattr(part, "text") and part.text:
                        result_content += part.text
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        args = dict(fc.args) if fc.args else {}
                        tool_calls.append({
                            "name": fc.name,
                            "arguments": args
                        })

            return {
                "content": result_content.strip(),
                "tool_calls": tool_calls
            }

        except Exception as e:
            return {
                "content": f"Gemini API Error: {str(e)}",
                "tool_calls": []
            }
