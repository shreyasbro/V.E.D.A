"""
V.E.D.A. Windows UI Automation & Multi-Monitor Subsystem
Semantic UI element discovery (buttons, edits, checkboxes, trees, menus, tabs, combo boxes),
semantic interactions, text extraction, scrolling, and multi-monitor geometry.
"""

import time
from typing import Any, Dict, List, Optional
import win32api
import win32con
import win32gui

try:
    import uiautomation as auto
    HAS_UIA = True
except ImportError:
    HAS_UIA = False


class UIAutomationEngine:
    """Semantic UI Automation for Windows desktop applications."""

    @staticmethod
    def get_element_tree(window_title: Optional[str] = None, max_depth: int = 3, max_elements: int = 50) -> Dict[str, Any]:
        """
        Enumerates semantic UI elements (buttons, edits, checkboxes, lists, menus, tabs)
        of the specified window (or active foreground window if None).
        """
        if not HAS_UIA:
            return {"success": False, "error": "uiautomation package is not installed."}

        try:
            if window_title:
                win = auto.WindowControl(searchDepth=2, SubName=window_title)
            else:
                win = auto.GetForegroundControl()

            if not win.Exists(maxSearchSeconds=1):
                return {"success": False, "error": f"Window '{window_title or 'Active'}' not found."}

            elements = []
            
            def walk(control, depth):
                if depth > max_depth or len(elements) >= max_elements:
                    return
                for child in control.GetChildren():
                    name = child.Name.strip() if child.Name else ""
                    ctrl_type = child.ControlTypeName
                    auto_id = child.AutomationId or ""
                    rect = child.BoundingRectangle
                    
                    if name or ctrl_type in ["ButtonControl", "EditControl", "CheckBoxControl", "MenuItemControl", "TabItemControl", "ListItemControl", "ComboBoxControl"]:
                        bbox = [rect.left, rect.top, rect.right, rect.bottom] if rect else None
                        center = [(rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2] if rect and rect.width() > 0 else None
                        elements.append({
                            "name": name,
                            "type": ctrl_type.replace("Control", ""),
                            "automation_id": auto_id,
                            "is_enabled": child.IsEnabled,
                            "bounding_box": bbox,
                            "center_point": center
                        })
                    walk(child, depth + 1)

            walk(win, 1)

            return {
                "success": True,
                "window": win.Name,
                "element_count": len(elements),
                "elements": elements
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def click_element_by_name(name: str, control_type: Optional[str] = None, automation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Semantically finds and invokes a UI control by name, control_type, or automation_id.
        Prefers native UI Automation invoke/toggle/selection pattern, falling back to click.
        """
        if not HAS_UIA:
            return {"success": False, "error": "uiautomation package is not installed."}

        try:
            fg = auto.GetForegroundControl()
            ctrl = None

            search_kwargs = {}
            if name:
                search_kwargs["SubName"] = name
            if automation_id:
                search_kwargs["AutomationId"] = automation_id

            if fg.Exists(maxSearchSeconds=0.5):
                ctrl = fg.Control(searchDepth=5, **search_kwargs)

            if not ctrl or not ctrl.Exists(maxSearchSeconds=0.5):
                ctrl = auto.Control(searchDepth=4, **search_kwargs)

            if not ctrl or not ctrl.Exists(maxSearchSeconds=1):
                return {"success": False, "error": f"UI element matching '{name or automation_id}' not found."}

            element_name = ctrl.Name
            element_type = ctrl.ControlTypeName

            invoked = False
            try:
                invoke_pattern = ctrl.GetInvokePattern()
                if invoke_pattern:
                    invoke_pattern.Invoke()
                    invoked = True
            except Exception:
                pass

            if not invoked:
                try:
                    toggle_pattern = ctrl.GetTogglePattern()
                    if toggle_pattern:
                        toggle_pattern.Toggle()
                        invoked = True
                except Exception:
                    pass

            if not invoked:
                try:
                    selection_pattern = ctrl.GetSelectionItemPattern()
                    if selection_pattern:
                        selection_pattern.Select()
                        invoked = True
                except Exception:
                    pass

            if not invoked:
                ctrl.Click(simulateMove=False)

            return {
                "success": True,
                "action": "click_element_by_name",
                "element_name": element_name,
                "element_type": element_type,
                "method": "semantic_pattern" if invoked else "automation_click"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def set_text_by_name(name: str, text: str) -> Dict[str, Any]:
        """
        Semantically finds an Edit/Input field and sets its text value directly.
        """
        if not HAS_UIA:
            return {"success": False, "error": "uiautomation package is not installed."}

        try:
            fg = auto.GetForegroundControl()
            edit = fg.EditControl(searchDepth=5, SubName=name)
            if not edit.Exists(maxSearchSeconds=0.5):
                edit = auto.EditControl(searchDepth=4, SubName=name)

            if not edit.Exists(maxSearchSeconds=1):
                return {"success": False, "error": f"Edit field matching '{name}' not found."}

            try:
                val_pattern = edit.GetValuePattern()
                if val_pattern:
                    val_pattern.SetValue(text)
                else:
                    edit.SendKeys(text)
            except Exception:
                edit.Click(simulateMove=False)
                edit.SendKeys(text)

            return {
                "success": True,
                "element_name": edit.Name,
                "text_set": text
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def select_element(element_name: str, item_text: str) -> Dict[str, Any]:
        """
        Selects an item inside a ComboBox, List, or Tab control.
        """
        if not HAS_UIA:
            return {"success": False, "error": "uiautomation package is not installed."}

        try:
            fg = auto.GetForegroundControl()
            ctrl = fg.Control(searchDepth=5, SubName=element_name)
            if not ctrl or not ctrl.Exists(maxSearchSeconds=0.5):
                ctrl = auto.Control(searchDepth=4, SubName=element_name)

            if not ctrl or not ctrl.Exists(maxSearchSeconds=1):
                return {"success": False, "error": f"Control '{element_name}' not found."}

            # If combo box, expand or set value
            item = ctrl.ListItemControl(SubName=item_text)
            if not item.Exists(maxSearchSeconds=0.5):
                item = ctrl.Control(SubName=item_text)

            if item and item.Exists(maxSearchSeconds=0.5):
                try:
                    sel = item.GetSelectionItemPattern()
                    if sel:
                        sel.Select()
                        return {"success": True, "selected": item_text, "parent": element_name}
                except Exception:
                    pass
                item.Click(simulateMove=False)
                return {"success": True, "selected": item_text, "parent": element_name}

            return {"success": False, "error": f"Item '{item_text}' not found inside '{element_name}'."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def scroll(direction: str = "down", amount: int = 3) -> Dict[str, Any]:
        """
        Scrolls the focused window or control (direction: 'up', 'down', 'page_up', 'page_down').
        """
        if not HAS_UIA:
            return {"success": False, "error": "uiautomation package is not installed."}

        try:
            fg = auto.GetForegroundControl()
            clean_dir = direction.lower().strip()
            
            try:
                scroll_pattern = fg.GetScrollPattern()
                if scroll_pattern:
                    if clean_dir == "down":
                        scroll_pattern.Scroll(auto.ScrollAmount.NoAmount, auto.ScrollAmount.SmallIncrement)
                    elif clean_dir == "up":
                        scroll_pattern.Scroll(auto.ScrollAmount.NoAmount, auto.ScrollAmount.SmallDecrement)
                    elif clean_dir == "page_down":
                        scroll_pattern.Scroll(auto.ScrollAmount.NoAmount, auto.ScrollAmount.LargeIncrement)
                    elif clean_dir == "page_up":
                        scroll_pattern.Scroll(auto.ScrollAmount.NoAmount, auto.ScrollAmount.LargeDecrement)
                    return {"success": True, "direction": direction, "method": "scroll_pattern"}
            except Exception:
                pass

            # Fallback to SendKeys PageDown/PageUp or Down
            if "down" in clean_dir:
                fg.SendKeys("{PageDown}" if "page" in clean_dir else "{Down}" * amount)
            else:
                fg.SendKeys("{PageUp}" if "page" in clean_dir else "{Up}" * amount)

            return {"success": True, "direction": direction, "method": "send_keys"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def read_visible_text(window_title: Optional[str] = None, max_chars: int = 3000) -> Dict[str, Any]:
        """
        Extracts all visible text strings from controls, edits, labels, and text blocks in the window.
        """
        if not HAS_UIA:
            return {"success": False, "error": "uiautomation package is not installed."}

        try:
            if window_title:
                win = auto.WindowControl(searchDepth=2, SubName=window_title)
            else:
                win = auto.GetForegroundControl()

            if not win.Exists(maxSearchSeconds=1):
                return {"success": False, "error": f"Window '{window_title or 'Active'}' not found."}

            text_snippets = []
            
            def extract(ctrl, depth):
                if depth > 4 or sum(len(t) for t in text_snippets) >= max_chars:
                    return
                for child in ctrl.GetChildren():
                    name = child.Name.strip() if child.Name else ""
                    ctrl_type = child.ControlTypeName
                    
                    if ctrl_type in ["TextControl", "EditControl", "DocumentControl"]:
                        if name and name not in text_snippets:
                            text_snippets.append(name)
                        try:
                            val = child.GetValuePattern().Value
                            if val and val.strip() and val.strip() not in text_snippets:
                                text_snippets.append(val.strip())
                        except Exception:
                            pass
                    extract(child, depth + 1)

            extract(win, 1)
            joined = "\n".join(text_snippets)

            return {
                "success": True,
                "window": win.Name,
                "text_count": len(text_snippets),
                "text": joined[:max_chars]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def wait_for_element(name: str, timeout_seconds: float = 5.0) -> Dict[str, Any]:
        """Waits for a UI element to appear in the active or desktop window."""
        if not HAS_UIA:
            return {"success": False, "error": "uiautomation package is not installed."}

        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            fg = auto.GetForegroundControl()
            if fg.Exists(maxSearchSeconds=0.2):
                ctrl = fg.Control(searchDepth=4, SubName=name)
                if ctrl.Exists(maxSearchSeconds=0.2):
                    return {
                        "success": True,
                        "element_name": ctrl.Name,
                        "waited_seconds": round(time.time() - start_time, 2)
                    }
            time.sleep(0.3)

        return {
            "success": False,
            "error": f"Timed out waiting for element '{name}' after {timeout_seconds}s."
        }


class MultiMonitorEngine:
    """Multi-monitor detection, resolutions, and display coordinates."""

    @staticmethod
    def get_monitors() -> Dict[str, Any]:
        """
        Returns all connected displays, resolutions, primary monitor flag, and workspace bounds.
        """
        monitors = []
        try:
            for idx, (hMonitor, hdcMonitor, pyRect) in enumerate(win32api.EnumDisplayMonitors()):
                info = win32api.GetMonitorInfo(hMonitor)
                is_primary = bool(info.get("Flags", 0) & win32con.MONITORINFOF_PRIMARY)
                monitor_rect = info.get("Monitor", pyRect)
                work_rect = info.get("Work", pyRect)
                width = monitor_rect[2] - monitor_rect[0]
                height = monitor_rect[3] - monitor_rect[1]

                monitors.append({
                    "index": idx,
                    "device": info.get("Device", f"DISPLAY{idx+1}"),
                    "is_primary": is_primary,
                    "resolution": f"{width}x{height}",
                    "bounds": {
                        "left": monitor_rect[0],
                        "top": monitor_rect[1],
                        "right": monitor_rect[2],
                        "bottom": monitor_rect[3],
                        "width": width,
                        "height": height
                    },
                    "work_area": {
                        "left": work_rect[0],
                        "top": work_rect[1],
                        "right": work_rect[2],
                        "bottom": work_rect[3]
                    }
                })

            return {
                "success": True,
                "monitor_count": len(monitors),
                "monitors": monitors
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
