# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    shop_labels.py
# @note    Multilingual shop item display names (DE/EN, extensible).

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import transaction

from luanti.models import (
    LuantiRegisteredItem,
    LuantiShopCategory,
    LuantiShopCategoryLabel,
    LuantiShopItem,
    LuantiShopItemLabel,
)

DEFAULT_LANG = "de"
FALLBACK_LANGS = ("de", "en")

# Common EconomyShopGUI / Mineclonia shop slugs → German tab titles for children.
CATEGORY_SLUG_LABELS_DE: dict[str, str] = {
    "blocks": "Blöcke",
    "block": "Blöcke",
    "building_blocks": "Baublöcke",
    "tools": "Werkzeuge",
    "tool": "Werkzeuge",
    "weapons": "Waffen",
    "weapon": "Waffen",
    "armor": "Rüstung",
    "armour": "Rüstung",
    "food": "Essen",
    "foods": "Essen",
    "farming": "Landwirtschaft",
    "farm": "Landwirtschaft",
    "redstone": "Redstone",
    "decoration": "Dekoration",
    "decorative": "Dekoration",
    "decorations": "Dekoration",
    "misc": "Sonstiges",
    "miscellaneous": "Sonstiges",
    "ores": "Erze",
    "minerals": "Erze",
    "wood": "Holz",
    "wool": "Wolle",
    "glass": "Glas",
    "transport": "Transport",
    "rails": "Schienen",
    "rail": "Schienen",
    "potions": "Tränke",
    "enchanting": "Verzauberung",
    "spawn_eggs": "Spawn-Eier",
    "fences": "Zäune",
    "stairs": "Treppen",
    "slabs": "Platten",
    "dyes": "Farbstoffe",
    "flowers": "Blumen",
    "plants": "Pflanzen",
    "mobs": "Kreaturen",
    "spawn": "Spawn-Eier",
}

CATEGORY_SLUG_LABELS_EN: dict[str, str] = {
    slug: slug.replace("_", " ").title()
    for slug in CATEGORY_SLUG_LABELS_DE
}

# Extra terms so queries like "Holz" match the wood tab (slug "wood") and its items.
CATEGORY_SLUG_SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "wood": ("holz", "holzart", "bretter", "balken", "stamm", "plank"),
    "blocks": ("block", "blöcke", "stein", "ziegel"),
    "tools": ("werkzeug", "axt", "spitzhacke", "schaufel", "hacke"),
    "food": ("essen", "nahrung"),
    "farm": ("farm", "acker", "saat", "farming", "landwirtschaft"),
    "ores": ("erz", "mineral"),
    "wool": ("wolle", "schaf"),
    "glass": ("glas", "fenster"),
    "rails": ("schiene", "zug", "minecart"),
    "decoration": ("deko", "dekoration", "schmuck"),
    "misc": ("sonstiges", "misc"),
}

# English node tokens in itemstrings → German terms kids type (birch → birke/birken).
ITEM_NODE_TOKEN_ALIASES_DE: dict[str, tuple[str, ...]] = {
    "birch": ("birke", "birken"),
    "oak": ("eiche", "eichen"),
    "spruce": ("fichte", "fichten"),
    "jungle": ("dschungel", "tropenholz"),
    "dark_oak": ("schwarzeiche", "schwarzeichen"),
    "acacia": ("akazie", "akazien"),
    "mangrove": ("mangrove", "mangroven"),
    "cherry": ("kirsche", "kirsch", "kirschholz"),
    "bamboo": ("bambus",),
    "stripped": ("entrinde", "entrindet", "rinde"),
    "planks": ("bretter", "brett"),
    "plank": ("bretter", "brett", "planke"),
    "wood": ("holz",),
    "tree": ("baum", "stamm"),
    "log": ("stamm", "baumstamm"),
    "leaves": ("laub", "blatter"),
    "sapling": ("setzling",),
    "stick": ("stock", "stecken"),
    "cobblestone": ("bruchstein", "pflaster"),
    "cobble": ("bruchstein",),
    "stone": ("stein",),
    "sand": ("sand",),
    "glass": ("glas",),
    "wool": ("wolle",),
    "iron": ("eisen",),
    "gold": ("gold",),
    "diamond": ("diamant",),
    "coal": ("kohle",),
    "torch": ("fackel",),
    "door": ("tur", "tuer"),
    "fence": ("zaun",),
    "stairs": ("treppe", "stufen"),
    "slab": ("platte", "stufe"),
}

_TR_ESCAPE = {
    "@@": "@",
    "@=": "=",
    "@n": "\n",
}


def normalize_language_code(raw: str | None) -> str:
    code = (raw or "").strip().lower().replace("_", "-")
    if not code:
        return DEFAULT_LANG
    primary = code.split("-", 1)[0]
    if primary in ("de", "en"):
        return primary
    return primary[:16] or DEFAULT_LANG


def _unescape_tr_value(s: str) -> str:
    out = s
    for seq, repl in _TR_ESCAPE.items():
        out = out.replace(seq, repl)
    return out


def parse_tr_file(path: Path) -> dict[str, str]:
    """Parse Luanti .tr file: original=translated (keys are source strings)."""
    result: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        orig, _, trans = line.partition("=")
        orig = _unescape_tr_value(orig.strip())
        trans = _unescape_tr_value(trans.strip())
        if orig:
            result[orig] = trans
    return result


def build_german_to_english_map(locale_root: Path) -> dict[str, str]:
    """
    Mineclonia .de.tr maps English source -> German translation.
    Invert to lookup EN label from DE text.
    """
    de_to_en: dict[str, str] = {}
    if not locale_root.is_dir():
        return de_to_en
    for path in locale_root.rglob("*.de.tr"):
        for en_src, de_trans in parse_tr_file(path).items():
            if de_trans and en_src:
                de_to_en[de_trans] = en_src
    return de_to_en


def build_english_to_german_map(locale_root: Path) -> dict[str, str]:
    """English source string -> German translation from all locale/*.de.tr files."""
    en_to_de: dict[str, str] = {}
    if not locale_root.is_dir():
        return en_to_de
    for path in locale_root.rglob("*.de.tr"):
        for en_src, de_trans in parse_tr_file(path).items():
            if de_trans and en_src:
                en_to_de[en_src] = de_trans
    return en_to_de


_MCL_ESC = "\x1b"


def _looks_like_mcl_rich_description(s: str) -> bool:
    text = s or ""
    return bool(
        _MCL_ESC in text
        or "(T@" in text
        or re.search(r"@\w+\)", text)
        or "mcl_tt" in text
        or re.search(r"\bArmor points:\s*", text, flags=re.I)
    )


def plain_shop_label(s: str | None, max_len: int = 128) -> str:
    """Strip Mineclonia/MCL rich item descriptions to a short plain title."""
    text = str(s or "")
    text = re.sub(r"[\r\n]+", " ", text)

    title_match = re.search(
        r"\(T@[^)]+\)([^(\x1b]+?)(?:"
        + re.escape(_MCL_ESC)
        + r"E|"
        + re.escape(_MCL_ESC)
        + r"|\(|$)",
        text,
    )
    if title_match:
        text = title_match.group(1).strip()
    else:
        text = re.sub(re.escape(_MCL_ESC) + r"[^(\x1b]*", " ", text)
        text = re.sub(re.escape(_MCL_ESC) + r".?", " ", text)
        text = re.sub(r"\([^)]*@[^)]*\)", " ", text)
        while True:
            nxt = re.sub(r"@\S+\)", " ", text)
            if nxt == text:
                break
            text = nxt
        text = text.replace("@", "")
        text = re.split(
            r"\s+(?:Feet|Head|Torso|Legs)\s+armor\b", text, maxsplit=1, flags=re.I
        )[0]
        text = re.split(r"\s+Armor points:\s*", text, maxsplit=1, flags=re.I)[0]

    text = text.replace("\\", "")
    text = re.sub(r"\s+", " ", text).strip()
    if max_len > 0 and len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def cleaned_display_name(s: str | None, max_len: int = 128) -> str:
    """Plain title for UI/API; leaves already-clean strings unchanged."""
    raw = (s or "").strip()
    if not raw:
        return ""
    if _looks_like_mcl_rich_description(raw):
        return plain_shop_label(raw, max_len=max_len)
    return raw[:max_len] if max_len > 0 else raw


def labels_map_for_items(item_ids: list[int]) -> dict[int, dict[str, str]]:
    if not item_ids:
        return {}
    out: dict[int, dict[str, str]] = {}
    for row in LuantiShopItemLabel.objects.filter(item_id__in=item_ids).values(
        "item_id", "language_code", "display_name"
    ):
        item_id = row["item_id"]
        lang = normalize_language_code(row["language_code"])
        name = (row["display_name"] or "").strip()
        if not name:
            continue
        out.setdefault(item_id, {})[lang] = name[:128]
    return out


def resolve_item_display_name(
    item: LuantiShopItem,
    lang: str,
    *,
    labels: dict[str, str] | None = None,
) -> str:
    """Fallback: requested lang -> de -> en -> legacy display_name -> item_name."""
    lang = normalize_language_code(lang)
    label_map = labels or {}
    for code in (lang, *FALLBACK_LANGS):
        if code in label_map and label_map[code]:
            return cleaned_display_name(label_map[code])
    legacy = (item.display_name or "").strip()
    if legacy:
        return cleaned_display_name(legacy)
    return item.item_name


def resolve_search_labels(
    item: LuantiShopItem,
    *,
    labels: dict[str, str] | None = None,
) -> dict[str, str]:
    merged = dict(labels or {})
    legacy = (item.display_name or "").strip()
    if legacy and "de" not in merged:
        merged["de"] = legacy[:128]
    return merged


def _humanize_itemstring(item_name: str) -> str:
    tail = (item_name or "").split(":", 1)[-1]
    return tail.replace("_", " ").replace("-", " ").strip()


def _german_search_aliases_from_item_name(item_name: str) -> list[str]:
    """Map mcl_core:birch_* etc. to German search syllables (Birk → Birke)."""
    tail = (item_name or "").lower().split(":", 1)[-1]
    tokens = re.split(r"[_\-\.]+", tail)
    found: list[str] = []
    seen_keys: set[str] = set()

    def add_for_key(key: str) -> None:
        if not key or key in seen_keys:
            return
        aliases = ITEM_NODE_TOKEN_ALIASES_DE.get(key)
        if aliases:
            seen_keys.add(key)
            found.extend(aliases)

    for i, token in enumerate(tokens):
        add_for_key(token)
        if i + 1 < len(tokens):
            add_for_key(f"{token}_{tokens[i + 1]}")
    tail_lower = tail.lower()
    for token_key, aliases in ITEM_NODE_TOKEN_ALIASES_DE.items():
        if token_key in tail_lower and token_key not in seen_keys:
            seen_keys.add(token_key)
            found.extend(aliases)
    return found


def normalize_shop_search_text(text: str) -> str:
    """Case-insensitive shop filter text (ASCII-friendly for Luanti string.find)."""
    folded = (text or "").casefold()
    for src, dst in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        folded = folded.replace(src, dst)
    return folded


def build_item_search_blob(
    item: LuantiShopItem,
    *,
    labels: dict[str, str] | None = None,
    resolved_display_name: str = "",
    category: LuantiShopCategory | None = None,
    category_labels: dict[str, str] | None = None,
    registry_description: str = "",
) -> str:
    """Lowercase text used for client-side shop filter (names, category, aliases)."""
    parts: list[str] = []
    shown = (resolved_display_name or "").strip()
    if shown:
        parts.append(shown)
    for name in (labels or {}).values():
        text = (name or "").strip()
        if text:
            parts.append(text)
    legacy = (item.display_name or "").strip()
    if legacy:
        parts.append(legacy)
    parts.append(_humanize_itemstring(item.item_name))
    parts.append((item.item_name or "").strip())

    if category is not None:
        parts.append((category.slug or "").replace("_", " "))
        parts.append((category.name or "").strip())
        slug = (category.slug or "").lower()
        for alias in CATEGORY_SLUG_SEARCH_ALIASES.get(slug, ()):
            parts.append(alias)
    for name in (category_labels or {}).values():
        text = (name or "").strip()
        if text:
            parts.append(text)

    reg = (registry_description or "").strip()
    if reg:
        parts.append(reg)

    parts.extend(_german_search_aliases_from_item_name(item.item_name))

    return normalize_shop_search_text(" ".join(parts))


@transaction.atomic
def set_item_label(
    item: LuantiShopItem,
    language_code: str,
    display_name: str,
    *,
    overwrite: bool = True,
    sync_legacy_de: bool = True,
) -> bool:
    lang = normalize_language_code(language_code)
    name = (display_name or "").strip()[:128]
    if not name:
        return False
    existing = LuantiShopItemLabel.objects.filter(item=item, language_code=lang).first()
    if existing and not overwrite:
        return False
    LuantiShopItemLabel.objects.update_or_create(
        item=item,
        language_code=lang,
        defaults={"display_name": name},
    )
    if sync_legacy_de and lang == DEFAULT_LANG:
        if item.display_name != name:
            item.display_name = name
            item.save(update_fields=["display_name"])
    return True


@dataclass
class LabelSyncResult:
    updated: int = 0
    created: int = 0
    skipped: int = 0
    missing_registry: int = 0


def _should_replace_label(item: LuantiShopItem, lang: str, overwrite: bool, only_empty: bool) -> bool:
    if overwrite and not only_empty:
        return True
    if LuantiShopItemLabel.objects.filter(item=item, language_code=lang).exists():
        if only_empty:
            row = LuantiShopItemLabel.objects.get(item=item, language_code=lang)
            return not (row.display_name or "").strip()
        return False
    legacy = (item.display_name or "").strip()
    if lang == DEFAULT_LANG and only_empty:
        return not legacy or legacy == item.item_name
    return True


@transaction.atomic
def sync_labels_from_registry(
    *,
    language_code: str = DEFAULT_LANG,
    overwrite: bool = False,
    only_empty: bool = True,
) -> LabelSyncResult:
    result = LabelSyncResult()
    lang = normalize_language_code(language_code)
    reg_map = {
        row.item_name: row.description
        for row in LuantiRegisteredItem.objects.all().only("item_name", "description")
    }
    for item in LuantiShopItem.objects.all().iterator():
        desc = plain_shop_label(reg_map.get(item.item_name) or "")[:128]
        if not desc:
            result.missing_registry += 1
            result.skipped += 1
            continue
        if not _should_replace_label(item, lang, overwrite, only_empty):
            result.skipped += 1
            continue
        existed = LuantiShopItemLabel.objects.filter(item=item, language_code=lang).exists()
        set_item_label(item, lang, desc, overwrite=True)
        if existed:
            result.updated += 1
        else:
            result.created += 1
    return result


@dataclass
class EnImportResult:
    updated: int = 0
    created: int = 0
    skipped: int = 0
    no_de_text: int = 0
    no_en_match: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class DeLocaleImportResult:
    updated: int = 0
    created: int = 0
    skipped: int = 0
    no_en_source: int = 0
    no_de_match: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ShopDeLabelStats:
    shop_items: int = 0
    de_labels_nonempty: int = 0
    de_labels_missing: int = 0


@transaction.atomic
def import_english_labels_from_locales(
    locale_root: Path | None = None,
    *,
    overwrite: bool = False,
    only_empty: bool = True,
) -> EnImportResult:
    result = EnImportResult()
    root = locale_root
    if root is None:
        raw = getattr(settings, "MCC_LUANTI_LOCALE_ROOT", "") or ""
        root = Path(raw) if raw else None
    if root is None or not root.is_dir():
        result.errors.append("locale_root_missing")
        return result

    de_to_en = build_german_to_english_map(root)
    if not de_to_en:
        result.errors.append("no_de_tr_files")
        return result

    reg_desc = {
        row.item_name: (row.description or "").strip()
        for row in LuantiRegisteredItem.objects.all().only("item_name", "description")
    }

    for item in LuantiShopItem.objects.prefetch_related("labels").all():
        de_label = ""
        row = item.labels.filter(language_code="de").first()
        if row and row.display_name:
            de_label = row.display_name.strip()
        if not de_label:
            de_label = (item.display_name or reg_desc.get(item.item_name) or "").strip()
        if not de_label:
            result.no_de_text += 1
            result.skipped += 1
            continue
        en_label = de_to_en.get(de_label)
        if not en_label:
            norm = re.sub(r"\s+", " ", de_label)
            for k, v in de_to_en.items():
                if re.sub(r"\s+", " ", k) == norm:
                    en_label = v
                    break
        if not en_label:
            result.no_en_match += 1
            result.skipped += 1
            continue
        en_label = en_label[:128]
        if not _should_replace_label(item, "en", overwrite, only_empty):
            result.skipped += 1
            continue
        existed = LuantiShopItemLabel.objects.filter(item=item, language_code="en").exists()
        set_item_label(item, "en", en_label, overwrite=True, sync_legacy_de=False)
        if existed:
            result.updated += 1
        else:
            result.created += 1
    return result


def _lookup_in_en_to_de(en_to_de: dict[str, str], source: str) -> str:
    key = (source or "").strip()
    if not key:
        return ""
    hit = en_to_de.get(key)
    if hit:
        return hit.strip()
    plain = plain_shop_label(key, max_len=0)
    if plain and plain != key:
        hit = en_to_de.get(plain)
        if hit:
            return hit.strip()
    norm = re.sub(r"\s+", " ", key)
    for k, v in en_to_de.items():
        if re.sub(r"\s+", " ", k) == norm:
            return v.strip()
    return ""


@transaction.atomic
def import_german_labels_from_locales(
    locale_root: Path | None = None,
    *,
    overwrite: bool = False,
    only_empty: bool = True,
) -> DeLocaleImportResult:
    """Set DE labels by matching registry/legacy English text to Mineclonia .de.tr keys."""
    result = DeLocaleImportResult()
    root = locale_root
    if root is None:
        raw = getattr(settings, "MCC_LUANTI_LOCALE_ROOT", "") or ""
        root = Path(raw) if raw else None
    if root is None or not root.is_dir():
        result.errors.append("locale_root_missing")
        return result

    en_to_de = build_english_to_german_map(root)
    if not en_to_de:
        result.errors.append("no_de_tr_files")
        return result

    reg_desc = {
        row.item_name: (row.description or "").strip()
        for row in LuantiRegisteredItem.objects.all().only("item_name", "description")
    }

    for item in LuantiShopItem.objects.prefetch_related("labels").all():
        candidates: list[str] = []
        reg = reg_desc.get(item.item_name) or ""
        if reg:
            candidates.extend(
                (
                    reg,
                    plain_shop_label(reg, max_len=0),
                    cleaned_display_name(reg),
                )
            )
        legacy = (item.display_name or "").strip()
        if legacy:
            candidates.extend(
                (
                    legacy,
                    plain_shop_label(legacy, max_len=0),
                    cleaned_display_name(legacy),
                )
            )
        row = item.labels.filter(language_code="de").first()
        if row and (row.display_name or "").strip():
            cur = row.display_name.strip()
            candidates.extend((cur, cleaned_display_name(cur)))
        de_label = ""
        for cand in candidates:
            if not cand:
                continue
            de_label = _lookup_in_en_to_de(en_to_de, cand)
            if de_label:
                break
        if not de_label:
            if not candidates:
                result.no_en_source += 1
            else:
                result.no_de_match += 1
            result.skipped += 1
            continue
        de_label = de_label[:128]
        if not _should_replace_label(item, "de", overwrite, only_empty):
            result.skipped += 1
            continue
        existed = LuantiShopItemLabel.objects.filter(item=item, language_code="de").exists()
        set_item_label(item, "de", de_label, overwrite=True)
        if existed:
            result.updated += 1
        else:
            result.created += 1
    return result


@dataclass
class DeLabelRepairResult:
    updated: int = 0
    unchanged: int = 0
    no_plain_title: int = 0
    errors: list[str] = field(default_factory=list)


@transaction.atomic
def repair_de_shop_labels(
    locale_root: Path | None = None,
    *,
    apply_locales: bool = True,
) -> DeLabelRepairResult:
    """Strip MCL markup from DE labels and re-apply Mineclonia .de.tr where possible."""
    result = DeLabelRepairResult()
    en_to_de: dict[str, str] = {}
    if apply_locales:
        root = locale_root
        if root is None:
            raw = getattr(settings, "MCC_LUANTI_LOCALE_ROOT", "") or ""
            root = Path(raw) if raw else None
        if root is None or not root.is_dir():
            result.errors.append("locale_root_missing")
        else:
            en_to_de = build_english_to_german_map(root)
            if not en_to_de:
                result.errors.append("no_de_tr_files")

    reg_desc = {
        row.item_name: (row.description or "").strip()
        for row in LuantiRegisteredItem.objects.all().only("item_name", "description")
    }

    for item in LuantiShopItem.objects.prefetch_related("labels").all():
        row = item.labels.filter(language_code="de").first()
        stored = (row.display_name if row else "") or ""
        source = stored or (item.display_name or "") or reg_desc.get(item.item_name, "")
        plain = cleaned_display_name(source) or plain_shop_label(reg_desc.get(item.item_name, ""))
        if not plain:
            result.no_plain_title += 1
            continue
        target = plain[:128]
        if en_to_de:
            de_hit = _lookup_in_en_to_de(en_to_de, plain)
            if de_hit:
                target = de_hit[:128]
        if stored.strip() == target:
            result.unchanged += 1
            continue
        set_item_label(item, "de", target, overwrite=True)
        result.updated += 1
    return result


def shop_de_label_stats() -> ShopDeLabelStats:
    total = LuantiShopItem.objects.count()
    de_nonempty = (
        LuantiShopItemLabel.objects.filter(language_code="de")
        .exclude(display_name="")
        .values("item_id")
        .distinct()
        .count()
    )
    return ShopDeLabelStats(
        shop_items=total,
        de_labels_nonempty=de_nonempty,
        de_labels_missing=max(0, total - de_nonempty),
    )


def _item_ids_with_nonempty_de_label() -> set[int]:
    return set(
        LuantiShopItemLabel.objects.filter(language_code="de")
        .exclude(display_name="")
        .values_list("item_id", flat=True)
    )


def shop_items_missing_de_label(*, limit: int = 200) -> list[dict[str, object]]:
    """Shop articles without a non-empty DE label (for Admin quick edit list)."""
    labeled = _item_ids_with_nonempty_de_label()
    reg_map = {
        row.item_name: (row.description or "").strip()
        for row in LuantiRegisteredItem.objects.all().only("item_name", "description")
    }
    if labeled:
        item_qs = (
            LuantiShopItem.objects.exclude(pk__in=labeled)
            .select_related("category")
            .prefetch_related("labels", "category__labels")
            .order_by("category__sort_order", "category__slug", "sort_order", "item_name")[
                :limit
            ]
        )
    else:
        item_qs = LuantiShopItem.objects.select_related("category").prefetch_related(
            "labels", "category__labels"
        ).order_by("category__sort_order", "category__slug", "sort_order", "item_name")[:limit]

    cat_label_maps = category_labels_map_for_categories(
        list({item.category_id for item in item_qs})
    )
    rows: list[dict[str, object]] = []
    for item in item_qs:
        cat = item.category
        cat_labels = cat_label_maps.get(cat.pk, {})
        reg = reg_map.get(item.item_name, "")
        plain_reg = cleaned_display_name(reg) or plain_shop_label(reg, max_len=0)
        de_row = next(
            (row for row in item.labels.all() if normalize_language_code(row.language_code) == "de"),
            None,
        )
        de_stored = (de_row.display_name if de_row else "") or ""
        rows.append(
            {
                "item_id": item.pk,
                "item_name": item.item_name,
                "category_slug": cat.slug,
                "category_name": resolve_category_display_name(cat, "de", labels=cat_labels),
                "legacy_display_name": (item.display_name or "").strip(),
                "de_label_stored": de_stored.strip(),
                "registry_plain": plain_reg,
                "enabled": item.enabled,
            }
        )
    return rows


def shop_item_search_hits(
    q: str,
    *,
    limit: int = 400,
) -> list[dict[str, object]]:
    """Admin shop search using the same blob rules as the in-game /mccshop filter."""
    q_norm = normalize_shop_search_text(q)
    if not q_norm:
        return []

    reg_map = {
        row.item_name: (row.description or "").strip()
        for row in LuantiRegisteredItem.objects.all().only("item_name", "description")
    }
    categories = LuantiShopCategory.objects.prefetch_related("labels", "items__labels").order_by(
        "sort_order", "slug"
    )
    cat_ids = [c.pk for c in categories]
    cat_label_maps = category_labels_map_for_categories(cat_ids)
    hits: list[dict[str, object]] = []

    for cat in categories:
        cat_labels = cat_label_maps.get(cat.pk, {})
        for item in cat.items.all():
            item_labels = {
                normalize_language_code(row.language_code): (row.display_name or "").strip()
                for row in item.labels.all()
                if (row.display_name or "").strip()
            }
            resolved = resolve_item_display_name(item, DEFAULT_LANG, labels=item_labels)
            blob = build_item_search_blob(
                item,
                labels=item_labels,
                resolved_display_name=resolved,
                category=cat,
                category_labels=cat_labels,
                registry_description=reg_map.get(item.item_name, ""),
            )
            if q_norm not in blob:
                continue
            hits.append(
                {
                    "item_name": item.item_name,
                    "label_de": resolve_item_display_name(item, "de", labels=item_labels),
                    "label_en": resolve_item_display_name(item, "en", labels=item_labels),
                    "category_slug": cat.slug,
                    "category_name": resolve_category_display_name(
                        cat, "de", labels=cat_labels
                    ),
                    "buy_price_velos": item.buy_price_velos,
                    "enabled": item.enabled,
                }
            )
            if len(hits) >= limit:
                return hits
    return hits


def build_shop_categories_for_admin(
    categories,
    *,
    shop_q: str = "",
) -> list[dict[str, object]]:
    """Attach label_de/en per item; optionally filter items by shop_q."""
    q_norm = normalize_shop_search_text(shop_q)
    reg_map = {
        row.item_name: (row.description or "").strip()
        for row in LuantiRegisteredItem.objects.all().only("item_name", "description")
    }
    cat_ids = [c.pk for c in categories]
    cat_label_maps = category_labels_map_for_categories(cat_ids)
    out: list[dict[str, object]] = []

    for cat in categories:
        cat_labels = cat_label_maps.get(cat.pk, {})
        item_rows: list[dict[str, object]] = []
        for item in cat.items.all():
            item_labels = {
                normalize_language_code(row.language_code): (row.display_name or "").strip()
                for row in item.labels.all()
                if (row.display_name or "").strip()
            }
            if q_norm:
                resolved = resolve_item_display_name(item, DEFAULT_LANG, labels=item_labels)
                blob = build_item_search_blob(
                    item,
                    labels=item_labels,
                    resolved_display_name=resolved,
                    category=cat,
                    category_labels=cat_labels,
                    registry_description=reg_map.get(item.item_name, ""),
                )
                if q_norm not in blob:
                    continue
            item_rows.append(
                {
                    "item": item,
                    "label_de": resolve_item_display_name(item, "de", labels=item_labels),
                    "label_en": resolve_item_display_name(item, "en", labels=item_labels),
                    "registry_description": reg_map.get(item.item_name, ""),
                }
            )
        if q_norm and not item_rows:
            continue
        out.append(
            {
                "category": cat,
                "items": item_rows,
            }
        )
    return out


def locale_root_configured() -> bool:
    raw = getattr(settings, "MCC_LUANTI_LOCALE_ROOT", "") or ""
    return bool(raw) and Path(raw).is_dir()


def suggested_category_label_de(category: LuantiShopCategory) -> str:
    slug = (category.slug or "").lower()
    if slug in CATEGORY_SLUG_LABELS_DE:
        return CATEGORY_SLUG_LABELS_DE[slug][:64]
    name = (category.name or "").strip()
    if name:
        return name[:64]
    return slug.replace("_", " ").title()[:64] or "Shop"


def suggested_category_label_en(category: LuantiShopCategory) -> str:
    slug = (category.slug or "").lower()
    if slug in CATEGORY_SLUG_LABELS_EN:
        return CATEGORY_SLUG_LABELS_EN[slug][:64]
    name = (category.name or "").strip()
    if name:
        return name[:64]
    return slug.replace("_", " ").title()[:64] or "Shop"


def category_labels_map_for_categories(category_ids: list[int]) -> dict[int, dict[str, str]]:
    if not category_ids:
        return {}
    out: dict[int, dict[str, str]] = {}
    for row in LuantiShopCategoryLabel.objects.filter(category_id__in=category_ids).values(
        "category_id", "language_code", "display_name"
    ):
        cid = row["category_id"]
        lang = normalize_language_code(row["language_code"])
        name = (row["display_name"] or "").strip()
        if name:
            out.setdefault(cid, {})[lang] = name[:64]
    return out


def resolve_category_display_name(
    category: LuantiShopCategory,
    lang: str,
    *,
    labels: dict[str, str] | None = None,
) -> str:
    lang = normalize_language_code(lang)
    if labels is None:
        label_map = {
            normalize_language_code(row.language_code): (row.display_name or "").strip()
            for row in category.labels.all()
            if (row.display_name or "").strip()
        }
    else:
        label_map = labels
    for code in (lang, *FALLBACK_LANGS):
        if code in label_map and label_map[code]:
            return label_map[code][:64]
    legacy = (category.name or "").strip()
    if legacy:
        return legacy[:64]
    return suggested_category_label_de(category)


@transaction.atomic
def set_category_label(
    category: LuantiShopCategory,
    language_code: str,
    display_name: str,
    *,
    overwrite: bool = True,
    sync_legacy_de: bool = True,
) -> bool:
    lang = normalize_language_code(language_code)
    name = (display_name or "").strip()[:64]
    if not name:
        return False
    existing = LuantiShopCategoryLabel.objects.filter(
        category=category, language_code=lang
    ).first()
    if existing and not overwrite:
        return False
    LuantiShopCategoryLabel.objects.update_or_create(
        category=category,
        language_code=lang,
        defaults={"display_name": name},
    )
    if sync_legacy_de and lang == DEFAULT_LANG and category.name != name:
        category.name = name
        category.save(update_fields=["name"])
    return True


def _should_replace_category_label(
    category: LuantiShopCategory, lang: str, overwrite: bool, only_empty: bool
) -> bool:
    if overwrite and not only_empty:
        return True
    if LuantiShopCategoryLabel.objects.filter(category=category, language_code=lang).exists():
        if only_empty:
            row = LuantiShopCategoryLabel.objects.get(category=category, language_code=lang)
            return not (row.display_name or "").strip()
        return False
    return True


@dataclass
class CategoryLabelSyncResult:
    updated: int = 0
    created: int = 0
    skipped: int = 0


@transaction.atomic
def sync_category_labels_defaults(
    *,
    overwrite: bool = False,
    only_empty: bool = True,
) -> CategoryLabelSyncResult:
    """Apply German/English default tab titles from slug map (+ legacy name for EN)."""
    result = CategoryLabelSyncResult()
    for cat in LuantiShopCategory.objects.all().iterator():
        for lang, suggested in (
            ("de", suggested_category_label_de(cat)),
            ("en", suggested_category_label_en(cat)),
        ):
            if not _should_replace_category_label(cat, lang, overwrite, only_empty):
                result.skipped += 1
                continue
            existed = LuantiShopCategoryLabel.objects.filter(
                category=cat, language_code=lang
            ).exists()
            set_category_label(
                cat,
                lang,
                suggested,
                overwrite=True,
                sync_legacy_de=(lang == DEFAULT_LANG),
            )
            if existed:
                result.updated += 1
            else:
                result.created += 1
    return result
