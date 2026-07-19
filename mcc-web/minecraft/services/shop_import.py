# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pathlib import Path

import yaml
from django.db import transaction
from django.utils.text import slugify

from minecraft.models import MinecraftShopCategory, MinecraftShopItem


_COLOR_CODE_PATTERN = re.compile(r"[&§][0-9a-fk-orA-FK-OR]")
_MATERIAL_PREFIX_PATTERN = re.compile(r"^minecraft:")


@dataclass
class ShopImportResult:
    categories_created: int = 0
    categories_updated: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def stem_from_filename(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1]
    for suffix in (".yml", ".yaml"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


def slug_from_filename(filename: str) -> str:
    stem = stem_from_filename(filename)
    slug = slugify(stem, allow_unicode=False).replace("-", "_")
    return slug or stem.lower()


def shop_relative_path(filepath: str) -> str:
    """Normalize a path relative to the shops/ or sections/ root."""
    return filepath.replace("\\", "/").lstrip("./")


def normalize_shop_upload_relative_path(relative_path: str) -> str | None:
    """
    Normalize browser upload paths to shops/-relative paths.

    Returns None for section YAML accidentally included in the shop upload
    (e.g. when the EconomyShopGUI root folder was selected).
    """
    path = shop_relative_path(relative_path)
    lower = path.lower()
    if lower.startswith("sections/"):
        return None
    if lower.startswith("shops/"):
        return path[6:]
    return path


def normalize_section_upload_relative_path(relative_path: str) -> str | None:
    """Normalize browser upload paths to sections/-relative paths."""
    path = shop_relative_path(relative_path)
    lower = path.lower()
    if lower.startswith("shops/"):
        return None
    if lower.startswith("sections/"):
        return path[9:]
    return path


def esgui_section_from_shop_path(relative_path: str) -> str:
    """
    EconomyShopGUI section id: path under shops/ without extension.

    Examples:
        misc.yml -> misc
        Mobs/spawn_eggs.yml -> Mobs/spawn_eggs
    """
    path = shop_relative_path(relative_path)
    stem = path
    for suffix in (".yml", ".yaml"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


def slug_from_shop_path(relative_path: str) -> str:
    """Unique MCC slug for a shop file, including nested paths."""
    section = esgui_section_from_shop_path(relative_path)
    slug = slugify(section.replace("/", "_"), allow_unicode=False).replace("-", "_")
    if slug:
        return slug
    return slug_from_filename(relative_path)


def esgui_section_from_filename(filename: str) -> str:
    """Backward-compatible alias for flat filenames."""
    return esgui_section_from_shop_path(filename)


def index_section_files(section_files: dict[str, str]) -> dict[str, str]:
    """Build lookup keys for section YAML (flat and nested layouts)."""
    indexed: dict[str, str] = {}
    for rel_path, content in section_files.items():
        rel = shop_relative_path(rel_path)
        indexed[rel] = content
        stem = esgui_section_from_shop_path(rel)
        indexed[stem] = content
        indexed[slug_from_shop_path(rel)] = content
        indexed[stem_from_filename(rel)] = content
    return indexed


def resolve_section_content(
    section_files: dict[str, str], shop_rel_path: str, slug: str
) -> str | None:
    section_path = esgui_section_from_shop_path(shop_rel_path)
    basename = stem_from_filename(shop_rel_path)
    for key in (
        section_path,
        section_path.replace("/", "_"),
        slug,
        basename,
        f"{basename}.yml",
        f"{basename}.yaml",
    ):
        content = section_files.get(key)
        if content is not None:
            return content
    return None


def is_shop_yaml_path(relative_path: str) -> bool:
    """EconomyShopGUI shop/section YAML only — no backups, DB, or other formats."""
    lower = shop_relative_path(relative_path).lower()
    if lower.endswith(".bak") or ".bak." in lower:
        return False
    return lower.endswith((".yml", ".yaml"))


def collect_yaml_files(root: Path) -> dict[str, str]:
    """Read all YAML files under root, keyed by POSIX path relative to root."""
    files: dict[str, str] = {}
    if not root.is_dir():
        return files

    collected: list[Path] = []
    for pattern in ("*.yml", "*.yaml"):
        collected.extend(root.rglob(pattern))

    for path in sorted(set(collected)):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if not is_shop_yaml_path(rel):
            continue
        files[rel] = path.read_text(encoding="utf-8")
    return files


def strip_minecraft_colors(value: str) -> str:
    cleaned = _COLOR_CODE_PATTERN.sub("", value or "")
    return " ".join(cleaned.split())


def item_display_name_from_yaml(item: dict) -> str:
    """Read ESGUI display name from display-name, display_name, or name."""
    for key in ("display-name", "display_name", "name"):
        raw = item.get(key)
        if raw:
            return strip_minecraft_colors(str(raw))[:128]
    return ""


def normalize_material(raw_material: str) -> str:
    material = str(raw_material).strip()
    material = _MATERIAL_PREFIX_PATTERN.sub("", material)
    return material.upper().replace("-", "_")


def _parse_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off"}
    return bool(value)


def _item_sort_key(value: str):
    return (0, int(value)) if str(value).isdigit() else (1, str(value))


def parse_esgui_section_meta(content: str, slug: str) -> dict:
    data = yaml.safe_load(content) or {}
    if not isinstance(data, dict):
        raise ValueError("Section YAML must define a mapping")

    title = data.get("title") or data.get("item", {}).get("name") or slug
    name = strip_minecraft_colors(str(title)) or slug.replace("_", " ").title()
    slot = data.get("slot", 0)
    try:
        sort_order = int(slot)
    except (TypeError, ValueError):
        sort_order = 0

    return {
        "name": name[:64],
        "enabled": _parse_bool(data.get("enable"), default=True),
        "sort_order": max(0, sort_order),
    }


def parse_esgui_shop_items(content: str) -> list[dict]:
    data = yaml.safe_load(content) or {}
    if not isinstance(data, dict):
        raise ValueError("Shop YAML must define a mapping")

    pages = data.get("pages") or {}
    if not isinstance(pages, dict):
        raise ValueError("Shop YAML must contain a pages mapping")

    items: list[dict] = []
    sort_order = 0
    for page_key in sorted(pages.keys(), key=_item_sort_key):
        page = pages.get(page_key) or {}
        if not isinstance(page, dict):
            continue
        page_items = page.get("items") or {}
        if not isinstance(page_items, dict):
            continue

        for item_key in sorted(page_items.keys(), key=_item_sort_key):
            item = page_items.get(item_key)
            if not isinstance(item, dict):
                continue

            material_raw = item.get("material")
            if not material_raw:
                continue

            buy = item.get("buy")
            if buy is None:
                continue
            try:
                buy_price = float(buy)
            except (TypeError, ValueError):
                continue
            if buy_price < 0:
                continue

            item_loc = f"{page_key}.items.{item_key}"
            display_name = item_display_name_from_yaml(item)

            stack_size = item.get("stack-size", item.get("stack_size", 1))
            try:
                stack_size = max(1, int(stack_size))
            except (TypeError, ValueError):
                stack_size = 1

            sort_order += 1
            items.append(
                {
                    "material": normalize_material(material_raw),
                    "display_name": display_name,
                    "esgui_item_key": str(item_key),
                    "esgui_item_loc": item_loc,
                    "buy_price_velos": max(0, int(round(buy_price))),
                    "stack_size": stack_size,
                    "sort_order": sort_order,
                    "enabled": True,
                }
            )

    return items


@transaction.atomic
def import_esgui_catalog(
    *,
    shop_files: dict[str, str],
    section_files: dict[str, str] | None = None,
    replace_items: bool = False,
) -> ShopImportResult:
    """Import EconomyShopGUI shop/section YAML into MCC shop models."""
    result = ShopImportResult()
    section_index = index_section_files(section_files or {})

    for rel_path, content in shop_files.items():
        shop_rel = shop_relative_path(rel_path)
        if not is_shop_yaml_path(shop_rel):
            continue
        slug = slug_from_shop_path(shop_rel)
        esgui_section = esgui_section_from_shop_path(shop_rel)
        if not slug:
            result.errors.append(f"{shop_rel}: invalid path")
            continue

        try:
            parsed_items = parse_esgui_shop_items(content)
        except (yaml.YAMLError, ValueError) as exc:
            result.errors.append(f"{shop_rel}: {exc}")
            continue

        section_meta = {
            "name": slug.replace("_", " ").title(),
            "enabled": True,
            "sort_order": 0,
        }
        section_content = resolve_section_content(section_index, shop_rel, slug)
        if section_content:
            try:
                section_meta = parse_esgui_section_meta(section_content, slug)
            except (yaml.YAMLError, ValueError) as exc:
                result.errors.append(f"sections/{esgui_section}.yml: {exc}")

        category, created = MinecraftShopCategory.objects.get_or_create(
            slug=slug,
            defaults={
                "name": section_meta["name"],
                "esgui_section": esgui_section,
                "sort_order": section_meta["sort_order"],
                "enabled": section_meta["enabled"],
            },
        )
        if created:
            result.categories_created += 1
        else:
            category.name = section_meta["name"]
            category.esgui_section = esgui_section
            category.sort_order = section_meta["sort_order"]
            category.enabled = section_meta["enabled"]
            category.save(
                update_fields=["name", "esgui_section", "sort_order", "enabled"]
            )
            result.categories_updated += 1

        if replace_items:
            category.items.all().delete()

        for item_data in parsed_items:
            if item_data["buy_price_velos"] <= 0:
                result.items_skipped += 1
                continue

            item_loc = (item_data.get("esgui_item_loc") or "").strip()
            if not item_loc:
                result.items_skipped += 1
                result.errors.append(f"{shop_rel}: missing esgui_item_loc for {item_data.get('material')}")
                continue

            _, item_created = MinecraftShopItem.objects.update_or_create(
                category=category,
                esgui_item_loc=item_loc,
                defaults={
                    "material": item_data["material"],
                    "display_name": item_data["display_name"],
                    "esgui_item_key": item_data.get("esgui_item_key", ""),
                    "buy_price_velos": item_data["buy_price_velos"],
                    "stack_size": item_data["stack_size"],
                    "sort_order": item_data["sort_order"],
                    "enabled": item_data["enabled"],
                },
            )
            if item_created:
                result.items_created += 1
            else:
                result.items_updated += 1

    return result
