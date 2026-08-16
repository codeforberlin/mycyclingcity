# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    grant_catalog.py
# @note    Generic Stadtsteuerung grants (VehiclesPlus garage, inventory, …).

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from config.logger_utils import get_logger
from minecraft.models import (
    MCSession,
    MinecraftGrantCatalogItem,
    MinecraftGrantRecord,
)

logger = get_logger("minecraft")

DEFAULT_VEHICLE_GRANT_TEMPLATE = "v give {player} {model}"
DEFAULT_VEHICLE_REPAIR_TEMPLATE = "v repair {player}"
DEFAULT_VEHICLE_REVOKE_TEMPLATE = "mccbridge vpremove {player} {model}"


@dataclass(frozen=True)
class GrantSlotSummary:
    total_active: int
    session_grants: int
    velos_redeems: int
    labels: tuple[str, ...]


def ensure_default_catalog_items() -> None:
    """Seed ExampleBike if the catalog is empty (idempotent)."""
    if MinecraftGrantCatalogItem.objects.exists():
        # Backfill empty revoke templates for vehicle garage items.
        MinecraftGrantCatalogItem.objects.filter(
            kind=MinecraftGrantCatalogItem.KIND_VEHICLE_GARAGE,
            rcon_revoke_template="",
        ).update(rcon_revoke_template=DEFAULT_VEHICLE_REVOKE_TEMPLATE)
        return
    MinecraftGrantCatalogItem.objects.create(
        slug="example-bike",
        name="Example Bike (Garage)",
        kind=MinecraftGrantCatalogItem.KIND_VEHICLE_GARAGE,
        enabled=True,
        sort_order=10,
        applies_to_player=True,
        applies_to_builder=True,
        model_id="ExampleBike",
        quantity_default=1,
        velos_cost=0,
        repair_velos_cost=1000,
        rcon_grant_template=DEFAULT_VEHICLE_GRANT_TEMPLATE,
        rcon_revoke_template=DEFAULT_VEHICLE_REVOKE_TEMPLATE,
        rcon_repair_template=DEFAULT_VEHICLE_REPAIR_TEMPLATE,
        notes="VehiclesPlus ExampleBike → persönliche Garage",
    )


def revoke_template_for_item(item: MinecraftGrantCatalogItem) -> str:
    """RCON/console revoke command; falls back for vehicle garage items."""
    text = (item.rcon_revoke_template or "").strip()
    if text:
        return text
    if item.kind == MinecraftGrantCatalogItem.KIND_VEHICLE_GARAGE:
        return DEFAULT_VEHICLE_REVOKE_TEMPLATE
    return ""


def _garage_player_for_record(record: MinecraftGrantRecord, *, fallback: str) -> str:
    """VehiclesPlus personal garage is named after the MS/online login."""
    ms = (record.ms_username or "").strip()
    if ms:
        return ms
    try:
        from minecraft.models import MinecraftPlayAccount

        account = (
            MinecraftPlayAccount.objects.filter(short_name__iexact=fallback)
            .only("ms_username")
            .first()
        )
        if account is not None and (account.ms_username or "").strip():
            return (account.ms_username or "").strip()
    except Exception:
        pass
    return (fallback or "").strip()


def catalog_items_for_account_type(account_type: str) -> list[MinecraftGrantCatalogItem]:
    ensure_default_catalog_items()
    qs = MinecraftGrantCatalogItem.objects.filter(enabled=True)
    if account_type == MCSession.ACCOUNT_BUILDER:
        qs = qs.filter(applies_to_builder=True)
    else:
        qs = qs.filter(applies_to_player=True)
    return list(qs.order_by("sort_order", "name"))


def normalize_grant_slugs(
    raw_slugs: Iterable[str] | None,
    *,
    account_type: str,
) -> list[str]:
    allowed = {item.slug for item in catalog_items_for_account_type(account_type)}
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_slugs or []:
        slug = (raw or "").strip()
        if not slug or slug in seen or slug not in allowed:
            continue
        seen.add(slug)
        out.append(slug)
    return out


def render_rcon_template(
    template: str,
    *,
    player: str,
    item: MinecraftGrantCatalogItem,
    quantity: int | None = None,
) -> str | None:
    text = (template or "").strip()
    if not text:
        return None
    qty = int(quantity if quantity is not None else item.quantity_default or 1)
    rendered = (
        text.replace("{player}", (player or "").strip())
        .replace("{model}", (item.model_id or item.slug).strip())
        .replace("{slug}", item.slug)
        .replace("{quantity}", str(max(1, qty)))
    )
    return rendered or None


def build_grant_commands(
    player: str,
    slugs: Iterable[str],
    *,
    account_type: str,
) -> list[str]:
    name = (player or "").strip()
    if not name:
        return []
    by_slug = {
        item.slug: item for item in catalog_items_for_account_type(account_type)
    }
    commands: list[str] = []
    for slug in normalize_grant_slugs(slugs, account_type=account_type):
        item = by_slug.get(slug)
        if item is None:
            continue
        cmd = render_rcon_template(
            item.rcon_grant_template,
            player=name,
            item=item,
        )
        if cmd:
            commands.append(cmd)
    return commands


def active_records_for_account(account_name: str) -> list[MinecraftGrantRecord]:
    name = (account_name or "").strip()
    if not name:
        return []
    return list(
        MinecraftGrantRecord.objects.filter(
            account_name__iexact=name,
            status=MinecraftGrantRecord.STATUS_ACTIVE,
        )
        .select_related("catalog_item")
        .order_by("granted_at")
    )


def summarize_active_grants(account_name: str) -> GrantSlotSummary:
    records = active_records_for_account(account_name)
    session_n = sum(
        1 for r in records if r.source == MinecraftGrantRecord.SOURCE_SESSION
    )
    velos_n = sum(1 for r in records if r.source == MinecraftGrantRecord.SOURCE_VELOS)
    labels = tuple(
        f"{r.catalog_item.name}"
        + (
            f" ({r.quantity})"
            if r.quantity and r.quantity > 1
            else ""
        )
        for r in records
    )
    return GrantSlotSummary(
        total_active=len(records),
        session_grants=session_n,
        velos_redeems=velos_n,
        labels=labels,
    )


def _debit_velos_for_item(
    *,
    account_name: str,
    account_type: str,
    amount: int,
    user: AbstractBaseUser | None,
    note: str,
) -> int:
    if amount < 1:
        return 0
    from minecraft.models import MinecraftSessionWaitlistEntry
    from minecraft.services.world_tickets import resolve_waitlist_cyclist
    from api.services.velos_redemption import redeem_cyclist_velos

    queue = (
        MinecraftSessionWaitlistEntry.QUEUE_BUILDER
        if account_type == MCSession.ACCOUNT_BUILDER
        else MinecraftSessionWaitlistEntry.QUEUE_PLAYER
    )
    cyclist = resolve_waitlist_cyclist(account_name, account_type=queue)
    if cyclist is None:
        raise ValueError(
            str(_("Kein Radler verknüpft — Velos-Einlösung nicht möglich."))
        )
    result = redeem_cyclist_velos(
        cyclist,
        redeemed_by=user if getattr(user, "is_authenticated", False) else None,
        note=note,
        amount=amount,
    )
    if not result.success:
        from minecraft.services.session_control import InsufficientVelosError

        raise InsufficientVelosError(result.message or str(_("Nicht genug Velos.")))
    return int(result.velos_redeemed or amount)


@transaction.atomic
def clear_active_grants_for_account(
    account_name: str,
    *,
    user: AbstractBaseUser | None = None,
) -> tuple[int, list[str]]:
    """
    Mark all active grants on the slot as revoked and collect RCON revoke commands.

    Returns (revoked_count, rcon_commands). Caller runs RCON.
    """
    name = (account_name or "").strip()
    records = active_records_for_account(name)
    if not records:
        return 0, []

    now = timezone.now()
    commands: list[str] = []
    player = ""
    for record in records:
        garage_player = _garage_player_for_record(record, fallback=name)
        player = garage_player or player
        cmd = render_rcon_template(
            revoke_template_for_item(record.catalog_item),
            player=garage_player or name,
            item=record.catalog_item,
            quantity=record.quantity,
        )
        if cmd:
            commands.append(cmd)
        record.status = MinecraftGrantRecord.STATUS_REVOKED
        record.revoked_at = now
        record.save(update_fields=["status", "revoked_at"])

    logger.info(
        "[grant_catalog] cleared account=%s count=%s by=%s",
        name,
        len(records),
        getattr(user, "username", None),
    )
    return len(records), commands


@transaction.atomic
def create_grant_records_after_rcon(
    *,
    session: MCSession,
    slugs: Iterable[str],
    player: str,
    user: AbstractBaseUser | None = None,
) -> list[MinecraftGrantRecord]:
    """Persist grant rows after successful (or attempted) RCON give."""
    account_type = session.account_type
    by_slug = {
        item.slug: item for item in catalog_items_for_account_type(account_type)
    }
    created: list[MinecraftGrantRecord] = []
    for slug in normalize_grant_slugs(slugs, account_type=account_type):
        item = by_slug.get(slug)
        if item is None:
            continue
        source = (
            MinecraftGrantRecord.SOURCE_VELOS
            if item.velos_cost > 0
            else MinecraftGrantRecord.SOURCE_SESSION
        )
        velos_charged = 0
        if item.velos_cost > 0:
            velos_charged = _debit_velos_for_item(
                account_name=session.account_name,
                account_type=account_type,
                amount=item.velos_cost,
                user=user,
                note=str(
                    _("Vergabe „%(name)s“ (Katalog)") % {"name": item.name}
                ),
            )
        record = MinecraftGrantRecord.objects.create(
            catalog_item=item,
            account_name=session.account_name,
            account_type=account_type,
            session=session,
            ms_username=(player or session.ms_username or "").strip(),
            source=source,
            status=MinecraftGrantRecord.STATUS_ACTIVE,
            quantity=item.quantity_default,
            velos_charged=velos_charged,
            granted_by=user if getattr(user, "is_authenticated", False) else None,
        )
        created.append(record)
    return created


def sync_grant_records_for_session(
    session: MCSession,
    *,
    player: str,
    user: AbstractBaseUser | None = None,
) -> list[MinecraftGrantRecord]:
    """Create missing active records for session.grant_catalog_slugs (idempotent)."""
    slugs = list(session.grant_catalog_slugs or [])
    if not slugs:
        return []
    existing = set(
        MinecraftGrantRecord.objects.filter(
            session=session,
            status=MinecraftGrantRecord.STATUS_ACTIVE,
        ).values_list("catalog_item__slug", flat=True)
    )
    missing = [s for s in slugs if s not in existing]
    if not missing:
        return []
    return create_grant_records_after_rcon(
        session=session,
        slugs=missing,
        player=player,
        user=user,
    )


def repair_vehicle_for_account(
    account_name: str,
    *,
    catalog_slug: str | None = None,
    user: AbstractBaseUser | None = None,
) -> tuple[str, list[str]]:
    """
    Admin repair outside the game: debit repair_velos_cost, return RCON commands.

    Picks the first active vehicle_garage record when slug omitted.
    """
    name = (account_name or "").strip()
    records = active_records_for_account(name)
    vehicle_records = [
        r
        for r in records
        if r.catalog_item.kind == MinecraftGrantCatalogItem.KIND_VEHICLE_GARAGE
    ]
    if catalog_slug:
        vehicle_records = [
            r for r in vehicle_records if r.catalog_item.slug == catalog_slug
        ]
    if not vehicle_records:
        raise ValueError(str(_("Kein aktives Fahrzeug-Grant auf diesem Slot.")))

    record = vehicle_records[0]
    item = record.catalog_item
    cost = int(item.repair_velos_cost or 0)
    player = (record.ms_username or "").strip() or name
    cmd = render_rcon_template(
        item.rcon_repair_template or "v repair {player}",
        player=player,
        item=item,
    )
    if not cmd:
        raise ValueError(str(_("Kein Reparatur-RCON für diesen Katalogeintrag.")))

    if cost > 0:
        _debit_velos_for_item(
            account_name=name,
            account_type=record.account_type,
            amount=cost,
            user=user,
            note=str(
                _("Reparatur „%(name)s“ (%(cost)s Velos)")
                % {"name": item.name, "cost": cost}
            ),
        )
    return item.name, [cmd]


def run_grant_rcon_commands(commands: list[str]) -> str:
    """Execute grant/clear/repair RCON commands (raises RconSequenceError)."""
    from minecraft.services.session_control import RconSequenceError, _run_or_raise

    if not commands:
        return ""
    try:
        return _run_or_raise(commands)
    except RconSequenceError:
        raise


def clear_grants_with_rcon(
    account_name: str,
    *,
    user: AbstractBaseUser | None = None,
) -> int:
    count, cmds = clear_active_grants_for_account(account_name, user=user)
    run_grant_rcon_commands(cmds)
    return count


def repair_vehicle_with_rcon(
    account_name: str,
    *,
    catalog_slug: str | None = None,
    user: AbstractBaseUser | None = None,
) -> str:
    label, cmds = repair_vehicle_for_account(
        account_name,
        catalog_slug=catalog_slug,
        user=user,
    )
    run_grant_rcon_commands(cmds)
    return label
