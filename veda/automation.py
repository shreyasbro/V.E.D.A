"""
V.E.D.A. Windows Autonomous Automation Engine
Features:
- Real Windows system monitoring (Battery, CPU, Network/Wi-Fi) using real Windows APIs.
- Edge-triggered hysteresis state machine (triggers once upon crossing threshold, resets only when crossing back).
- Natural language rule extraction supporting English, Hindi, and Hinglish.
- Local persistent execution (stored in ~/.veda/automations.json).
- Works completely offline without needing Gemini at trigger time.
- Integrated with Kokoro TTS and UI notification callbacks.
"""

import os
import re
import json
import time
import threading
import uuid
from typing import Dict, Any, List, Optional, Callable
import psutil

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".veda")
AUTOMATIONS_FILE = os.path.join(CONFIG_DIR, "automations.json")


class AutomationRule:
    """Represents a persistent automation condition and associated local action."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        metric: str,             # "battery", "cpu", "network"
        operator: str,           # "<=", ">=", "==", "!="
        threshold: Any,          # numerical threshold or status code
        alert_message: str,
        enabled: bool = True,
        action_type: str = "voice_and_notification",  # "voice", "notification", "voice_and_notification"
        created_at: Optional[float] = None
    ):
        self.rule_id = rule_id or str(uuid.uuid4())[:8]
        self.name = name
        self.metric = metric.lower()
        self.operator = operator
        self.threshold = float(threshold) if isinstance(threshold, (int, float, str)) and str(threshold).replace(".", "", 1).isdigit() else threshold
        self.alert_message = alert_message
        self.enabled = enabled
        self.action_type = action_type
        self.created_at = created_at or time.time()

        # State tracking for hysteresis (edge-triggered)
        self.is_triggered = False
        self.last_triggered_time = 0.0

    def evaluate(self, state: Dict[str, Any]) -> tuple[bool, str]:
        """
        Evaluates the rule against system state with edge-triggered hysteresis.
        Returns (triggered_now: bool, reason: str).
        """
        if not self.enabled:
            return False, "Rule disabled"

        is_met = False
        if self.metric == "battery":
            current_val = state.get("battery_percent")
            if current_val is None:
                return False, "No battery data"
            thresh = float(self.threshold)
            if self.operator in ["<=", "<"]:
                is_met = current_val <= thresh
                if current_val > thresh + 1.0:
                    self.is_triggered = False
            elif self.operator in [">=", ">"]:
                is_met = current_val >= thresh
                if current_val < thresh - 1.0:
                    self.is_triggered = False
            elif self.operator in ["==", "="]:
                is_met = current_val == thresh
                if current_val != thresh:
                    self.is_triggered = False

        elif self.metric == "cpu":
            current_val = state.get("cpu_percent", 0.0)
            thresh = float(self.threshold)
            if self.operator in [">=", ">"]:
                is_met = current_val >= thresh
                if current_val < max(0.0, thresh - 5.0):
                    self.is_triggered = False
            elif self.operator in ["<=", "<"]:
                is_met = current_val <= thresh
                if current_val > thresh + 5.0:
                    self.is_triggered = False

        elif self.metric in ["network", "wifi"]:
            is_connected = bool(state.get("network_connected", False))
            target_state = str(self.threshold).lower()
            if target_state in ["disconnected", "off", "lost", "0", "false"]:
                is_met = not is_connected
                if is_connected:
                    self.is_triggered = False
            else:
                is_met = is_connected
                if not is_connected:
                    self.is_triggered = False

        if is_met:
            if not self.is_triggered:
                self.is_triggered = True
                self.last_triggered_time = time.time()
                return True, f"Condition met: {self.metric} {self.operator} {self.threshold}"
            else:
                return False, "Already triggered (hysteresis hold)"

        return False, "Condition not met"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "metric": self.metric,
            "operator": self.operator,
            "threshold": self.threshold,
            "alert_message": self.alert_message,
            "enabled": self.enabled,
            "action_type": self.action_type,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutomationRule":
        return cls(
            rule_id=data.get("rule_id", ""),
            name=data.get("name", "Unnamed Rule"),
            metric=data.get("metric", "battery"),
            operator=data.get("operator", "<="),
            threshold=data.get("threshold", 30),
            alert_message=data.get("alert_message", "Automation alert!"),
            enabled=data.get("enabled", True),
            action_type=data.get("action_type", "voice_and_notification"),
            created_at=data.get("created_at")
        )


class AutomationEngine:
    """
    Background daemon that monitors real Windows hardware/system states
    and executes actions when configured conditions are met.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AutomationEngine, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, check_interval: float = 3.0):
        if self._initialized:
            return
        self._initialized = True

        self.check_interval = check_interval
        self.rules: List[AutomationRule] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Callbacks for UI & Voice actions
        self.on_trigger_callback: Optional[Callable[[AutomationRule, Dict[str, Any]], None]] = None
        self.tts_callback: Optional[Callable[[str, str], None]] = None

        self._ensure_storage()
        self.load_rules()

    def _ensure_storage(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if not os.path.exists(AUTOMATIONS_FILE):
            try:
                with open(AUTOMATIONS_FILE, "w", encoding="utf-8") as f:
                    json.dump([], f)
            except Exception:
                pass

    def load_rules(self):
        with self._lock:
            if not os.path.exists(AUTOMATIONS_FILE):
                self.rules = []
                return
            try:
                with open(AUTOMATIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.rules = [AutomationRule.from_dict(d) for d in data if isinstance(d, dict)]
            except Exception as e:
                print(f"[AUTOMATION] Error loading rules: {e}")
                self.rules = []

    def save_rules(self):
        with self._lock:
            try:
                with open(AUTOMATIONS_FILE, "w", encoding="utf-8") as f:
                    json.dump([r.to_dict() for r in self.rules], f, indent=2)
            except Exception as e:
                print(f"[AUTOMATION] Error saving rules: {e}")

    def add_rule(self, rule: AutomationRule) -> bool:
        with self._lock:
            self.rules = [r for r in self.rules if r.rule_id != rule.rule_id]
            self.rules.append(rule)
        self.save_rules()
        print(f"[AUTOMATION] Added rule '{rule.name}' (ID: {rule.rule_id})")
        return True

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            orig_len = len(self.rules)
            self.rules = [r for r in self.rules if r.rule_id != rule_id]
            changed = len(self.rules) < orig_len
        if changed:
            self.save_rules()
            print(f"[AUTOMATION] Deleted rule ID: {rule_id}")
        return changed

    def toggle_rule(self, rule_id: str, enabled: Optional[bool] = None) -> bool:
        with self._lock:
            for r in self.rules:
                if r.rule_id == rule_id:
                    r.enabled = not r.enabled if enabled is None else enabled
                    self.save_rules()
                    print(f"[AUTOMATION] Toggled rule '{r.name}' -> {'Enabled' if r.enabled else 'Disabled'}")
                    return True
        return False

    def get_rules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self.rules]

    def list_rules(self) -> List[AutomationRule]:
        with self._lock:
            return list(self.rules)

    def test_rule(self, rule_id: str):
        with self._lock:
            rule = next((r for r in self.rules if r.rule_id == rule_id), None)
        if rule:
            self._execute_rule_action(rule, "Manual Test Trigger")

    # ==========================================
    # REAL WINDOWS SYSTEM STATE TELEMETRY
    # ==========================================
    def get_system_state(self) -> Dict[str, Any]:
        """Queries real Windows hardware and network state directly."""
        return self.get_current_system_state()

    @staticmethod
    def get_current_system_state() -> Dict[str, Any]:
        """Queries real Windows hardware and network state directly."""
        state = {
            "battery_percent": 100,
            "battery_plugged": True,
            "cpu_percent": 0.0,
            "network_connected": True
        }

        # 1. Real Battery Check via Windows APIs
        try:
            bat = psutil.sensors_battery()
            if bat:
                state["battery_percent"] = int(bat.percent)
                state["battery_plugged"] = bool(bat.power_plugged)
        except Exception:
            pass

        # 2. Real CPU Usage
        try:
            state["cpu_percent"] = float(psutil.cpu_percent(interval=None))
        except Exception:
            pass

        # 3. Network / Wi-Fi Check
        try:
            net_stats = psutil.net_if_stats()
            has_up_nic = any(nic.isup for nic in net_stats.values() if nic.isup)
            state["network_connected"] = has_up_nic
        except Exception:
            pass

        return state

    # ==========================================
    # EVALUATION LOOP & HYSTERESIS LOGIC
    # ==========================================
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print("[AUTOMATION] Automation Engine background monitor started.")

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=1.0)
            except Exception:
                pass
        self._thread = None
        print("[AUTOMATION] Automation Engine stopped.")

    def _monitor_loop(self):
        while self._running:
            try:
                self._evaluate_rules()
            except Exception as e:
                print(f"[AUTOMATION] Error evaluating rules: {e}")
            time.sleep(self.check_interval)

    def _evaluate_rules(self):
        state = self.get_current_system_state()

        with self._lock:
            active_rules = list(self.rules)

        for rule in active_rules:
            if not rule.enabled:
                continue

            current_val = None
            is_condition_met = False

            # --- Battery Metric ---
            if rule.metric == "battery":
                current_val = state["battery_percent"]
                thresh = float(rule.threshold)
                if rule.operator in ["<=", "<"]:
                    is_condition_met = current_val <= thresh
                    # Reset hysteresis: when battery rises significantly above threshold
                    if current_val > thresh + 1.0:
                        rule.is_triggered = False
                elif rule.operator in [">=", ">"]:
                    is_condition_met = current_val >= thresh
                    # Reset hysteresis: when battery drops below threshold
                    if current_val < thresh - 1.0:
                        rule.is_triggered = False
                elif rule.operator in ["==", "="]:
                    is_condition_met = current_val == thresh
                    if current_val != thresh:
                        rule.is_triggered = False

            # --- CPU Metric ---
            elif rule.metric == "cpu":
                current_val = state["cpu_percent"]
                thresh = float(rule.threshold)
                if rule.operator in [">=", ">"]:
                    is_condition_met = current_val >= thresh
                    # Reset when CPU falls below threshold - 5%
                    if current_val < max(0.0, thresh - 5.0):
                        rule.is_triggered = False
                elif rule.operator in ["<=", "<"]:
                    is_condition_met = current_val <= thresh
                    if current_val > thresh + 5.0:
                        rule.is_triggered = False

            # --- Network Metric ---
            elif rule.metric in ["network", "wifi"]:
                is_connected = state["network_connected"]
                target_state = str(rule.threshold).lower()
                if target_state in ["disconnected", "off", "lost", "0", "false"]:
                    is_condition_met = not is_connected
                    if is_connected:
                        rule.is_triggered = False
                else:
                    is_condition_met = is_connected
                    if not is_connected:
                        rule.is_triggered = False

            # --- Trigger Action (Edge-Triggered) ---
            if is_condition_met and not rule.is_triggered:
                rule.is_triggered = True
                rule.last_triggered_time = time.time()
                self._fire_action(rule, state)

    def _fire_action(self, rule: AutomationRule, state: Dict[str, Any]):
        """Fires the configured action completely locally without calling Gemini."""
        msg = rule.alert_message or f"Alert: {rule.name} triggered."
        print(f"[AUTOMATION TRIGGERED] {rule.name}: {msg}")

        # 1. Voice Announcement via Kokoro TTS
        if "voice" in rule.action_type and self.tts_callback:
            try:
                self.tts_callback(msg, "HINGLISH")
            except Exception as e:
                print(f"[AUTOMATION] Error executing voice action: {e}")

        # 2. UI Notification Callback
        if self.on_trigger_callback:
            try:
                self.on_trigger_callback(rule, state)
            except Exception as e:
                print(f"[AUTOMATION] Error executing trigger callback: {e}")

    # ==========================================
    # NATURAL LANGUAGE PARSER
    # ==========================================
    @classmethod
    def parse_natural_language_rule(cls, prompt: str) -> Optional[AutomationRule]:
        """
        Parses user intent from English, Hindi, or Hinglish text into an AutomationRule.
        Examples:
        - "Jab meri battery 30% ho jaye to mujhe bata dena." -> battery <= 30
        - "Tell me when my battery goes below 20%." -> battery <= 20
        - "Battery full ho jaye to bol dena." -> battery >= 100
        - "Jab Wi-Fi disconnect ho to mujhe bata dena." -> network == disconnected
        - "CPU 90% se upar jaye to warn karna." -> cpu >= 90
        """
        text = prompt.lower().strip()

        # 1. Battery Conditions
        if "battery" in text or "charging" in text or "charge" in text:
            # Battery full
            if "full" in text or "100" in text:
                return AutomationRule(
                    rule_id=str(uuid.uuid4())[:8],
                    name="Battery Full Alert",
                    metric="battery",
                    operator=">=",
                    threshold=100.0,
                    alert_message="Battery full ho gayi hai. Aap charger nikal sakte hain."
                )

            # Extract percentage (e.g. 30%, 20 percent, below 15)
            m = re.search(r"(\d{1,3})\s*(?:%|percent|pratishat)?", text)
            if m:
                val = float(m.group(1))
                if 0 <= val <= 100:
                    op = "<="
                    if any(w in text for w in ["upar", "above", "more than", "reach", "cross", "jyada"]):
                        op = ">="
                    elif any(w in text for w in ["below", "niche", "kam", "ho jaye", "drops", "less than"]):
                        op = "<="

                    msg = f"Battery {int(val)} percent ho gayi hai. Kripya dhyan dein."
                    if val <= 30:
                        msg = f"Battery {int(val)} percent ho gayi hai. Charger laga lijiye."
                    elif val >= 80:
                        msg = f"Battery {int(val)} percent pahunch gayi hai."

                    return AutomationRule(
                        rule_id=str(uuid.uuid4())[:8],
                        name=f"Battery {op} {int(val)}%",
                        metric="battery",
                        operator=op,
                        threshold=val,
                        alert_message=msg
                    )

        # 2. CPU Conditions
        if "cpu" in text or "processor" in text:
            m = re.search(r"(\d{1,3})\s*(?:%|percent)?", text)
            if m:
                val = float(m.group(1))
                op = ">=" if any(w in text for w in ["upar", "above", "cross", "high", "jyada"]) else "<="
                return AutomationRule(
                    rule_id=str(uuid.uuid4())[:8],
                    name=f"CPU {op} {int(val)}%",
                    metric="cpu",
                    operator=op,
                    threshold=val,
                    alert_message=f"Warning: CPU usage {int(val)} percent se upar pahunch gaya hai."
                )

        # 3. Wi-Fi / Network Conditions
        if "wi-fi" in text or "wifi" in text or "network" in text or "internet" in text:
            if any(w in text for w in ["disconnect", "lost", "band", "chala jaye", "off", "drop"]):
                return AutomationRule(
                    rule_id=str(uuid.uuid4())[:8],
                    name="Wi-Fi Disconnected Alert",
                    metric="network",
                    operator="==",
                    threshold="disconnected",
                    alert_message="Wi-Fi connection disconnect ho gaya hai."
                )
            elif any(w in text for w in ["connect", "online", "wapas", "restore"]):
                return AutomationRule(
                    rule_id=str(uuid.uuid4())[:8],
                    name="Wi-Fi Connected Alert",
                    metric="network",
                    operator="==",
                    threshold="connected",
                    alert_message="Wi-Fi connect ho gaya hai."
                )

        return None


# Global singleton instance
automation_engine = AutomationEngine()
