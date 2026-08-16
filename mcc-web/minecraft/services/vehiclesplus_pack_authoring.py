# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    vehiclesplus_pack_authoring.py
# @note    Merge vehicle item models into a selectable MCC resource pack ZIP.

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from django.conf import settings

from config.logger_utils import get_logger

logger = get_logger("minecraft")

_SAFE_PACK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.zip$")
_SAFE_MODEL_STEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SAFE_STAGING_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")
_JUNK_ZIP_PREFIXES = ("home/", "__MACOSX/", ".")
_STAGING_MAX_AGE_SEC = 24 * 3600
_MAX_VENDOR_ZIP_BYTES = 80 * 1024 * 1024

DEFAULT_PACK_FORMAT = 64
DEFAULT_LEATHER_ITEM = "leather_boots"
LEATHER_ITEMS = (
    "leather_boots",
    "leather_chestplate",
    "leather_helmet",
)


@dataclass(frozen=True)
class PackMergeResult:
    output_path: Path
    sha1: str
    custom_model_data: int
    model_resource: str
    http_url: str
    vendor_hjson: str = ""
    vendor_hjson_subdir: str = ""


@dataclass(frozen=True)
class VendorModelCandidate:
    """One importable model JSON found inside a vendor/resource-pack ZIP."""

    path: str
    stem: str
    namespace: str
    texture_refs: tuple[str, ...] = ()
    texture_files_found: int = 0
    has_elements: bool = False
    parent: str = ""
    # From vendor item overrides / HJSON hints (informational; CMD is reassigned on merge).
    vendor_cmd: int | None = None
    leather_item: str = ""


@dataclass(frozen=True)
class VendorZipInspection:
    staging_token: str
    original_name: str
    models: tuple[VendorModelCandidate, ...]
    texture_count: int
    member_count: int


@dataclass(frozen=True)
class ServerPackApplyResult:
    """Result of writing resource-pack settings to Paper / VehiclesPlus."""

    properties_path: Path
    properties_backup: Path
    resource_pack_url: str
    sha1: str
    resource_pack_id: str
    vehiclesplus_config: Path | None = None
    vehiclesplus_backup: Path | None = None


class PackAuthoringError(ValueError):
    """User-facing validation / I/O error while authoring a pack."""


def resource_packs_dir() -> Path:
    raw = getattr(settings, "MCC_MINECRAFT_RESOURCE_PACKS_DIR", "") or ""
    if raw:
        return Path(raw)
    data_dir = Path(getattr(settings, "DATA_DIR", "/data/var/mcc"))
    return data_dir / "media" / "mc-packs"


def resource_pack_http_base() -> str:
    return (
        getattr(settings, "MCC_MINECRAFT_RESOURCE_PACK_HTTP_BASE", "") or ""
    ).rstrip("/")


def default_source_pack_name() -> str:
    return (
        getattr(
            settings,
            "MCC_MINECRAFT_RESOURCE_PACK_DEFAULT_SOURCE",
            "VPExample-v3-1.21.7-1.21.8_MCC.zip",
        )
        or "VPExample-v3-1.21.7-1.21.8_MCC.zip"
    )


def list_pack_zip_names() -> list[str]:
    root = resource_packs_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.glob("*.zip") if p.is_file())


def validate_pack_filename(name: str, *, field: str = "Pack") -> str:
    text = (name or "").strip()
    if not text.endswith(".zip"):
        text = f"{text}.zip"
    if not _SAFE_PACK_NAME_RE.match(text):
        raise PackAuthoringError(
            f"{field}-Dateiname ungültig (nur A–Z, a–z, 0–9, ._- und Endung .zip)."
        )
    if ".." in text or "/" in text or "\\" in text:
        raise PackAuthoringError(f"{field}-Dateiname darf keine Pfadanteile enthalten.")
    return text


def validate_model_stem(stem: str) -> str:
    text = (stem or "").strip()
    if not _SAFE_MODEL_STEM_RE.match(text):
        raise PackAuthoringError(
            "Modell-ID ungültig (nur A–Z, a–z, 0–9, _-; max. 64 Zeichen)."
        )
    return text


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_junk_zip_member(name: str) -> bool:
    normalized = name.replace("\\", "/").lstrip("/")
    if not normalized or normalized.endswith("/"):
        return False
    return any(normalized.startswith(prefix) for prefix in _JUNK_ZIP_PREFIXES)


def _extract_source_zip(source_zip: Path, dest: Path) -> None:
    with zipfile.ZipFile(source_zip, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.endswith("/") or _is_junk_zip_member(name):
                continue
            # Strip accidental absolute / nested junk roots; keep assets/ and pack.*
            if name.startswith("/") or name.startswith("../"):
                continue
            target = dest / name
            if not str(target.resolve()).startswith(str(dest.resolve())):
                raise PackAuthoringError("Ungültiger Zip-Eintrag (Path traversal).")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def _write_pack_mcmeta(root: Path, *, pack_format: int = DEFAULT_PACK_FORMAT) -> None:
    meta = {
        "pack": {
            "pack_format": pack_format,
            "description": "VehiclesPlus Resourcepack (MCC)",
            "supported_formats": pack_format,
        },
        "meta": {
            "game_version": "1.21.8",
        },
    }
    (root / "pack.mcmeta").write_text(
        json.dumps(meta, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _collect_cmd_thresholds(item_json: dict) -> list[int]:
    found: list[int] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if "threshold" in node:
                try:
                    found.append(int(node["threshold"]))
                except (TypeError, ValueError):
                    pass
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(item_json)
    return found


def next_custom_model_data(pack_root: Path, *, item: str = DEFAULT_LEATHER_ITEM) -> int:
    path = pack_root / "assets" / "minecraft" / "items" / f"{item}.json"
    if not path.is_file():
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    thresholds = _collect_cmd_thresholds(data)
    return (max(thresholds) + 1) if thresholds else 1


def _entry_model_resource(entry: dict) -> str:
    model_node = entry.get("model")
    if isinstance(model_node, dict):
        return str(model_node.get("model") or "").strip()
    if isinstance(model_node, str):
        return model_node.strip()
    return ""


def find_cmd_for_model_resource(
    pack_root: Path,
    *,
    model_resource: str,
    item: str = DEFAULT_LEATHER_ITEM,
) -> int | None:
    """Return custom_model_data threshold bound to ``model_resource``, if any."""
    path = pack_root / "assets" / "minecraft" / "items" / f"{item}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = _find_range_entries(data)
    if not entries:
        return None
    want = model_resource.strip()
    for entry in entries:
        if _entry_model_resource(entry) == want:
            try:
                return int(entry.get("threshold"))
            except (TypeError, ValueError):
                continue
    return None


def list_vehicle_model_stems_in_pack(pack_name: str) -> list[str]:
    """List ``assets/vp/models/item/vehicles/*.json`` stems inside a pack ZIP."""
    try:
        name = validate_pack_filename(pack_name, field="Pack")
    except PackAuthoringError:
        return []
    path = resource_packs_dir() / name
    if not path.is_file():
        return []
    stems: list[str] = []
    prefix = "assets/vp/models/item/vehicles/"
    try:
        with zipfile.ZipFile(path, "r") as zf:
            for info in zf.namelist():
                norm = info.replace("\\", "/").lstrip("/")
                # Nested vendor zips may prefix folders; take suffix after assets/vp/...
                idx = norm.find(prefix)
                if idx < 0:
                    continue
                rest = norm[idx + len(prefix) :]
                if "/" in rest or not rest.endswith(".json"):
                    continue
                stem = Path(rest).stem
                if _SAFE_MODEL_STEM_RE.match(stem):
                    stems.append(stem)
    except zipfile.BadZipFile:
        return []
    return sorted(set(stems))


def _resolve_cmd_for_write(
    pack_root: Path,
    *,
    stem: str,
    leather_item: str,
    custom_model_data: int | None,
    replace_existing: bool,
) -> int:
    model_resource = f"vp:item/vehicles/{stem}"
    if replace_existing:
        if custom_model_data is not None:
            cmd = int(custom_model_data)
        else:
            found = find_cmd_for_model_resource(
                pack_root, model_resource=model_resource, item=leather_item
            )
            if found is not None:
                cmd = found
            else:
                # Model file may exist without a leather binding (broken import).
                cmd = next_custom_model_data(pack_root, item=leather_item)
    else:
        cmd = (
            int(custom_model_data)
            if custom_model_data is not None
            else next_custom_model_data(pack_root, item=leather_item)
        )
    if cmd < 1:
        raise PackAuthoringError("custom_model_data muss ≥ 1 sein.")
    return cmd


def _find_range_entries(node) -> list | None:
    """Locate the custom_model_data range_dispatch entries list (mutates in place)."""
    if isinstance(node, dict):
        if (
            node.get("type") in {"range_dispatch", "minecraft:range_dispatch"}
            and str(node.get("property", "")).endswith("custom_model_data")
            and isinstance(node.get("entries"), list)
        ):
            return node["entries"]
        for value in node.values():
            found = _find_range_entries(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_range_entries(item)
            if found is not None:
                return found
    return None


def _append_cmd_entry(
    pack_root: Path,
    *,
    item: str,
    custom_model_data: int,
    model_resource: str,
    replace_existing: bool = False,
) -> None:
    path = pack_root / "assets" / "minecraft" / "items" / f"{item}.json"
    if not path.is_file():
        raise PackAuthoringError(f"Item-Definition fehlt im Pack: {item}.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = _find_range_entries(data)
    if entries is None:
        raise PackAuthoringError(
            f"Keine custom_model_data range_dispatch-Einträge in {item}.json gefunden."
        )
    if replace_existing:
        # Drop previous binding for this CMD and/or this model resource, then re-add.
        entries[:] = [
            entry
            for entry in entries
            if not (
                int(entry.get("threshold", -1)) == custom_model_data
                or _entry_model_resource(entry) == model_resource
            )
        ]
    else:
        for entry in entries:
            if int(entry.get("threshold", -1)) == custom_model_data:
                raise PackAuthoringError(
                    f"custom_model_data {custom_model_data} ist in {item}.json schon vergeben. "
                    "Für Tausch „Modell ersetzen“ aktivieren."
                )
    entries.append(
        {
            "threshold": custom_model_data,
            "model": {
                "type": "model",
                "model": model_resource,
                "tints": [{"type": "minecraft:dye", "default": -6265536}],
            },
        }
    )
    entries.sort(key=lambda e: int(e.get("threshold", 0)))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _zip_directory(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(source_dir.rglob("*")):
            if not file_path.is_file():
                continue
            arcname = file_path.relative_to(source_dir).as_posix()
            if _is_junk_zip_member(arcname):
                continue
            zf.write(file_path, arcname)


def merge_model_into_pack(
    *,
    source_pack_name: str,
    output_pack_name: str,
    model_stem: str,
    model_json_bytes: bytes,
    custom_model_data: int | None = None,
    leather_item: str = DEFAULT_LEATHER_ITEM,
    texture_files: list[tuple[str, bytes]] | None = None,
    overwrite_output: bool = True,
    replace_existing: bool = False,
) -> PackMergeResult:
    """
    Copy ``source_pack_name`` from the packs dir, add a vehicle item model, write
    ``output_pack_name`` (chooser) next to it. Source and output may be the same name.

    With ``replace_existing=True``, overwrite model/textures and keep/reuse the CMD
    for ``vp:item/vehicles/<stem>`` (or the CMD given explicitly).
    """
    root = resource_packs_dir()
    root.mkdir(parents=True, exist_ok=True)

    source_name = validate_pack_filename(source_pack_name, field="Quell-Pack")
    output_name = validate_pack_filename(output_pack_name, field="Ziel-Pack")
    stem = validate_model_stem(model_stem)

    if leather_item not in LEATHER_ITEMS:
        raise PackAuthoringError(f"Ungültiges Leder-Item: {leather_item}")

    source_zip = root / source_name
    if not source_zip.is_file():
        raise PackAuthoringError(f"Quell-Pack nicht gefunden: {source_name}")

    output_zip = root / output_name
    if output_zip.exists() and not overwrite_output and output_name != source_name:
        raise PackAuthoringError(f"Ziel-Pack existiert bereits: {output_name}")

    try:
        model_data = json.loads(model_json_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackAuthoringError(f"Modell-JSON ungültig: {exc}") from exc
    if not isinstance(model_data, dict):
        raise PackAuthoringError("Modell-JSON muss ein Objekt sein.")

    with tempfile.TemporaryDirectory(prefix="mcc-vp-pack-") as tmp:
        work = Path(tmp) / "pack"
        work.mkdir()
        _extract_source_zip(source_zip, work)
        _write_pack_mcmeta(work)

        cmd = _resolve_cmd_for_write(
            work,
            stem=stem,
            leather_item=leather_item,
            custom_model_data=custom_model_data,
            replace_existing=replace_existing,
        )

        model_rel = Path("assets/vp/models/item/vehicles") / f"{stem}.json"
        model_path = work / model_rel
        if model_path.is_file() and not replace_existing:
            # Same stem already in pack → treat as replace (keep CMD) instead of failing.
            replace_existing = True
            cmd = _resolve_cmd_for_write(
                work,
                stem=stem,
                leather_item=leather_item,
                custom_model_data=custom_model_data,
                replace_existing=True,
            )
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text(
            json.dumps(model_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        tex_flat = work / "assets" / "vp" / "textures" / "item" / "vehicles"
        tex_stem = tex_flat / stem
        if replace_existing and tex_stem.is_dir():
            shutil.rmtree(tex_stem, ignore_errors=True)

        for texture_name, payload in texture_files or []:
            safe = Path(texture_name).name
            if not safe.lower().endswith((".png", ".mcmeta")):
                raise PackAuthoringError(f"Textur nicht erlaubt: {safe}")
            # Prefer stem subfolder (matches ZIP-import layout)
            tex_path = tex_stem / safe
            tex_path.parent.mkdir(parents=True, exist_ok=True)
            tex_path.write_bytes(payload)

        model_resource = f"vp:item/vehicles/{stem}"
        _append_cmd_entry(
            work,
            item=leather_item,
            custom_model_data=cmd,
            model_resource=model_resource,
            replace_existing=replace_existing,
        )

        _zip_directory(work, output_zip)

    digest = sha1_file(output_zip)
    base = resource_pack_http_base()
    http_url = f"{base}/{output_name}" if base else output_name
    logger.info(
        "[vp_pack] merged model=%s cmd=%s replace=%s source=%s output=%s sha1=%s",
        stem,
        cmd,
        replace_existing,
        source_name,
        output_name,
        digest,
    )
    return PackMergeResult(
        output_path=output_zip,
        sha1=digest,
        custom_model_data=cmd,
        model_resource=model_resource,
        http_url=http_url,
    )


def import_staging_dir() -> Path:
    data_dir = Path(getattr(settings, "DATA_DIR", "/data/var/mcc"))
    return data_dir / "tmp" / "vp-pack-import"


def _cleanup_stale_staging() -> None:
    root = import_staging_dir()
    if not root.is_dir():
        return
    now = time.time()
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            age = now - child.stat().st_mtime
        except OSError:
            continue
        if age > _STAGING_MAX_AGE_SEC:
            shutil.rmtree(child, ignore_errors=True)


def _validate_staging_token(token: str) -> str:
    text = (token or "").strip().lower()
    if not _SAFE_STAGING_TOKEN_RE.match(text):
        raise PackAuthoringError("Ungültiges Import-Token.")
    return text


def stage_vendor_zip(*, payload: bytes, original_name: str) -> str:
    """Persist an uploaded vendor ZIP and return a one-time staging token."""
    if not payload:
        raise PackAuthoringError("Leeres ZIP-Archiv.")
    if len(payload) > _MAX_VENDOR_ZIP_BYTES:
        raise PackAuthoringError(
            f"ZIP zu groß (max. {_MAX_VENDOR_ZIP_BYTES // (1024 * 1024)} MB)."
        )
    with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
        tmp.write(payload)
        tmp.flush()
        try:
            with zipfile.ZipFile(tmp.name, "r") as zf:
                bad = zf.testzip()
                if bad is not None:
                    raise PackAuthoringError(f"Beschädigter ZIP-Eintrag: {bad}")
        except zipfile.BadZipFile as exc:
            raise PackAuthoringError(f"Keine gültige ZIP-Datei: {exc}") from exc

    _cleanup_stale_staging()
    token = uuid4().hex
    dest = import_staging_dir() / token
    dest.mkdir(parents=True, exist_ok=False)
    (dest / "upload.zip").write_bytes(payload)
    safe_name = Path(original_name or "model.zip").name[:180]
    (dest / "meta.json").write_text(
        json.dumps({"original_name": safe_name}, ensure_ascii=False),
        encoding="utf-8",
    )
    return token


def _staged_zip_path(token: str) -> Path:
    token = _validate_staging_token(token)
    path = import_staging_dir() / token / "upload.zip"
    if not path.is_file():
        raise PackAuthoringError(
            "Import-Staging abgelaufen oder nicht gefunden — ZIP bitte erneut hochladen."
        )
    return path


def discard_staged_vendor_zip(token: str) -> None:
    try:
        token = _validate_staging_token(token)
    except PackAuthoringError:
        return
    shutil.rmtree(import_staging_dir() / token, ignore_errors=True)


def _normalize_zip_member(name: str) -> str | None:
    normalized = name.replace("\\", "/").lstrip("/")
    if not normalized or normalized.endswith("/"):
        return None
    if _is_junk_zip_member(normalized):
        return None
    if normalized.startswith("../") or "/../" in normalized:
        return None
    return normalized


def _assets_relative_path(normalized: str) -> str | None:
    """
    Strip any vendor nesting prefix so paths start at ``assets/``.

    PixelMine example:
    ``PixelMine_…/Drag & Drop Files/Resource Pack/assets/minecraft/models/…``
    → ``assets/minecraft/models/…``
    """
    marker = "/assets/"
    if normalized.startswith("assets/"):
        return normalized
    idx = normalized.find(marker)
    if idx >= 0:
        return normalized[idx + 1 :]  # drop leading slash → assets/...
    return None


def _pack_preference_score(full_path: str) -> int:
    """Higher = preferred when the same model appears in multiple plugin folders."""
    lower = full_path.lower()
    score = 0
    # PixelMine ships the canonical pack under "Resource Pack/" (with space).
    if "/resource pack/" in lower:
        score += 200
    elif "/resourcepack/" in lower and "/itemsadder/" not in lower:
        score += 80
    if "vehiclesplus" in lower:
        score += 40
    if "/itemsadder/" in lower:
        score += 10
    if "/nexo/" in lower:
        score += 8
    if "/oraxen/" in lower:
        score += 5
    if "/mtvehicles/" in lower:
        score -= 20
    # Prefer shorter paths after assets/ (less nesting noise)
    assets_rel = _assets_relative_path(full_path) or full_path
    score -= assets_rel.count("/")
    return score


def _zip_member_map(zf: zipfile.ZipFile) -> dict[str, str]:
    """
    Map lookup keys → actual zip member names.

    Indexes both the full nested path and a canonical ``assets/...`` key so
    texture refs resolve even inside PixelMine ``Drag & Drop Files/Resource Pack/``.
    When the same assets-relative path appears multiple times, keep the preferred pack.
    """
    mapping: dict[str, str] = {}
    assets_best: dict[str, tuple[int, str]] = {}

    for info in zf.infolist():
        if info.is_dir():
            continue
        normalized = _normalize_zip_member(info.filename)
        if not normalized:
            continue
        mapping[normalized] = info.filename
        assets_rel = _assets_relative_path(normalized)
        if assets_rel:
            score = _pack_preference_score(normalized)
            prev = assets_best.get(assets_rel)
            if prev is None or score > prev[0]:
                assets_best[assets_rel] = (score, info.filename)

    for assets_rel, (_score, member_name) in assets_best.items():
        mapping[assets_rel] = member_name
    return mapping


def _find_member_for_suffix(members: dict[str, str], *candidates: str) -> str | None:
    """Resolve a texture/model candidate against nested or canonical keys."""
    for candidate in candidates:
        if candidate in members:
            return members[candidate]
        # Suffix match for deeply nested duplicates not indexed as assets/
        suffix = candidate if candidate.startswith("/") else f"/{candidate}"
        matches = [m for key, m in members.items() if key.endswith(suffix) or key == candidate]
        if matches:
            # Prefer Resource Pack via score on keys
            best_key = max(
                (k for k in members if k.endswith(suffix) or k == candidate),
                key=_pack_preference_score,
            )
            return members[best_key]
    return None


def _texture_ref_to_candidates(ref: str) -> list[str]:
    """Minecraft texture refs → possible assets/.../textures/... paths."""
    text = (ref or "").strip()
    if not text or text.startswith("#"):
        return []
    if ":" in text:
        ns, path = text.split(":", 1)
    else:
        ns, path = "minecraft", text
    path = path.lstrip("/")
    if path.endswith(".png"):
        path = path[: -len(".png")]
    base = f"assets/{ns}/textures/{path}"
    return [f"{base}.png", f"{base}.png.mcmeta"]


def _collect_texture_refs(model_data: dict) -> list[str]:
    textures = model_data.get("textures")
    if not isinstance(textures, dict):
        return []
    refs: list[str] = []
    for value in textures.values():
        if isinstance(value, str) and value.strip() and not value.startswith("#"):
            refs.append(value.strip())
    return refs


def _looks_like_geometry_model(model_data: dict, *, rel_path: str) -> bool:
    lower = rel_path.replace("\\", "/").lower()
    # Skip only shallow vanilla item override shells:
    # assets/.../models/item/leather_boots.json (no subfolder).
    # Keep assets/.../models/item/bikes/foo.json and models/pixelmine/vehicles/*.json.
    if re.search(r"/models/items?/[^/]+\.json$", lower):
        return False
    if "elements" in model_data:
        return True
    textures = model_data.get("textures")
    if isinstance(textures, dict) and textures:
        return True
    parent = str(model_data.get("parent") or "")
    if parent.startswith("minecraft:item/") or parent.startswith("item/"):
        return False
    return bool(parent)


def _dedupe_model_candidates(
    models: list[VendorModelCandidate],
) -> list[VendorModelCandidate]:
    """Keep one entry per model stem, preferring Resource Pack / assets paths."""
    best: dict[str, VendorModelCandidate] = {}
    for model in models:
        key = model.stem.lower()
        prev = best.get(key)
        if prev is None:
            best[key] = model
            continue
        if _pack_preference_score(model.path) > _pack_preference_score(prev.path):
            best[key] = model
    return sorted(best.values(), key=lambda m: m.path.lower())


def _model_resource_aliases(logic_path: str, stem: str) -> set[str]:
    """Resource locations that may appear in leather_boots overrides for this model."""
    aliases = {stem, f"item/{stem}", f"minecraft:item/{stem}"}
    assets_rel = _assets_relative_path(logic_path) or logic_path
    if "/models/" in assets_rel:
        left, right = assets_rel.split("/models/", 1)
        model_path = right.rsplit(".", 1)[0]
        aliases.add(model_path)
        ns = left.split("/")[-1] if left.startswith("assets/") else ""
        if ns:
            aliases.add(f"{ns}:{model_path}")
        # Without namespace prefix used by older packs
        if "/" in model_path:
            aliases.add(model_path)
    return {a.replace("\\", "/").lower() for a in aliases if a}


def _extract_override_bindings(data: dict) -> list[tuple[str, int]]:
    """Return (model_resource, custom_model_data) pairs from legacy overrides."""
    found: list[tuple[str, int]] = []
    overrides = data.get("overrides")
    if not isinstance(overrides, list):
        return found
    for entry in overrides:
        if not isinstance(entry, dict):
            continue
        model = str(entry.get("model") or "").strip()
        pred = entry.get("predicate") or {}
        if not isinstance(pred, dict):
            continue
        cmd = pred.get("custom_model_data")
        if model and cmd is not None:
            try:
                found.append((model, int(cmd)))
            except (TypeError, ValueError):
                continue
    return found


def _extract_range_dispatch_bindings(data: dict) -> list[tuple[str, int]]:
    """Return (model_resource, threshold) from 1.21.4+ items/*.json range_dispatch."""
    found: list[tuple[str, int]] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if (
                node.get("type") in {"range_dispatch", "minecraft:range_dispatch"}
                and str(node.get("property", "")).endswith("custom_model_data")
                and isinstance(node.get("entries"), list)
            ):
                for entry in node["entries"]:
                    if not isinstance(entry, dict):
                        continue
                    try:
                        threshold = int(entry.get("threshold"))
                    except (TypeError, ValueError):
                        continue
                    model_node = entry.get("model")
                    resource = ""
                    if isinstance(model_node, dict):
                        resource = str(model_node.get("model") or "").strip()
                    elif isinstance(model_node, str):
                        resource = model_node.strip()
                    if resource:
                        found.append((resource, threshold))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


def _scan_vendor_item_bindings(
    zf: zipfile.ZipFile, members: dict[str, str]
) -> dict[str, tuple[str, int]]:
    """
    Map model-resource alias → (leather_item_stem, vendor_cmd).

    Prefer Resource Pack copies when the same binding appears multiple times.
    """
    bindings: dict[str, tuple[int, str, int]] = {}  # alias -> (score, item, cmd)
    item_name_re = re.compile(r"/models/items?/([a-z0-9_]+)\.json$", re.I)
    items_dir_re = re.compile(r"/items/([a-z0-9_]+)\.json$", re.I)

    for rel_path, raw_name in members.items():
        lower = rel_path.replace("\\", "/").lower()
        item = ""
        m_item = item_name_re.search(lower)
        if m_item and re.search(r"/models/items?/[^/]+\.json$", lower):
            item = m_item.group(1)
        else:
            m_new = items_dir_re.search(lower)
            if m_new and "/assets/" in f"/{lower}" and "/models/" not in lower:
                item = m_new.group(1)
        if not item:
            continue
        if item not in LEATHER_ITEMS and not item.startswith("leather_"):
            continue
        try:
            data = json.loads(zf.read(raw_name).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError):
            continue
        if not isinstance(data, dict):
            continue
        pairs = _extract_override_bindings(data) + _extract_range_dispatch_bindings(data)
        score = _pack_preference_score(rel_path)
        for model_res, cmd in pairs:
            alias = model_res.replace("\\", "/").lower()
            # also bare path without minecraft:
            if ":" in alias:
                alias_alt = alias.split(":", 1)[1]
            else:
                alias_alt = alias
            for key in {alias, alias_alt}:
                prev = bindings.get(key)
                if prev is None or score > prev[0]:
                    bindings[key] = (score, item, cmd)
    return {k: (v[1], v[2]) for k, v in bindings.items()}


def inspect_staged_vendor_zip(token: str) -> VendorZipInspection:
    zip_path = _staged_zip_path(token)
    meta_path = zip_path.parent / "meta.json"
    original_name = "model.zip"
    if meta_path.is_file():
        try:
            original_name = json.loads(meta_path.read_text(encoding="utf-8")).get(
                "original_name", original_name
            )
        except (OSError, json.JSONDecodeError):
            pass

    models: list[VendorModelCandidate] = []
    texture_count = 0
    member_count = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = _zip_member_map(zf)
        member_count = len({v for v in members.values()})
        texture_count = sum(
            1
            for p, raw in members.items()
            if p.startswith("assets/")
            and p.lower().endswith(".png")
            and "/textures/" in p
        )
        item_bindings = _scan_vendor_item_bindings(zf, members)
        for info in zf.infolist():
            if info.is_dir():
                continue
            full_path = _normalize_zip_member(info.filename)
            if not full_path or not full_path.endswith(".json"):
                continue
            if "/models/" not in full_path:
                continue
            if "/items/" in full_path or "/blockstates/" in full_path:
                continue
            assets_rel = _assets_relative_path(full_path)
            logic_path = assets_rel or full_path
            if not (
                logic_path.startswith("assets/")
                or "/pack/models/" in full_path.replace("\\", "/").lower()
            ):
                continue
            try:
                data = json.loads(zf.read(info).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError):
                continue
            if not isinstance(data, dict) or not _looks_like_geometry_model(
                data, rel_path=logic_path
            ):
                continue
            parts = Path(logic_path).parts
            namespace = (
                parts[1] if len(parts) > 2 and parts[0] == "assets" else "unknown"
            )
            raw_stem = Path(logic_path).stem
            if _SAFE_MODEL_STEM_RE.match(raw_stem):
                stem = raw_stem
            else:
                stem = re.sub(r"[^A-Za-z0-9_-]", "_", raw_stem)[:64] or "model"
            refs = _collect_texture_refs(data)
            found_set: set[str] = set()
            for ref in refs:
                for candidate in _texture_ref_to_candidates(ref):
                    if not candidate.endswith(".png"):
                        continue
                    if _find_member_for_suffix(members, candidate):
                        found_set.add(candidate)
                        break
            vendor_cmd: int | None = None
            leather_item = ""
            for alias in _model_resource_aliases(logic_path, stem):
                hit = item_bindings.get(alias)
                if hit:
                    leather_item, vendor_cmd = hit
                    break
            models.append(
                VendorModelCandidate(
                    path=full_path,
                    stem=stem,
                    namespace=namespace,
                    texture_refs=tuple(refs),
                    texture_files_found=len(found_set),
                    has_elements=isinstance(data.get("elements"), list),
                    parent=str(data.get("parent") or ""),
                    vendor_cmd=vendor_cmd,
                    leather_item=leather_item,
                )
            )

    models = _dedupe_model_candidates(models)
    if not models:
        raise PackAuthoringError(
            "Im ZIP wurden keine importierbaren Item-Modelle "
            "(z. B. …/Resource Pack/assets/*/models/**/*.json) gefunden."
        )
    return VendorZipInspection(
        staging_token=token,
        original_name=str(original_name),
        models=tuple(models),
        texture_count=texture_count,
        member_count=member_count,
    )


def _rewrite_model_textures(
    model_data: dict,
    *,
    stem: str,
    texture_name_map: dict[str, str],
) -> dict:
    """Rewrite textures dict values to vp:item/vehicles/<stem>/<file>."""
    textures = model_data.get("textures")
    if not isinstance(textures, dict):
        return model_data
    new_textures: dict = {}
    for key, value in textures.items():
        if not isinstance(value, str) or value.startswith("#"):
            new_textures[key] = value
            continue
        mapped = texture_name_map.get(value.strip())
        if mapped:
            new_textures[key] = f"vp:item/vehicles/{stem}/{mapped}"
        else:
            new_textures[key] = value
    model_data = dict(model_data)
    model_data["textures"] = new_textures
    return model_data


def _safe_texture_basename(ref: str, used: set[str]) -> str:
    base = Path(ref.split(":", 1)[-1]).name
    if not base.lower().endswith(".png"):
        base = f"{base}.png" if base else "texture.png"
    stem = Path(base).stem
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem)[:48] or "texture"
    candidate = f"{stem}.png"
    n = 2
    while candidate.lower() in used:
        candidate = f"{stem}_{n}.png"
        n += 1
    used.add(candidate.lower())
    return candidate


def import_model_from_vendor_zip(
    *,
    staging_token: str,
    model_path: str,
    source_pack_name: str,
    output_pack_name: str,
    model_stem: str,
    custom_model_data: int | None = None,
    leather_item: str = DEFAULT_LEATHER_ITEM,
    overwrite_output: bool = True,
    replace_existing: bool = False,
) -> PackMergeResult:
    """
    Import one model (+ its textures) from a staged vendor ZIP into an MCC pack.

    By default assigns the next free custom_model_data. With ``replace_existing``,
    overwrites ``vp:item/vehicles/<stem>`` and reuses its CMD (or the CMD given).
    """
    inspection = inspect_staged_vendor_zip(staging_token)
    allowed = {m.path: m for m in inspection.models}
    chosen_path = (model_path or "").replace("\\", "/").lstrip("/")
    if chosen_path not in allowed:
        raise PackAuthoringError("Gewähltes Modell ist nicht Teil der ZIP-Vorschau.")

    root = resource_packs_dir()
    root.mkdir(parents=True, exist_ok=True)
    source_name = validate_pack_filename(source_pack_name, field="Quell-Pack")
    output_name = validate_pack_filename(output_pack_name, field="Ziel-Pack")
    stem = validate_model_stem(model_stem)
    if leather_item not in LEATHER_ITEMS:
        raise PackAuthoringError(f"Ungültiges Leder-Item: {leather_item}")

    source_zip = root / source_name
    if not source_zip.is_file():
        raise PackAuthoringError(f"Quell-Pack nicht gefunden: {source_name}")
    output_zip = root / output_name
    if output_zip.exists() and not overwrite_output and output_name != source_name:
        raise PackAuthoringError(f"Ziel-Pack existiert bereits: {output_name}")

    vendor_zip = _staged_zip_path(staging_token)
    with zipfile.ZipFile(vendor_zip, "r") as vzf:
        members = _zip_member_map(vzf)
        if chosen_path not in members:
            raise PackAuthoringError(f"Modell-Pfad fehlt im ZIP: {chosen_path}")
        try:
            model_data = json.loads(vzf.read(members[chosen_path]).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PackAuthoringError(f"Modell-JSON ungültig: {exc}") from exc
        if not isinstance(model_data, dict):
            raise PackAuthoringError("Modell-JSON muss ein Objekt sein.")

        texture_bytes: dict[str, bytes] = {}
        texture_name_map: dict[str, str] = {}
        used_names: set[str] = set()
        for ref in _collect_texture_refs(model_data):
            png_member = None
            mcmeta_member = None
            for candidate in _texture_ref_to_candidates(ref):
                found = _find_member_for_suffix(members, candidate)
                if found is None:
                    continue
                if candidate.endswith(".mcmeta"):
                    mcmeta_member = found
                else:
                    png_member = found
            if png_member is None:
                continue
            out_name = _safe_texture_basename(ref, used_names)
            texture_bytes[out_name] = vzf.read(png_member)
            texture_name_map[ref] = Path(out_name).stem
            if mcmeta_member is not None:
                texture_bytes[f"{out_name}.mcmeta"] = vzf.read(mcmeta_member)

        # Fallback: PNGs next to the model under a textures sibling path
        if not texture_bytes:
            model_dir = str(Path(chosen_path).parent).replace("\\", "/")
            guess = model_dir.replace("/models/", "/textures/")
            for rel, actual in members.items():
                if "/textures/" not in rel or not rel.lower().endswith(".png"):
                    continue
                if not (
                    rel.startswith(guess)
                    or rel.endswith(guess.split("assets/", 1)[-1] if "assets/" in guess else guess)
                    or Path(rel).stem == Path(chosen_path).stem
                ):
                    continue
                # Prefer assets-canonical keys
                if not rel.startswith("assets/") and _assets_relative_path(rel):
                    continue
                out_name = _safe_texture_basename(rel, used_names)
                texture_bytes[out_name] = vzf.read(actual)
                stem_key = Path(rel).stem
                for ref in _collect_texture_refs(model_data):
                    if ref.endswith(stem_key) or ref.endswith(f"{stem_key}.png"):
                        texture_name_map[ref] = Path(out_name).stem
            # If still empty: any png with same stem under textures/
            if not texture_bytes:
                want = Path(chosen_path).stem.lower()
                for rel, actual in members.items():
                    if not rel.startswith("assets/") or "/textures/" not in rel:
                        continue
                    if Path(rel).stem.lower() != want or not rel.lower().endswith(".png"):
                        continue
                    out_name = _safe_texture_basename(rel, used_names)
                    texture_bytes[out_name] = vzf.read(actual)
                    for ref in _collect_texture_refs(model_data):
                        texture_name_map.setdefault(ref, Path(out_name).stem)

        model_data = _rewrite_model_textures(
            model_data, stem=stem, texture_name_map=texture_name_map
        )

        with tempfile.TemporaryDirectory(prefix="mcc-vp-pack-") as tmp:
            work = Path(tmp) / "pack"
            work.mkdir()
            _extract_source_zip(source_zip, work)
            _write_pack_mcmeta(work)

            cmd = _resolve_cmd_for_write(
                work,
                stem=stem,
                leather_item=leather_item,
                custom_model_data=custom_model_data,
                replace_existing=replace_existing,
            )

            model_out = (
                work / "assets" / "vp" / "models" / "item" / "vehicles" / f"{stem}.json"
            )
            model_out.parent.mkdir(parents=True, exist_ok=True)
            if model_out.exists() and not replace_existing:
                # Same stem already in pack → overwrite and keep CMD.
                replace_existing = True
                cmd = _resolve_cmd_for_write(
                    work,
                    stem=stem,
                    leather_item=leather_item,
                    custom_model_data=custom_model_data,
                    replace_existing=True,
                )
            model_out.write_text(
                json.dumps(model_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            tex_dir = work / "assets" / "vp" / "textures" / "item" / "vehicles" / stem
            if replace_existing and tex_dir.is_dir():
                shutil.rmtree(tex_dir, ignore_errors=True)
            if texture_bytes:
                tex_dir.mkdir(parents=True, exist_ok=True)
                for name, payload in texture_bytes.items():
                    (tex_dir / name).write_bytes(payload)

            model_resource = f"vp:item/vehicles/{stem}"
            _append_cmd_entry(
                work,
                item=leather_item,
                custom_model_data=cmd,
                model_resource=model_resource,
                replace_existing=replace_existing,
            )
            _zip_directory(work, output_zip)

    digest = sha1_file(output_zip)
    base = resource_pack_http_base()
    http_url = f"{base}/{output_name}" if base else output_name

    vendor_hjson, vendor_subdir = extract_vendor_hjson_from_zip(
        staging_token=staging_token,
        model_stem=stem,
        custom_model_data=cmd,
    )

    logger.info(
        "[vp_pack] imported vendor model=%s path=%s cmd=%s replace=%s source=%s output=%s sha1=%s hjson_subdir=%s",
        stem,
        chosen_path,
        cmd,
        replace_existing,
        source_name,
        output_name,
        digest,
        vendor_subdir or "-",
    )
    discard_staged_vendor_zip(staging_token)
    return PackMergeResult(
        output_path=output_zip,
        sha1=digest,
        custom_model_data=cmd,
        model_resource=model_resource,
        http_url=http_url,
        vendor_hjson=vendor_hjson,
        vendor_hjson_subdir=vendor_subdir,
    )


def _hjson_preference_score(path: str) -> int:
    lower = path.replace("\\", "/").lower()
    score = 0
    if "vehiclespluspro v3" in lower or "vehiclespluspro_v3" in lower:
        score += 100
    if "vehiclespluspro v2" in lower:
        score += 40
    if "/vehicles/" in lower and lower.endswith(".hjson"):
        score += 20
    if lower.endswith(".yml") or lower.endswith(".yaml"):
        score += 5
    score -= lower.count("/")
    return score


def rewrite_hjson_custom_model_data(text: str, custom_model_data: int) -> str:
    """Rewrite skin custommodeldata values to the CMD assigned in the MCC pack."""
    return re.sub(
        r"(?i)(custommodeldata\s*:\s*)\d+",
        rf"\g<1>{int(custom_model_data)}",
        text,
    )


def extract_vendor_hjson_from_zip(
    *,
    staging_token: str,
    model_stem: str,
    custom_model_data: int,
) -> tuple[str, str]:
    """
    Find VehiclesPlusPro ``*.hjson`` for ``model_stem`` in the staged vendor ZIP.

    Returns (hjson_text_with_updated_cmd, subdir) where subdir is e.g. ``cars`` / ``bikes``.
    Empty strings if none found.
    """
    stem = validate_model_stem(model_stem).lower()
    zip_path = _staged_zip_path(staging_token)
    best: tuple[int, str, str] | None = None  # score, member_name, subdir
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            lower = name.lower()
            if not (lower.endswith(".hjson") or lower.endswith(".yml")):
                continue
            if f"/{stem}." not in f"/{Path(lower).name}":
                # allow exact stem filename
                if Path(lower).stem != stem:
                    continue
            if "vehiclesplus" not in lower and "/vehicles/" not in lower:
                continue
            parts = Path(name).parts
            subdir = ""
            for i, part in enumerate(parts):
                if part.lower() == "vehicles" and i + 1 < len(parts):
                    subdir = parts[i + 1]
                    break
            if not subdir or subdir.lower().endswith((".hjson", ".yml")):
                subdir = "cars"
            score = _hjson_preference_score(name)
            if best is None or score > best[0]:
                best = (score, info.filename, subdir)
        if best is None:
            return "", ""
        raw = zf.read(best[1]).decode("utf-8", errors="replace")
    return rewrite_hjson_custom_model_data(raw, custom_model_data), best[2]


def paper_server_properties_path() -> Path:
    root = getattr(settings, "MCC_MINECRAFT_PAPER_DIR", "") or ""
    return Path(root) / "server.properties"


def vehiclesplus_config_path() -> Path | None:
    vehicles_dir = getattr(settings, "MCC_MINECRAFT_VEHICLESPLUS_VEHICLES_DIR", "") or ""
    if vehicles_dir:
        cfg = Path(vehicles_dir).parent / "config.yml"
        if cfg.is_file():
            return cfg
    paper = getattr(settings, "MCC_MINECRAFT_PAPER_DIR", "") or ""
    if paper:
        cfg = Path(paper) / "plugins" / "VehiclesPlus" / "config.yml"
        if cfg.is_file():
            return cfg
    return None


def _timestamp_suffix() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _backup_file_with_timestamp(path: Path) -> Path:
    if not path.is_file():
        raise PackAuthoringError(f"Datei nicht gefunden: {path}")
    backup = path.with_name(f"{path.name}.bak-{_timestamp_suffix()}")
    # Avoid clobber if two writes in the same second
    n = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak-{_timestamp_suffix()}-{n}")
        n += 1
    shutil.copy2(path, backup)
    return backup


def _escape_server_properties_value(value: str) -> str:
    """Escape special characters the way Paper/Java Properties expect for URLs."""
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("=", "\\=")
    )


def _set_properties_keys(text: str, updates: dict[str, str]) -> str:
    """Replace or append key=value lines; preserve comments and other keys."""
    # Keep original newline style
    newline = "\r\n" if "\r\n" in text else "\n"
    raw_lines = text.splitlines()
    pending = dict(updates)
    out: list[str] = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in pending:
            out.append(f"{key}={pending.pop(key)}")
        else:
            out.append(line)
    for key, value in pending.items():
        out.append(f"{key}={value}")
    body = newline.join(out)
    if text.endswith(("\n", "\r\n")) and not body.endswith("\n"):
        body += newline
    return body


def _set_yaml_scalar_key(text: str, key: str, value: str) -> str:
    """Replace a top-level ``key: value`` line (VehiclesPlus config.yml)."""
    pattern = re.compile(
        rf"^({re.escape(key)}\s*:\s*).*$",
        re.MULTILINE,
    )
    replacement = rf"\g<1>{value}"
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    newline = "\r\n" if "\r\n" in text else "\n"
    suffix = "" if text.endswith(("\n", "\r\n")) else newline
    return f"{text}{suffix}{key}: {value}{newline}"


def apply_resource_pack_to_server(
    *,
    pack_http_url: str,
    sha1: str,
    update_vehiclesplus: bool = True,
) -> ServerPackApplyResult:
    """
    Backup and update Paper ``server.properties`` resource-pack keys.
    Optionally sync VehiclesPlus ``config.yml`` ``resourcePackUrl``.
    """
    url = (pack_http_url or "").strip()
    digest = (sha1 or "").strip().lower()
    if not url:
        raise PackAuthoringError("Resource-Pack-URL fehlt.")
    if not re.fullmatch(r"[0-9a-f]{40}", digest):
        raise PackAuthoringError("SHA1 ungültig (40 Hex-Zeichen erwartet).")

    props_path = paper_server_properties_path()
    if not props_path.is_file():
        raise PackAuthoringError(
            f"server.properties nicht gefunden: {props_path} "
            "(MCC_MINECRAFT_PAPER_DIR prüfen)."
        )

    pack_id = str(uuid4())
    props_backup = _backup_file_with_timestamp(props_path)
    original = props_path.read_text(encoding="utf-8", errors="replace")
    updated = _set_properties_keys(
        original,
        {
            "resource-pack": _escape_server_properties_value(url),
            "resource-pack-sha1": digest,
            "resource-pack-id": pack_id,
        },
    )
    props_path.write_text(updated, encoding="utf-8")
    logger.info(
        "[vp_pack] updated server.properties resource-pack=%s sha1=%s backup=%s",
        url,
        digest,
        props_backup.name,
    )

    vp_cfg: Path | None = None
    vp_backup: Path | None = None
    if update_vehiclesplus:
        vp_cfg = vehiclesplus_config_path()
        if vp_cfg is not None:
            vp_backup = _backup_file_with_timestamp(vp_cfg)
            vp_text = vp_cfg.read_text(encoding="utf-8", errors="replace")
            vp_cfg.write_text(
                _set_yaml_scalar_key(vp_text, "resourcePackUrl", url),
                encoding="utf-8",
            )
            logger.info(
                "[vp_pack] updated VehiclesPlus resourcePackUrl=%s backup=%s",
                url,
                vp_backup.name,
            )

    return ServerPackApplyResult(
        properties_path=props_path,
        properties_backup=props_backup,
        resource_pack_url=url,
        sha1=digest,
        resource_pack_id=pack_id,
        vehiclesplus_config=vp_cfg,
        vehiclesplus_backup=vp_backup,
    )


def scaffold_lastenrad_hjson(
    *,
    model_id: str = "Lastenrad",
    custom_model_data: int,
    display_name: str = "&aLastenrad",
) -> str:
    """Minimal bike HJSON pointing at the merged leather_boots CMD."""
    mid = validate_model_stem(model_id)
    return f"""{{
  id: {mid}
  displayName: {display_name}
  typeId: bikes
  typeStrategies:
  [
    {{
      movementType: land
    }}
  ]
  price: 0
  permissions:
  {{
    buy: vp.buy.{mid}
    adjust: vp.adjust.{mid}
    spawn: vp.spawn.{mid}
    ride: vp.ride.{mid}
    sitWithoutRidePermission: true
  }}
  availableColors:
  [
    {{ red: 255, green: 255, blue: 255 }}
    {{ red: 40, green: 40, blue: 40 }}
    {{ red: 180, green: 80, blue: 40 }}
  ]
  parts:
  [
    {{
      type: bikeskin
      xoffset: 0
      yoffset: 0.45
      zoffset: 0
      rotationOffset: 0
      item:
      {{
        material: LEATHER_BOOTS
        custommodeldata: {int(custom_model_data)}
        color:
        {{
          red: 255
          green: 255
          blue: 255
        }}
      }}
      position: HEAD
      wheelieOffset: 0
    }}
    {{
      type: bikeseat
      xoffset: 0
      yoffset: -0.6
      zoffset: 0
      rotationOffset: 0
      steer: true
      guiitem:
      {{
        damage: 1
        material: DIAMOND_HOE
        unbreakable: true
      }}
    }}
  ]
  maxSpeed:
  {{
    base: 45
    upgradable: false
    max: 45
    step: 5
    stepCost: 0
    unit: km/h
  }}
  fuelTank:
  {{
    base: 50
    upgradable: false
    max: 50
    step: 5
    stepCost: 0
    unit: L
  }}
  turningRadius:
  {{
    base: 7
    upgradable: false
    max: 7
    step: 1
    stepCost: 0
    unit: ""
  }}
  acceleration:
  {{
    base: 35
    upgradable: false
    max: 35
    step: 1
    stepCost: 0
    unit: ""
  }}
  hitbox:
  {{
    length: 3
    width: 1.4
    height: 1.2
  }}
  fuel:
  {{
    typeId: gasoline
    usage: 4
  }}
  exhaust:
  {{
    enabled: false
    particle: LARGE_SMOKE
    xoffset: 0
    zoffset: 0
    yoffset: 0
  }}
  horn:
  {{
    enabled: false
    sound:
    {{
      sound: block.note_block.bass
      volume: 1
      pitch: 1
      duration: 3
    }}
  }}
  sounds:
  {{
    idle:
    {{
      sound: vp.idle
      volume: 1
      pitch: 1
      duration: 6
    }}
    start:
    {{
      sound: vp.start
      volume: 1
      pitch: 1
      duration: 2
    }}
    accelerate:
    {{
      sound: vp.accelerate
      volume: 1
      pitch: 1
      duration: 2
    }}
    driving:
    {{
      sound: vp.driving
      volume: 1
      pitch: 1
      duration: 2
    }}
    slowingDown:
    {{
      sound: vp.slowingdown
      volume: 1
      pitch: 1
      duration: 2
    }}
  }}
  realisticSteering: false
  trunkSize: 0
  drift: false
  exitWhileMoving: true
  health: 100
  gearbox:
  {{
    realistic: false
    cooldown: 10
  }}
}}
"""


@dataclass(frozen=True)
class VehicleExportResult:
    """In-memory ZIP export of one VehiclesPlus vehicle for backup / re-import."""

    filename: str
    payload: bytes
    model_id: str
    category: str
    display_name: str
    has_hjson: bool
    has_model: bool
    texture_count: int
    custom_model_data: int | None


_CMD_IN_HJSON_RE = re.compile(
    r"(?i)custommodeldata\s*:\s*(\d+)",
)


def _parse_cmd_from_hjson(text: str) -> int | None:
    match = _CMD_IN_HJSON_RE.search(text or "")
    if not match:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    return value if value >= 1 else None


def build_vehicle_export_zip(
    *,
    model_id: str,
    source_pack_name: str = "",
) -> VehicleExportResult:
    """
    Build a downloadable ZIP for one VehiclesPlus vehicle.

    Layout (compatible with the Admin ZIP-import analyzer)::

        manifest.json
        README.txt
        vehicles/<category>/<id>.hjson
        Resource Pack/assets/vp/models/item/vehicles/<id>.json
        Resource Pack/assets/vp/textures/item/vehicles/<id>/*

    HJSON always comes from the live plugin vehicles directory. Model/textures
    are taken from ``source_pack_name`` when present in that pack ZIP.
    """
    from minecraft.services.vehiclesplus_catalog import (
        list_vehiclesplus_models,
        vehiclesplus_vehicles_dir,
    )

    stem = validate_model_stem(model_id)
    models = {m.model_id: m for m in list_vehiclesplus_models()}
    chosen = models.get(stem)
    if chosen is None:
        for mid, model in models.items():
            if mid.lower() == stem.lower():
                chosen = model
                break
    if chosen is None:
        raise PackAuthoringError(
            f"Fahrzeug „{stem}“ nicht im Plugin-Verzeichnis "
            f"({vehiclesplus_vehicles_dir()}) gefunden."
        )

    hjson_path = Path(chosen.path)
    if not hjson_path.is_file():
        raise PackAuthoringError(f"HJSON fehlt: {hjson_path}")
    hjson_text = hjson_path.read_text(encoding="utf-8", errors="replace")
    cmd = _parse_cmd_from_hjson(hjson_text)

    pack_name = ""
    if (source_pack_name or "").strip():
        pack_name = validate_pack_filename(source_pack_name, field="Export-Pack")

    model_bytes: bytes | None = None
    texture_files: list[tuple[str, bytes]] = []
    if pack_name:
        pack_path = resource_packs_dir() / pack_name
        if not pack_path.is_file():
            raise PackAuthoringError(f"Export-Pack nicht gefunden: {pack_name}")
        model_rel = f"assets/vp/models/item/vehicles/{chosen.model_id}.json"
        tex_prefix = f"assets/vp/textures/item/vehicles/{chosen.model_id}/"
        try:
            with zipfile.ZipFile(pack_path, "r") as zf:
                names = {n.replace("\\", "/"): n for n in zf.namelist()}
                if model_rel in names:
                    model_bytes = zf.read(names[model_rel])
                for logical, actual in names.items():
                    if not logical.startswith(tex_prefix):
                        continue
                    if logical.endswith("/"):
                        continue
                    texture_files.append((logical[len(tex_prefix) :], zf.read(actual)))
        except zipfile.BadZipFile as exc:
            raise PackAuthoringError(f"Ungültiges Pack-ZIP: {exc}") from exc

    manifest = {
        "format": "mcc-vp-vehicle-export-v1",
        "model_id": chosen.model_id,
        "category": chosen.category,
        "display_name": chosen.display_name,
        "custom_model_data": cmd,
        "source_pack": pack_name or None,
        "has_hjson": True,
        "has_model": model_bytes is not None,
        "texture_count": len(texture_files),
        "reimport_hint": (
            "In Admin → VehiclesPlus Resourcepack: dieses ZIP analysieren, "
            "Modell wählen, Ziel-Pack setzen, bei gleicher ID ersetzen."
        ),
    }
    readme = (
        "MCC VehiclesPlus Fahrzeug-Export\n"
        "================================\n\n"
        f"Fahrzeug: {chosen.display_name} ({chosen.model_id})\n"
        f"Kategorie: {chosen.category}\n"
        f"custom_model_data (HJSON): {cmd if cmd is not None else '-'}\n"
        f"Quell-Pack fuer Assets: {pack_name or '-'}\n\n"
        "Inhalt:\n"
        f"  vehicles/{chosen.category}/{chosen.model_id}.hjson\n"
        "  Resource Pack/assets/vp/models/...  (falls im Pack vorhanden)\n"
        "  Resource Pack/assets/vp/textures/...\n\n"
        "Re-Import:\n"
        "  1) Admin -> Minecraft -> VehiclesPlus Resourcepack\n"
        "  2) ZIP analysieren -> Modell waehlen -> Pack mergen\n"
        "  3) HJSON schreiben aktiv lassen (oder HJSON manuell nach\n"
        f"     plugins/VehiclesPlus/vehicles/{chosen.category}/ kopieren)\n"
        "  4) Paper: vehiclemodel reload <id>\n"
    )

    buffer = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as out:
        out.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        out.writestr("README.txt", readme)
        out.writestr(
            f"vehicles/{chosen.category}/{chosen.model_id}.hjson",
            hjson_text.encode("utf-8"),
        )
        if model_bytes is not None:
            out.writestr(
                f"Resource Pack/assets/vp/models/item/vehicles/{chosen.model_id}.json",
                model_bytes,
            )
        for name, payload in sorted(texture_files, key=lambda t: t[0].lower()):
            safe = Path(name).name
            if not safe or ".." in name.replace("\\", "/"):
                continue
            out.writestr(
                f"Resource Pack/assets/vp/textures/item/vehicles/{chosen.model_id}/{safe}",
                payload,
            )

    buffer.seek(0)
    payload = buffer.read()
    buffer.close()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"mcc-vp-{chosen.model_id}-{stamp}.zip"
    logger.info(
        "[vp_pack] exported vehicle=%s category=%s pack=%s model=%s textures=%s bytes=%s",
        chosen.model_id,
        chosen.category,
        pack_name or "-",
        bool(model_bytes),
        len(texture_files),
        len(payload),
    )
    return VehicleExportResult(
        filename=filename,
        payload=payload,
        model_id=chosen.model_id,
        category=chosen.category,
        display_name=chosen.display_name,
        has_hjson=True,
        has_model=model_bytes is not None,
        texture_count=len(texture_files),
        custom_model_data=cmd,
    )
