# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from typing import Any

from django.utils.html import escape, format_html
from django.utils.translation import gettext as _

from luanti.models import LuantiAccount, LuantiPlayerInventory

INVENTORY_MODES = (
    LuantiAccount.MODE_PLAY,
    LuantiAccount.MODE_PLAN,
    LuantiAccount.MODE_BUILD,
)

MAX_INVENTORY_ROWS = 64
MAX_STACK_COUNT = 64

INVENTORY_ERROR_MESSAGES = {
    "invalid_mode": _("Ungültiger Inventar-Modus."),
    "invalid_item_name": _("Item-Name muss das Formular namespace:name haben."),
    "invalid_count": _("Menge muss zwischen 1 und 64 liegen."),
    "invalid_slot": _("Slot muss zwischen 1 und 64 liegen."),
    "invalid_wear": _("Verschleiß (wear) ist ungültig."),
    "too_many_rows": _("Zu viele Zeilen (max. 64)."),
    "duplicate_slot": _("Jeder Slot darf nur einmal vorkommen."),
}


class InventoryAdminError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or INVENTORY_ERROR_MESSAGES.get(code, code))


def normalize_mode(mode: str) -> str:
    mode = (mode or "").strip().lower()
    if mode not in INVENTORY_MODES:
        raise InventoryAdminError("invalid_mode")
    return mode


def inventory_item_count(payload: list | None) -> int:
    if not isinstance(payload, list):
        return 0
    return sum(
        1 for row in payload if isinstance(row, dict) and (row.get("name") or "").strip()
    )


def inventory_rows_for_display(payload: list | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(payload, list):
        return rows
    for row in payload:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
        is_plan = str(meta.get("mcc_plan") or "") == "1"
        rows.append(
            {
                "slot": row.get("slot"),
                "name": name,
                "count": int(row.get("count") or 1),
                "wear": row.get("wear"),
                "is_plan": is_plan,
                "meta_target": str(meta.get("mcc_target_name") or ""),
            }
        )
    return rows


def editor_rows_from_payload(payload: list | None) -> list[dict[str, Any]]:
    """Rows for the tabular editor (includes wear as string)."""
    rows = []
    for row in inventory_rows_for_display(payload):
        wear = row.get("wear")
        rows.append(
            {
                "slot": row.get("slot") or "",
                "name": row["name"],
                "count": row["count"],
                "wear": wear if wear is not None else "",
            }
        )
    if not rows:
        rows.append({"slot": 1, "name": "", "count": 1, "wear": ""})
    return rows


def _meta_key(row: dict) -> tuple:
    return (
        int(row.get("slot") or 0),
        str(row.get("name") or "").strip(),
    )


def merge_inventory_meta(old_payload: list | None, new_payload: list) -> list:
    """Preserve plan meta when slot+name unchanged."""
    old_map: dict[tuple, dict] = {}
    if isinstance(old_payload, list):
        for row in old_payload:
            if isinstance(row, dict) and row.get("name"):
                old_map[_meta_key(row)] = (
                    row.get("meta") if isinstance(row.get("meta"), dict) else {}
                )
    out: list[dict] = []
    for row in new_payload:
        entry = dict(row)
        key = _meta_key(entry)
        if key in old_map and old_map[key]:
            entry["meta"] = dict(old_map[key])
        out.append(entry)
    return out


def parse_inventory_post(post) -> list[dict]:
    indices: set[int] = set()
    for key in post:
        if not key.startswith("row-") or not key.endswith("-name"):
            continue
        mid = key[4:-5]
        try:
            indices.add(int(mid))
        except ValueError:
            continue
    rows: list[dict] = []
    for idx in sorted(indices):
        name = str(post.get(f"row-{idx}-name") or "").strip()
        if not name:
            continue
        if ":" not in name:
            raise InventoryAdminError("invalid_item_name")
        try:
            count = int(post.get(f"row-{idx}-count") or 1)
        except (TypeError, ValueError):
            raise InventoryAdminError("invalid_count")
        if count < 1 or count > MAX_STACK_COUNT:
            raise InventoryAdminError("invalid_count")
        try:
            slot = int(post.get(f"row-{idx}-slot") or (idx + 1))
        except (TypeError, ValueError):
            slot = idx + 1
        if slot < 1 or slot > MAX_INVENTORY_ROWS:
            raise InventoryAdminError("invalid_slot")
        wear_raw = post.get(f"row-{idx}-wear")
        row: dict[str, Any] = {"slot": slot, "name": name, "count": count}
        if wear_raw not in (None, ""):
            try:
                row["wear"] = int(wear_raw)
            except (TypeError, ValueError):
                raise InventoryAdminError("invalid_wear")
        rows.append(row)
    if len(rows) > MAX_INVENTORY_ROWS:
        raise InventoryAdminError("too_many_rows")
    slots = [int(r.get("slot") or 0) for r in rows]
    if len(set(slots)) != len(slots):
        raise InventoryAdminError("duplicate_slot")
    return rows


def format_shop_credit_admin_label(hint: dict) -> str:
    if not isinstance(hint, dict):
        return "—"
    if hint.get("sellable"):
        group = str(hint.get("credit_group_name") or hint.get("wallet_group_name") or "?")
        qty = int(hint.get("credit_available") or 0)
        price = int(hint.get("buy_price_velos") or 0)
        if price > 0:
            return _(
                "Gruppe %(group)s · %(qty)s Kaufguthaben · %(price)s Velos/Stück"
            ) % {"group": group, "qty": qty, "price": price}
        return _("Gruppe %(group)s · %(qty)s Kaufguthaben") % {"group": group, "qty": qty}
    if hint.get("reason") == "other_group" and hint.get("credit_group_name"):
        return _("Guthaben bei Gruppe %(group)s (nicht über aktuelle Wallet)") % {
            "group": hint["credit_group_name"],
        }
    if hint.get("shop_item_name") or hint.get("reason") == "no_credit":
        wallet = str(hint.get("wallet_group_name") or "—")
        return _("Kein verkaufbares Kaufguthaben (Wallet: %(wallet)s)") % {"wallet": wallet}
    if hint.get("reason") == "not_in_shop":
        return _("Kein Shop-Artikel")
    return "—"


def shop_credit_labels_for_account(
    account: LuantiAccount | None, item_names: list[str]
) -> dict[str, str]:
    if account is None:
        return {}
    from luanti.services.shop import sell_hint_for_inventory_name

    labels: dict[str, str] = {}
    seen: set[str] = set()
    for raw in item_names:
        name = str(raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        labels[name] = format_shop_credit_admin_label(
            sell_hint_for_inventory_name(login_name=account.login_name, inventory_name=name)
        )
    return labels


def format_inventory_table_html(
    payload: list | None, account: LuantiAccount | None = None
) -> str:
    rows = inventory_rows_for_display(payload)
    if not rows:
        return format_html("<p class=\"help\">{}</p>", _("Keine Items gespeichert."))
    credit_labels = shop_credit_labels_for_account(account, [r["name"] for r in rows])
    show_shop_col = account is not None
    parts = [
        '<table class="mcc-inv-table" style="width:100%;border-collapse:collapse;font-size:13px;">',
        "<thead><tr>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #ccc;\">{escape(_('Slot'))}</th>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #ccc;\">{escape(_('Item'))}</th>"
        f"<th style=\"text-align:right;padding:4px 8px;border-bottom:1px solid #ccc;\">{escape(_('Menge'))}</th>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #ccc;\">{escape(_('Plan'))}</th>",
    ]
    if show_shop_col:
        parts.append(
            f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #ccc;\">"
            f"{escape(_('Shop-Guthaben'))}</th>"
        )
    parts.append("</tr></thead><tbody>")
    for row in rows:
        plan_cell = _("ja") if row["is_plan"] else "—"
        parts.append(
            "<tr>"
            f"<td style=\"padding:4px 8px;border-bottom:1px solid #eee;\">{escape(str(row['slot'] or '—'))}</td>"
            f"<td style=\"padding:4px 8px;border-bottom:1px solid #eee;\"><code>{escape(row['name'])}</code></td>"
            f"<td style=\"padding:4px 8px;border-bottom:1px solid #eee;text-align:right;\">{row['count']}</td>"
            f"<td style=\"padding:4px 8px;border-bottom:1px solid #eee;\">{escape(plan_cell)}</td>"
        )
        if show_shop_col:
            credit_cell = credit_labels.get(row["name"], "—")
            parts.append(
                f"<td style=\"padding:4px 8px;border-bottom:1px solid #eee;\">{escape(credit_cell)}</td>"
            )
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return format_html("".join(parts))


def inventory_summaries_for_account(account: LuantiAccount) -> list[dict]:
    summaries = []
    labels = dict(LuantiPlayerInventory._meta.get_field("mode").choices)
    for mode in INVENTORY_MODES:
        inv = LuantiPlayerInventory.objects.filter(account=account, mode=mode).first()
        count = inventory_item_count(inv.payload if inv else None)
        summaries.append(
            {
                "mode": mode,
                "mode_label": str(labels.get(mode, mode)),
                "item_count": count,
                "revision": int(inv.revision) if inv else 0,
                "updated_at": inv.updated_at if inv else None,
            }
        )
    return summaries


def save_player_inventory(
    inv: LuantiPlayerInventory,
    rows: list[dict],
    *,
    push_live: bool = True,
) -> tuple[LuantiPlayerInventory, bool]:
    from luanti.services.session_control import push_account_inventory

    merged = merge_inventory_meta(inv.payload, rows)
    inv.payload = merged
    inv.revision = int(inv.revision or 0) + 1
    inv.save(update_fields=["payload", "revision", "updated_at"])
    pushed = push_account_inventory(inv) if push_live else False
    return inv, pushed


def live_push_status_message(pushed: bool, inv: LuantiPlayerInventory) -> str:
    if pushed:
        return _("Gespeichert und live an den verbundenen Spieler übertragen.")
    from luanti.services.session_control import get_active_session

    session = get_active_session(inv.account.login_name)
    if not session:
        return _("Gespeichert (keine offene Session — nur Datenbank).")
    if session.is_paused:
        return _("Gespeichert (Session pausiert — nur Datenbank).")
    if session.mode != inv.mode:
        return _("Gespeichert (aktueller Session-Modus weicht ab — nur Datenbank).")
    return _("Gespeichert (Spieler nicht online — nur Datenbank).")