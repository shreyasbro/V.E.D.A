import time
from typing import Any, Callable, Dict, List, Optional
from veda.core.types import AgentState
from veda.tools.registry import ToolRegistry
from veda.providers.base import AIProvider

class AgentLoop:
    """
    Core Autonomous Agent Perception-Reasoning-Action-Verification Loop.
    USER REQUEST -> OBSERVE -> PLAN -> TOOL -> OBSERVE -> VERIFY -> REPEAT -> FINAL REPLY
    """

    def __init__(self, provider: AIProvider, tool_registry: ToolRegistry, max_iterations: int = 8):
        self.provider = provider
        self.tools = tool_registry
        self.max_iterations = max_iterations
        self.state = AgentState()

    def run(
        self,
        user_request: str,
        status_callback: Optional[Callable[[str, str], None]] = None,
        action_callback: Optional[Callable[[str], None]] = None,
        abort_event: Optional[Any] = None
    ) -> str:
        self.state.current_request = user_request
        self.state.tool_calls_history.clear()
        self.state.error = None

        def update_status(text: str, color: str = "#38bdf8"):
            if status_callback:
                status_callback(text, color)

        def log_action(text: str):
            if action_callback:
                action_callback(text)

        update_status("UNDERSTANDING...", "#7c3aed")
        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": user_request}
        ]

        iteration = 0
        final_answer = ""

        while iteration < self.max_iterations:
            if abort_event and abort_event.is_set():
                update_status("STOPPED", "#f59e0b")
                return "Task was aborted by user."

            iteration += 1
            update_status("REASONING & PLANNING...", "#3b82f6")

            # Call AI Model with active tools
            tool_definitions = self.tools.get_definitions()
            response = self.provider.generate_response(messages, tool_definitions)

            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            # If no tool calls requested, we have reached the final answer
            if not tool_calls:
                final_answer = content or "Task complete."
                break

            # Append model reasoning to message history
            messages.append({
                "role": "model",
                "content": content,
                "tool_calls": tool_calls
            })

            # Execute tool calls
            for tc in tool_calls:
                if abort_event and abort_event.is_set():
                    update_status("STOPPED", "#f59e0b")
                    return "Task was aborted by user."

                tool_name = tc.get("name")
                args = tc.get("arguments", {})

                update_status(f"EXECUTING: {tool_name}", "#0284c7")
                log_action(f"[{tool_name}] args: {args}")

                # Execute real Windows tool
                result = self.tools.execute(tool_name, **args)
                log_action(f"[{tool_name}] result: {result.to_dict()}")

                self.state.tool_calls_history.append({
                    "tool": tool_name,
                    "arguments": args,
                    "result": result.to_dict()
                })

                # Append tool result to context for next reasoning turn
                messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": str(result.to_dict())
                })

                # Verification pause to allow OS UI states to stabilize
                time.sleep(0.3)

        update_status("COMPLETED", "#10b981")
        return final_answer
