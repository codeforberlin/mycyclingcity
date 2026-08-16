# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    vehiclesplus_catalog.py
# @note    Scan VehiclesPlus vehicle *.hjson files for Vergabe-Katalog UI.

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

# Minecraft § / & color and formatting codes in display names.
_MC_COLOR_RE = re.compile(r"[§&][0-9a-fk-or]", re.IGNORECASE)
_ID_RE = re.compile(r"(?m)^\s*id\s*:\s*(?P<id>[A-Za-z0-9_]+)\s*$")
_DISPLAY_RE = re.compile(
    r"(?m)^\s*displayName\s*:\s*(?P<name>.+?)\s*$",
)


@dataclass(frozen=True)
class VehiclesPlusModel:
    model_id: str
    category: str
    display_name: str
    path: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.model_id,
            "category": self.category,
            "display_name": self.display_name,
            "path": self.path,
        }


def vehiclesplus_vehicles_dir() -> Path:
    raw = getattr(settings, "MCC_MINECRAFT_VEHICLESPLUS_VEHICLES_DIR", "") or ""
    if raw:
        return Path(raw)
    paper = getattr(settings, "MCC_MINECRAFT_PAPER_DIR", "") or ""
    return Path(paper) / "plugins" / "VehiclesPlus" / "vehicles"


def strip_minecraft_colors(text: str) -> str:
    cleaned = _MC_COLOR_RE.sub("", text or "")
    return " ".join(cleaned.split()).strip()


def _clean_hjson_scalar(raw: str) -> str:
    text = (raw or "").strip()
    # Trailing HJSON punctuation on same line (rare one-liners).
    text = text.rstrip(",").strip()
    if text.endswith("}") and "{" not in text:
        text = text[:-1].strip()
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        text = text[1:-1]
    return text.strip()


def parse_vehiclesplus_hjson(text: str, *, fallback_id: str = "") -> tuple[str, str]:
    """
    Extract (model_id, display_name) from a VehiclesPlus .hjson body.

    Uses light regex parsing (HJSON is not strict JSON).
    """
    model_id = fallback_id
    match_id = _ID_RE.search(text or "")
    if match_id:
        model_id = match_id.group("id").strip()
    else:
        # One-line / inline: id: ExampleBike
        inline_id = re.search(r"\bid\s*:\s*([A-Za-z0-9_]+)", text or "")
        if inline_id:
            model_id = inline_id.group(1).strip()

    display = model_id
    match_dn = _DISPLAY_RE.search(text or "")
    raw = ""
    if match_dn:
        raw = match_dn.group("name")
    else:
        inline_dn = re.search(r"\bdisplayName\s*:\s*([^\n]+)", text or "")
        if inline_dn:
            raw = inline_dn.group(1)
    if raw:
        display = strip_minecraft_colors(_clean_hjson_scalar(raw)) or model_id
    return model_id, display


def list_vehiclesplus_models(
    *,
    root: Path | str | None = None,
) -> list[VehiclesPlusModel]:
    """
    Scan VehiclesPlus vehicles directory for *.hjson definitions.

    Returns sorted list (category, display_name, model_id). Empty if path missing.
    """
    base = Path(root) if root is not None else vehiclesplus_vehicles_dir()
    if not base.is_dir():
        return []

    found: dict[str, VehiclesPlusModel] = {}
    for path in sorted(base.rglob("*.hjson")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fallback = path.stem
        model_id, display = parse_vehiclesplus_hjson(text, fallback_id=fallback)
        if not model_id:
            continue
        try:
            category = path.relative_to(base).parts[0] if path.parent != base else ""
        except ValueError:
            category = path.parent.name
        found[model_id] = VehiclesPlusModel(
            model_id=model_id,
            category=category or "other",
            display_name=display or model_id,
            path=str(path),
        )

    return sorted(
        found.values(),
        key=lambda m: (m.category.lower(), m.display_name.lower(), m.model_id.lower()),
    )


def vehiclesplus_models_by_category(
    *,
    root: Path | str | None = None,
) -> list[tuple[str, list[VehiclesPlusModel]]]:
    """Group models for <optgroup> rendering."""
    grouped: dict[str, list[VehiclesPlusModel]] = {}
    for model in list_vehiclesplus_models(root=root):
        grouped.setdefault(model.category, []).append(model)
    return sorted(grouped.items(), key=lambda kv: kv[0].lower())
