from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON schema style

@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error
        }

@dataclass
class AgentState:
    current_request: str = ""
    active_window: str = ""
    open_windows: List[str] = field(default_factory=list)
    tool_calls_history: List[Dict[str, Any]] = field(default_factory=list)
    task_status: str = "IDLE"  # IDLE, UNDERSTANDING, PLANNING, EXECUTING, VERIFYING, COMPLETED, ERROR
    error: Optional[str] = None
