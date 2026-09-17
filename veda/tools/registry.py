from typing import Any, Callable, Dict, List
from veda.core.types import ToolDefinition, ToolResult
from veda.tools.windows_tools import WindowsTools

class ToolRegistry:
    """Registry mapping tools to schemas and execution handlers."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._handlers: Dict[str, Callable[..., ToolResult]] = {}
        self._register_default_tools()

    def register(self, definition: ToolDefinition, handler: Callable[..., ToolResult]):
        self._tools[definition.name] = definition
        self._handlers[definition.name] = handler

    def get_definitions(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def execute(self, name: str, **kwargs) -> ToolResult:
        handler = self._handlers.get(name)
        if not handler:
            return ToolResult(False, error=f"Tool '{name}' is not registered.")
        try:
            return handler(**kwargs)
        except Exception as e:
            return ToolResult(False, error=f"Tool '{name}' failed with error: {str(e)}")

    def _register_default_tools(self):
        self.register(
            ToolDefinition(
                name="get_active_window",
                description="Returns the currently active window title and process state.",
                parameters={"type": "object", "properties": {}}
            ),
            lambda **kw: WindowsTools.get_active_window()
        )

        self.register(
            ToolDefinition(
                name="get_open_windows",
                description="Returns a list of all currently open and visible window titles on the computer.",
                parameters={"type": "object", "properties": {}}
            ),
            lambda **kw: WindowsTools.get_open_windows()
        )

        self.register(
            ToolDefinition(
                name="take_screenshot",
                description="Captures the full primary screen and saves it as an image.",
                parameters={
                    "type": "object",
                    "properties": {
                        "save_path": {"type": "string", "description": "Optional file path to save the screenshot."}
                    }
                }
            ),
            lambda **kw: WindowsTools.take_screenshot(kw.get("save_path"))
        )

        self.register(
            ToolDefinition(
                name="open_application",
                description="Launches a requested Windows application (e.g. 'notepad', 'chrome', 'calc', 'cmd', 'explorer').",
                parameters={
                    "type": "object",
                    "properties": {
                        "application": {"type": "string", "description": "The application executable name or command, e.g. 'notepad' or 'chrome'."}
                    },
                    "required": ["application"]
                }
            ),
            lambda **kw: WindowsTools.open_application(kw["application"])
        )

        self.register(
            ToolDefinition(
                name="focus_window",
                description="Brings a window matching title_query to the foreground and focuses it.",
                parameters={
                    "type": "object",
                    "properties": {
                        "title_query": {"type": "string", "description": "Substring of the window title to focus, e.g. 'Notepad' or 'Chrome'."}
                    },
                    "required": ["title_query"]
                }
            ),
            lambda **kw: WindowsTools.focus_window(kw["title_query"])
        )

        self.register(
            ToolDefinition(
                name="type_text",
                description="Types text into the currently focused application window.",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The exact text string to type."}
                    },
                    "required": ["text"]
                }
            ),
            lambda **kw: WindowsTools.type_text(kw["text"])
        )

        self.register(
            ToolDefinition(
                name="press_key",
                description="Presses a keyboard key or hotkey combination (e.g. 'enter', 'tab', 'alt+f4', 'ctrl+s').",
                parameters={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Key name or hotkey combination."}
                    },
                    "required": ["key"]
                }
            ),
            lambda **kw: WindowsTools.press_key(kw["key"])
        )

        self.register(
            ToolDefinition(
                name="mouse_move",
                description="Moves the mouse cursor smoothly to screen coordinates (x, y).",
                parameters={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "Target X screen coordinate."},
                        "y": {"type": "integer", "description": "Target Y screen coordinate."}
                    },
                    "required": ["x", "y"]
                }
            ),
            lambda **kw: WindowsTools.mouse_move(kw["x"], kw["y"])
        )

        self.register(
            ToolDefinition(
                name="mouse_click",
                description="Performs a mouse click at optional coordinates (x, y).",
                parameters={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "Optional X coordinate to click."},
                        "y": {"type": "integer", "description": "Optional Y coordinate to click."},
                        "clicks": {"type": "integer", "description": "Number of clicks: 1=single, 2=double, 3=triple."}
                    }
                }
            ),
            lambda **kw: WindowsTools.mouse_click(kw.get("x"), kw.get("y"), kw.get("clicks", 1))
        )

        self.register(
            ToolDefinition(
                name="scroll",
                description="Scrolls vertically up (positive) or down (negative).",
                parameters={
                    "type": "object",
                    "properties": {
                        "clicks": {"type": "integer", "description": "Number of scroll clicks, positive up, negative down."}
                    },
                    "required": ["clicks"]
                }
            ),
            lambda **kw: WindowsTools.scroll(kw["clicks"])
        )

        self.register(
            ToolDefinition(
                name="list_directory",
                description="Lists files and subfolders in the specified directory (defaults to Desktop if omitted).",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Optional directory path. Defaults to user Desktop."}
                    }
                }
            ),
            lambda **kw: WindowsTools.list_directory(kw.get("path"))
        )

        self.register(
            ToolDefinition(
                name="read_text_file",
                description="Reads the contents of a text file from disk.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute or relative file path to read."}
                    },
                    "required": ["path"]
                }
            ),
            lambda **kw: WindowsTools.read_text_file(kw["path"])
        )

        self.register(
            ToolDefinition(
                name="write_text_file",
                description="Creates or overwrites a text file with specified content. Defaults relative filenames to Desktop.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Target file name or path."},
                        "content": {"type": "string", "description": "Text content to write into the file."}
                    },
                    "required": ["path", "content"]
                }
            ),
            lambda **kw: WindowsTools.write_text_file(kw["path"], kw["content"])
        )
