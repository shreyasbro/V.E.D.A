from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from veda.core.types import ToolDefinition

class AIProvider(ABC):
    """Abstract interface for intelligence providers (Gemini, Local Models, etc.)."""

    @abstractmethod
    def generate_response(
        self,
        messages: List[Dict[str, Any]],
        tools: List[ToolDefinition]
    ) -> Dict[str, Any]:
        """
        Executes a completion or function call turn.
        Returns a dict:
        {
            "content": "text reply or thoughts",
            "tool_calls": [{"name": "tool_name", "arguments": {...}}]
        }
        """
        pass
