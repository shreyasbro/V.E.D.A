"""
V.E.D.A. Permissions & Security Boundary Subsystem
Enforces fine-grained permission control for:
- computer_control
- file_access
- live_screen
- microphone
- camera
- gemini_network
- elevated_operations
"""

from typing import Any, Callable, Dict
from veda.config import VedaConfig

class PermissionDeniedError(Exception):
    pass

class PermissionGuard:
    """Checks runtime permissions and guards tool execution."""

    @staticmethod
    def check_permission(permission_key: str) -> bool:
        permissions = VedaConfig.get_permissions()
        val = permissions.get(permission_key, False)
        if permission_key == "elevated_operations":
            return val != "always_deny"
        return bool(val)

    @classmethod
    def require(cls, permission_key: str, action_name: str = "This action"):
        if not cls.check_permission(permission_key):
            pretty_names = {
                "computer_control": "Computer Control (Mouse/Keyboard/Windows)",
                "file_access": "File Access (Read/Write/Delete/Create)",
                "live_screen": "Live Screen Observation",
                "microphone": "Microphone Access (Voice/Speech)",
                "camera": "Camera Access (Visual Capture)",
                "gemini_network": "Gemini Cloud Network",
                "elevated_operations": "Administrator / Elevated Operations"
            }
            name = pretty_names.get(permission_key, permission_key)
            raise PermissionDeniedError(
                f"PERMISSION DENIED: {action_name} requires '{name}', which is currently DISABLED in V.E.D.A. Settings/Permissions Dashboard."
            )

def guard(permission_key: str):
    """Decorator to enforce a permission before executing a capability."""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            try:
                PermissionGuard.require(permission_key, action_name=func.__name__)
            except PermissionDeniedError as e:
                return {
                    "success": False,
                    "permission_denied": True,
                    "error": str(e)
                }
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator
