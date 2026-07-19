# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from minecraft.models import (
    MinecraftOutboxEvent,
    MinecraftPlayerScoreboardSnapshot,
    MinecraftShopItem,
    MinecraftWorkerState,
)
from minecraft.services.bridge_connection import get_connected_server_ids
from minecraft.services.rcon_client import check_connection
from minecraft.services.shop_catalog import category_count, item_count
from minecraft.services.team_registration import active_registrations, get_objective_spendable
from minecraft.services.team_velos_query import get_team_velos_by_mc_username


HEARTBEAT_STALE_AFTER = timedelta(minutes=2)
SNAPSHOT_STALE_AFTER = timedelta(hours=1)
OUTBOX_PENDING_WARNING = 10


@dataclass
class ShopReadinessCheck:
    id: str
    label: str
    ok: bool
    severity: str
    detail: str
    hint: str = ""
    action: str = ""


@dataclass
class ShopReadinessReport:
    ok: bool
    checks: list[ShopReadinessCheck] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        errors = sum(1 for check in self.checks if check.severity == "error")
        warnings = sum(1 for check in self.checks if check.severity == "warning")
        passed = sum(1 for check in self.checks if check.ok)
        return {"errors": errors, "warnings": warnings, "passed": passed}

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "checks": [
                {
                    "id": check.id,
                    "label": str(check.label),
                    "ok": check.ok,
                    "severity": check.severity,
                    "detail": str(check.detail),
                    "hint": str(check.hint),
                    "action": check.action,
                }
                for check in self.checks
            ],
        }


def _probe_script_status(script_path: Path, action: str = "status") -> bool:
    if not script_path.exists() or not os.access(script_path, os.X_OK):
        return False
    try:
        result = subprocess.run(
            [str(script_path), action],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _script_path(name: str) -> Path:
    return Path(settings.BASE_DIR) / "scripts" / name


def _add_check(
    checks: list[ShopReadinessCheck],
    *,
    check_id: str,
    label: str,
    ok: bool,
    detail: str,
    severity: str | None = None,
    hint: str = "",
    action: str = "",
) -> None:
    checks.append(
        ShopReadinessCheck(
            id=check_id,
            label=label,
            ok=ok,
            severity=severity or ("ok" if ok else "error"),
            detail=detail,
            hint=hint,
            action=action,
        )
    )


def check_shop_readiness(
    *,
    worker_running: bool | None = None,
    snapshot_worker_running: bool | None = None,
    ws_running: bool | None = None,
) -> ShopReadinessReport:
    checks: list[ShopReadinessCheck] = []
    minecraft_script = _script_path("minecraft.sh")
    ws_script = _script_path("minecraft_ws.sh")

    if worker_running is None:
        worker_running = _probe_script_status(minecraft_script, "status")
    if snapshot_worker_running is None:
        snapshot_worker_running = _probe_script_status(minecraft_script, "snapshot-status")
    if ws_running is None:
        ws_running = _probe_script_status(ws_script, "status")

    # --- Infrastructure ---
    rcon_ok, rcon_error, rcon_mode = check_connection()
    if rcon_ok and rcon_mode == "auth":
        rcon_detail = _("RCON erreichbar und authentifiziert")
        rcon_severity = "ok"
    elif rcon_ok:
        rcon_detail = _("RCON-Port erreichbar (Authentifizierung nicht geprüft)")
        rcon_severity = "warning"
    else:
        rcon_detail = _("RCON nicht erreichbar: %(error)s") % {"error": rcon_error}
        rcon_severity = "error"
    _add_check(
        checks,
        check_id="rcon",
        label=_("RCON-Verbindung"),
        ok=rcon_ok,
        severity=rcon_severity,
        detail=rcon_detail,
        hint=_("RCON-Host, Port und Passwort in .env prüfen") if not rcon_ok else "",
        action="rcon-test" if not rcon_ok else "",
    )

    worker_state = MinecraftWorkerState.get_state()
    worker_ok = bool(worker_running)
    if worker_ok and worker_state.last_error:
        worker_severity = "warning"
        worker_detail = _("Bridge-Worker läuft, letzter Fehler: %(error)s") % {
            "error": worker_state.last_error[:200]
        }
    elif worker_ok:
        worker_severity = "ok"
        worker_detail = _("Bridge-Worker-Prozess läuft")
        if worker_state.last_heartbeat:
            age = timezone.now() - worker_state.last_heartbeat
            if age > HEARTBEAT_STALE_AFTER:
                worker_severity = "warning"
                worker_detail = _("Bridge-Worker läuft, Heartbeat veraltet (%(minutes)s Min.)") % {
                    "minutes": int(age.total_seconds() // 60)
                }
    else:
        worker_severity = "error"
        worker_detail = _("Bridge-Worker ist gestoppt — Scoreboard-Sync aus der Datenbank ausstehend")
    _add_check(
        checks,
        check_id="bridge_worker",
        label=_("Bridge-Worker"),
        ok=worker_ok and worker_severity != "error",
        severity=worker_severity,
        detail=worker_detail,
        hint=_("Worker in der Steuerzentrale starten") if not worker_ok else "",
        action="start" if not worker_ok else "",
    )

    ws_enabled = settings.MCC_MINECRAFT_WS_ENABLED
    if not ws_enabled:
        ws_severity = "error"
        ws_detail = _("WebSocket ist in den Einstellungen deaktiviert")
        ws_ok = False
    elif not ws_running:
        ws_severity = "error"
        ws_detail = _("Daphne-WebSocket-Server läuft nicht")
        ws_ok = False
    else:
        ws_severity = "ok"
        ws_detail = _("WebSocket-Server läuft")
        ws_ok = True
    _add_check(
        checks,
        check_id="websocket",
        label=_("WebSocket-Server"),
        ok=ws_ok,
        severity=ws_severity,
        detail=ws_detail,
        hint=_("WebSocket starten") if ws_enabled and not ws_running else "",
        action="ws-start" if ws_enabled and not ws_running else "",
    )

    connected_servers = get_connected_server_ids()
    allowed_servers = list(settings.MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS or [])
    if not ws_enabled:
        bridge_severity = "error"
        bridge_detail = _("WebSocket deaktiviert — MCC-Bridge kann nicht verbunden sein")
        bridge_ok = False
    elif not allowed_servers:
        bridge_severity = "error"
        bridge_detail = _("Keine erlaubten server_id in MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS")
        bridge_ok = False
    elif not connected_servers:
        bridge_severity = "error"
        bridge_detail = _("Keine aktive MCC-Bridge-Verbindung")
        bridge_ok = False
    else:
        bridge_ok = True
        bridge_severity = "ok"
        bridge_detail = _("MCC-Bridge verbunden: %(servers)s") % {
            "servers": ", ".join(connected_servers)
        }
        missing_allowed = [server_id for server_id in allowed_servers if server_id not in connected_servers]
        if missing_allowed:
            bridge_severity = "warning"
            bridge_detail = _(
                "Verbunden: %(connected)s — nicht verbunden: %(missing)s"
            ) % {
                "connected": ", ".join(connected_servers),
                "missing": ", ".join(missing_allowed),
            }
    _add_check(
        checks,
        check_id="bridge_connected",
        label=_("MCC-Bridge"),
        ok=bridge_ok,
        severity=bridge_severity,
        detail=bridge_detail,
        hint=_("Auf dem MC-Server /mccbridge status prüfen") if not bridge_ok else "",
    )

    failed_outbox = MinecraftOutboxEvent.objects.filter(
        status=MinecraftOutboxEvent.STATUS_FAILED
    ).count()
    pending_outbox = MinecraftOutboxEvent.objects.filter(
        status=MinecraftOutboxEvent.STATUS_PENDING
    ).count()
    if failed_outbox > 0:
        outbox_severity = "error"
        outbox_detail = _("%(count)s fehlgeschlagene Outbox-Events") % {"count": failed_outbox}
        outbox_ok = False
    elif pending_outbox > OUTBOX_PENDING_WARNING:
        outbox_severity = "warning"
        outbox_detail = _("%(count)s ausstehende Outbox-Events") % {"count": pending_outbox}
        outbox_ok = True
    else:
        outbox_severity = "ok"
        outbox_detail = _("Outbox in Ordnung (%(pending)s ausstehend)") % {"pending": pending_outbox}
        outbox_ok = True
    _add_check(
        checks,
        check_id="outbox",
        label=_("Outbox"),
        ok=outbox_ok,
        severity=outbox_severity,
        detail=outbox_detail,
        hint=_("Postausgang bereinigen und Teams synchronisieren") if failed_outbox else "",
        action="cleanup" if failed_outbox else ("sync" if pending_outbox > OUTBOX_PENDING_WARNING else ""),
    )

    if not snapshot_worker_running:
        _add_check(
            checks,
            check_id="snapshot_worker",
            label=_("Snapshot-Worker"),
            ok=True,
            severity="warning",
            detail=_("Snapshot-Worker gestoppt — Scoreboard-Abgleich nur manuell"),
            hint=_("Snapshot Worker starten oder Snapshot manuell aktualisieren"),
            action="snapshot-start",
        )

    # --- Configuration ---
    objective = get_objective_spendable()
    objective_ok = bool(objective)
    _add_check(
        checks,
        check_id="objective",
        label=_("Scoreboard-Objective"),
        ok=objective_ok,
        severity="error" if not objective_ok else "ok",
        detail=_("Aktives Objective: %(name)s") % {"name": objective or "—"}
        if objective_ok
        else _("Kein Objective für Velos konfiguriert"),
        hint=_("Objective in der Scoreboard-Konfiguration setzen") if not objective_ok else "",
    )

    # --- Velos consistency ---
    registrations = list(active_registrations())
    if not registrations:
        _add_check(
            checks,
            check_id="teams_registered",
            label=_("Registrierte Teams"),
            ok=False,
            severity="error",
            detail=_("Kein aktives Team für Minecraft registriert"),
            hint=_("Teams in der Steuerzentrale registrieren"),
        )
    else:
        _add_check(
            checks,
            check_id="teams_registered",
            label=_("Registrierte Teams"),
            ok=True,
            severity="ok",
            detail=_("%(count)s aktive Team-Registrierung(en)") % {"count": len(registrations)},
        )

    snapshots = {
        snapshot.player_name: snapshot
        for snapshot in MinecraftPlayerScoreboardSnapshot.objects.all()
    }
    drifts: list[str] = []
    missing_snapshots: list[str] = []
    lookup_errors: list[str] = []

    for registration in registrations:
        group = registration.group
        db_value = int(group.velos_spendable or 0)
        player = registration.mc_username

        shop_data = get_team_velos_by_mc_username(player)
        if shop_data is None:
            lookup_errors.append(player)
        elif int(shop_data["velos_spendable"]) != db_value:
            lookup_errors.append(f"{player} (Shop-Lookup {shop_data['velos_spendable']} ≠ DB {db_value})")

        snapshot = snapshots.get(player)
        if snapshot is None:
            missing_snapshots.append(player)
            continue
        snapshot_value = int(snapshot.velos_spendable or 0)
        if db_value != snapshot_value:
            drifts.append(f"{player} (DB {db_value}, Scoreboard {snapshot_value})")

    if drifts:
        _add_check(
            checks,
            check_id="velos_drift",
            label=_("Velos DB ↔ Scoreboard"),
            ok=False,
            severity="error",
            detail=_("Abweichung bei: %(teams)s") % {"teams": "; ".join(drifts)},
            hint=_("Der Shop nutzt die Datenbank — Scoreboard muss synchronisiert werden"),
            action="sync",
        )
    elif missing_snapshots:
        _add_check(
            checks,
            check_id="velos_drift",
            label=_("Velos DB ↔ Scoreboard"),
            ok=True,
            severity="warning",
            detail=_("Kein Snapshot für: %(teams)s") % {"teams": ", ".join(missing_snapshots)},
            hint=_("Snapshot aktualisieren und Teams synchronisieren"),
            action="snapshot",
        )
    elif registrations:
        stale_snapshots = []
        now = timezone.now()
        for registration in registrations:
            snapshot = snapshots.get(registration.mc_username)
            if snapshot and snapshot.captured_at and now - snapshot.captured_at > SNAPSHOT_STALE_AFTER:
                stale_snapshots.append(registration.mc_username)
        if stale_snapshots:
            _add_check(
                checks,
                check_id="velos_drift",
                label=_("Velos DB ↔ Scoreboard"),
                ok=True,
                severity="warning",
                detail=_("Snapshot älter als %(hours)s h: %(teams)s")
                % {"hours": int(SNAPSHOT_STALE_AFTER.total_seconds() // 3600), "teams": ", ".join(stale_snapshots)},
                hint=_("Snapshot aktualisieren"),
                action="snapshot",
            )
        else:
            _add_check(
                checks,
                check_id="velos_drift",
                label=_("Velos DB ↔ Scoreboard"),
                ok=True,
                severity="ok",
                detail=_("Alle registrierten Teams stimmen überein"),
            )

    if lookup_errors:
        _add_check(
            checks,
            check_id="shop_lookup",
            label=_("Shop-Velos-Abfrage"),
            ok=False,
            severity="error",
            detail=_("Shop-Lookup fehlgeschlagen für: %(teams)s") % {"teams": "; ".join(lookup_errors)},
            hint=_("Team-Registrierung und mc_username prüfen"),
        )
    elif registrations:
        _add_check(
            checks,
            check_id="shop_lookup",
            label=_("Shop-Velos-Abfrage"),
            ok=True,
            severity="ok",
            detail=_("Shop würde für alle Teams den DB-Stand liefern"),
        )

    # --- Shop catalog ---
    categories = category_count()
    items = item_count()
    if categories == 0 or items == 0:
        _add_check(
            checks,
            check_id="catalog_items",
            label=_("Shop-Katalog"),
            ok=False,
            severity="error",
            detail=_("%(categories)s Kategorien, %(items)s aktive Artikel") % {
                "categories": categories,
                "items": items,
            },
            hint=_("Shop-Katalog importieren oder anlegen"),
        )
    else:
        _add_check(
            checks,
            check_id="catalog_items",
            label=_("Shop-Katalog"),
            ok=True,
            severity="ok",
            detail=_("%(categories)s Kategorien, %(items)s aktive Artikel") % {
                "categories": categories,
                "items": items,
            },
        )

    incomplete_items = MinecraftShopItem.objects.filter(
        enabled=True,
        category__enabled=True,
    ).filter(esgui_item_loc="").count()
    zero_price_items = MinecraftShopItem.objects.filter(
        enabled=True,
        category__enabled=True,
        buy_price_velos=0,
    ).count()
    if incomplete_items or zero_price_items:
        parts = []
        if incomplete_items:
            parts.append(_("%(count)s ohne esgui_item_loc") % {"count": incomplete_items})
        if zero_price_items:
            parts.append(_("%(count)s mit Preis 0") % {"count": zero_price_items})
        _add_check(
            checks,
            check_id="catalog_complete",
            label=_("Shop-Artikel vollständig"),
            ok=False,
            severity="warning",
            detail="; ".join(str(part) for part in parts),
            hint=_("Artikel im Katalog bearbeiten"),
        )
    elif items > 0:
        _add_check(
            checks,
            check_id="catalog_complete",
            label=_("Shop-Artikel vollständig"),
            ok=True,
            severity="ok",
            detail=_("Alle aktiven Artikel haben Preis und ESGUI-Zuordnung"),
        )

    if items > 0 and ws_enabled and connected_servers:
        _add_check(
            checks,
            check_id="catalog_push",
            label=_("Katalog-Push möglich"),
            ok=True,
            severity="ok",
            detail=_("Shop kann an verbundene Bridge gepusht werden"),
            hint=_("Nach Katalog-Änderungen Shop-Preise pushen"),
            action="push-shop",
        )
    elif items > 0:
        _add_check(
            checks,
            check_id="catalog_push",
            label=_("Katalog-Push möglich"),
            ok=False,
            severity="warning",
            detail=_("Katalog vorhanden, aber Push derzeit nicht möglich"),
            hint=_("WebSocket und MCC-Bridge prüfen, dann Shop pushen"),
            action="push-shop",
        )

    has_errors = any(check.severity == "error" for check in checks)
    return ShopReadinessReport(ok=not has_errors, checks=checks)
