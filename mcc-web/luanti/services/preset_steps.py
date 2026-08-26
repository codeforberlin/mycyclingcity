# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Line-based editor format for LuantiCityPreset.steps (not hardcoded at runtime).

from __future__ import annotations

import json
import re
from typing import Any

MAX_STEPS = 50
MAX_LINE_LEN = 256

ALLOWED_OPS = frozenset({"set_time", "set_time_speed", "set_weather", "chat"})

_OP_LINE = re.compile(
    r"^(?P<op>set_time_speed|set_time|set_weather|chat)\s+(?P<rest>.+)$",
    re.IGNORECASE,
)


def steps_to_text(steps: list | None) -> str:
    """Serialize steps for the preset editor textarea (one step per line)."""
    lines: list[str] = []
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        op = str(step.get("op") or "").strip().lower()
        if op == "set_time":
            lines.append(f"set_time {step.get('value', 6000)}")
        elif op == "set_time_speed":
            lines.append(f"set_time_speed {step.get('value', 72)}")
        elif op == "set_weather":
            lines.append(f"set_weather {step.get('value') or step.get('weather') or 'clear'}")
        elif op == "chat":
            lines.append(f"chat {step.get('message') or ''}")
        else:
            lines.append(json.dumps(step, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines)


def parse_steps_text(text: str) -> list[dict[str, Any]]:
    """
    Parse editor text into step dicts.

    Supported lines:
      set_time 6000
      set_time_speed 0
      set_weather clear
      chat Es ist Tag.
      {"op":"set_time","value":6000}
    Empty lines and # comments are ignored.
    """
    steps: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Ungültiges JSON: {line[:60]}") from exc
            if not isinstance(obj, dict) or not obj.get("op"):
                raise ValueError(f"JSON-Schritt braucht ein 'op'-Feld: {line[:60]}")
            steps.append(obj)
            continue
        match = _OP_LINE.match(line)
        if not match:
            raise ValueError(
                "Unbekannte Zeile (erlaubt: set_time / set_time_speed / "
                f"set_weather / chat / JSON): {line[:60]}"
            )
        op = match.group("op").lower()
        rest = match.group("rest").strip()
        if op == "set_time":
            try:
                value = int(rest.split()[0])
            except (ValueError, IndexError) as exc:
                raise ValueError(f"set_time braucht eine Zahl: {line[:60]}") from exc
            steps.append({"op": "set_time", "value": value})
        elif op == "set_time_speed":
            try:
                value = int(rest.split()[0])
            except (ValueError, IndexError) as exc:
                raise ValueError(f"set_time_speed braucht eine Zahl: {line[:60]}") from exc
            steps.append({"op": "set_time_speed", "value": max(0, value)})
        elif op == "set_weather":
            weather = rest.split()[0].lower() if rest else "clear"
            steps.append({"op": "set_weather", "value": weather})
        elif op == "chat":
            steps.append({"op": "chat", "message": rest})
    return steps


def validate_steps(steps: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    if not steps:
        errors.append("Mindestens ein Schritt ist erforderlich.")
        return errors, warnings
    if len(steps) > MAX_STEPS:
        errors.append(f"Maximal {MAX_STEPS} Schritte erlaubt.")
    for i, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"Schritt {i}: kein Objekt.")
            continue
        op = str(step.get("op") or "").strip().lower()
        if op not in ALLOWED_OPS:
            errors.append(f"Schritt {i}: unbekannte Operation '{op}'.")
            continue
        encoded = json.dumps(step, ensure_ascii=False)
        if len(encoded) > MAX_LINE_LEN * 2:
            warnings.append(f"Schritt {i}: sehr lang — Bridge könnte kürzen.")
        if op == "set_time" and step.get("value") is None:
            errors.append(f"Schritt {i}: set_time braucht value.")
        if op == "set_time_speed" and step.get("value") is None:
            errors.append(f"Schritt {i}: set_time_speed braucht value.")
        if op == "set_weather" and not (step.get("value") or step.get("weather")):
            errors.append(f"Schritt {i}: set_weather braucht value.")
        if op == "chat" and not str(step.get("message") or "").strip():
            errors.append(f"Schritt {i}: chat braucht message.")
    return errors, warnings
