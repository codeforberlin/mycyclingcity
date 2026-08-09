# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    services.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Aggregation helpers for the dynamo energy GUI."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from django.db.models import Sum
from django.utils import timezone

from api.models import CyclistDeviceCurrentMileage, Group, HourlyMetric
from dynamo.models import DynamoBatteryTarget, DynamoDisplaySettings
from dynamo.physics import estimate_energy_from_distance


def get_descendant_group_ids(root: Group) -> Set[int]:
    """Return root id plus all visible descendant group ids (recursive)."""
    ids: Set[int] = {root.id}
    children = list(
        Group.objects.filter(parent_id=root.id, is_visible=True).values_list('id', flat=True)
    )
    for child_id in children:
        child = Group.objects.filter(pk=child_id).first()
        if child:
            ids.update(get_descendant_group_ids(child))
    return ids


def _collect_leaf_groups(root: Group) -> List[Group]:
    """Visible leaf groups under ``root`` (depth-first, sorted by label)."""
    leaves: List[Group] = []

    def walk(node: Group) -> None:
        children = list(Group.objects.filter(parent_id=node.id, is_visible=True).order_by('name'))
        if not children:
            if node.is_leaf_group():
                leaves.append(node)
            return
        for child in children:
            walk(child)

    walk(root)
    leaves.sort(key=lambda g: (g.get_kiosk_label() or g.name or '').lower())
    return leaves


def build_group_filter_catalog(current: Optional[Group] = None) -> Dict:
    """
    Options for the dynamo GUI group pickers.

    TOP groups are visible roots (parent is null). Each entry lists its leaf
    descendants so the UI can offer TOP and Leaf selection.
    """
    tops = list(
        Group.objects.filter(parent__isnull=True, is_visible=True).order_by('name')
    )
    options = []
    for top in tops:
        leaf_groups = _collect_leaf_groups(top)
        options.append({
            'name': top.name,
            'label': top.get_kiosk_label(),
            'leaves': [
                {
                    'name': leaf.name,
                    'label': leaf.get_kiosk_label(),
                }
                for leaf in leaf_groups
            ],
        })

    current_name = current.name if current else None
    top_name = None
    is_leaf = False
    if current is not None:
        is_leaf = bool(current.is_leaf_group() and current.parent_id)
        top_name = current.top_parent_name

    return {
        'current': current_name,
        'top': top_name,
        'is_leaf': is_leaf,
        'options': options,
    }


def resolve_top_group_filter(group_name: Optional[str]) -> Tuple[Optional[Group], Optional[Set[int]]]:
    """
    Resolve ?group=<name> to a visible group and its descendant id set.

    Works for TOP and leaf groups alike. Returns (group, descendant_ids).
    If group_name is empty, returns (None, None) meaning no filter (all groups).
    """
    if not group_name:
        return None, None
    try:
        group = Group.objects.get(name__iexact=group_name.strip(), is_visible=True)
    except Group.DoesNotExist:
        return None, set()
    return group, get_descendant_group_ids(group)


def _session_in_scope(session: CyclistDeviceCurrentMileage, group_ids: Optional[Set[int]]) -> bool:
    if group_ids is None:
        return True
    if not group_ids:
        return False
    return session.cyclist.groups.filter(id__in=group_ids).exists()


def get_active_sessions(group_ids: Optional[Set[int]] = None, active_seconds: int = 180):
    """Active sessions optionally filtered by group scope."""
    cutoff = timezone.now() - timedelta(seconds=active_seconds)
    qs = (
        CyclistDeviceCurrentMileage.objects
        .select_related('cyclist', 'device')
        .prefetch_related('cyclist__groups')
        .filter(last_activity__gte=cutoff)
        .order_by('-last_power_w', '-last_activity')
    )
    if group_ids is None:
        return list(qs)
    return [s for s in qs if _session_in_scope(s, group_ids)]


def sum_energy_wh(
    group_ids: Optional[Set[int]],
    start,
    end=None,
    *,
    estimate_missing: bool = True,
) -> Decimal:
    """
    Sum HourlyMetric.energy_wh in a time window for groups in scope.

    If estimate_missing is True, rows with energy_wh=0 but distance>0 contribute
    an estimate from distance (legacy data).
    """
    qs = HourlyMetric.objects.filter(timestamp__gte=start)
    if end is not None:
        qs = qs.filter(timestamp__lt=end)
    if group_ids is not None:
        if not group_ids:
            return Decimal('0.00000')
        qs = qs.filter(group_at_time_id__in=group_ids)

    if not estimate_missing:
        total = qs.aggregate(total=Sum('energy_wh'))['total']
        return total or Decimal('0.00000')

    total = Decimal('0.00000')
    settings_obj = DynamoDisplaySettings.get_settings()
    assumed_speed = float(settings_obj.assumed_speed_kmh_for_estimates)
    for row in qs.values('energy_wh', 'distance_km'):
        energy = row['energy_wh'] or Decimal('0')
        if energy > 0:
            total += energy
        elif row['distance_km'] and row['distance_km'] > 0:
            estimated = estimate_energy_from_distance(
                row['distance_km'],
                assumed_speed_kmh=assumed_speed,
            )
            total += Decimal(str(round(estimated, 5)))
    return total


def daily_energy_wh(group_ids: Optional[Set[int]] = None) -> Decimal:
    now = timezone.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return sum_energy_wh(group_ids, start)


def weekly_energy_wh(group_ids: Optional[Set[int]] = None) -> Decimal:
    now = timezone.now()
    start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return sum_energy_wh(group_ids, start)


def yearly_energy_wh(group_ids: Optional[Set[int]] = None) -> Decimal:
    now = timezone.now()
    start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return sum_energy_wh(group_ids, start)


def energy_timeseries(
    group_ids: Optional[Set[int]],
    *,
    days: int = 7,
) -> List[Dict]:
    """Daily energy buckets for the last ``days`` days (inclusive of today)."""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    series = []
    for offset in range(days - 1, -1, -1):
        day_start = today_start - timedelta(days=offset)
        day_end = day_start + timedelta(days=1)
        wh = sum_energy_wh(group_ids, day_start, day_end)
        series.append({
            'date': day_start.date().isoformat(),
            'label': day_start.strftime('%d.%m.'),
            'energy_wh': float(wh),
        })
    return series


def hourly_energy_today(group_ids: Optional[Set[int]] = None) -> List[Dict]:
    """Hourly energy for today (0–23), zeros for hours without data."""
    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    buckets = {h: 0.0 for h in range(24)}

    qs = HourlyMetric.objects.filter(timestamp__gte=day_start, timestamp__lt=day_start + timedelta(days=1))
    if group_ids is not None:
        if not group_ids:
            return [{'hour': h, 'energy_wh': 0.0} for h in range(24)]
        qs = qs.filter(group_at_time_id__in=group_ids)

    settings_obj = DynamoDisplaySettings.get_settings()
    assumed_speed = float(settings_obj.assumed_speed_kmh_for_estimates)
    for row in qs.values('timestamp', 'energy_wh', 'distance_km'):
        hour = timezone.localtime(row['timestamp']).hour
        energy = row['energy_wh'] or Decimal('0')
        if energy <= 0 and row['distance_km'] and row['distance_km'] > 0:
            energy = Decimal(str(round(
                estimate_energy_from_distance(row['distance_km'], assumed_speed_kmh=assumed_speed),
                5,
            )))
        buckets[hour] = buckets.get(hour, 0.0) + float(energy)

    return [{'hour': h, 'energy_wh': buckets[h]} for h in range(24)]


def leaf_group_power_bars(
    sessions: List[CyclistDeviceCurrentMileage],
    group_ids: Optional[Set[int]],
) -> List[Dict]:
    """Aggregate current power and today's Wh by leaf group in scope."""
    leaf_map: Dict[int, Dict] = {}
    for session in sessions:
        leaf = None
        for g in session.cyclist.groups.all():
            if g.is_leaf_group() and (group_ids is None or g.id in group_ids):
                leaf = g
                break
        if leaf is None:
            continue
        entry = leaf_map.setdefault(leaf.id, {
            'group_id': leaf.id,
            'group_name': leaf.name,
            'name': leaf.get_kiosk_label() if hasattr(leaf, 'get_kiosk_label') else leaf.name,
            'color': leaf.color or '#38bdf8',
            'power_w': 0.0,
            'session_energy_wh': 0.0,
            'cyclists': 0,
        })
        entry['power_w'] += float(session.last_power_w or 0)
        entry['session_energy_wh'] += float(session.session_energy_wh or 0)
        entry['cyclists'] += 1

    bars = sorted(leaf_map.values(), key=lambda x: x['power_w'], reverse=True)
    return bars


def battery_progress(total_wh: Decimal) -> List[Dict]:
    """Fill levels for active battery targets given total Wh."""
    targets = DynamoBatteryTarget.objects.filter(is_active=True)
    results = []
    total = float(total_wh or 0)
    for target in targets:
        capacity = float(target.capacity_wh)
        if capacity <= 0:
            continue
        ratio = min(1.0, total / capacity)
        full_count = int(total // capacity) if capacity > 0 else 0
        results.append({
            'id': target.id,
            'name': target.name,
            'capacity_wh': capacity,
            'icon_key': target.icon_key,
            'fill_ratio': ratio,
            'fill_percent': round(ratio * 100, 1),
            'full_count': full_count,
            'remainder_wh': total - (full_count * capacity),
        })
    return results


def appliance_runtimes(total_power_w: float) -> List[Dict]:
    """How long appliances could run at the current group power."""
    settings_obj = DynamoDisplaySettings.get_settings()
    items = settings_obj.appliance_equivalents or []
    results = []
    for item in items:
        watts = float(item.get('watts') or 0)
        if watts <= 0:
            continue
        hours = (total_power_w / watts) if total_power_w > 0 else 0.0
        results.append({
            'key': item.get('key', ''),
            'label': item.get('label', item.get('key', '')),
            'watts': watts,
            'hours': hours,
            'minutes': hours * 60.0,
        })
    return results


def build_live_payload(
    group_name: Optional[str] = None,
    *,
    show_cyclist_ride_stats: Optional[bool] = None,
    charger_profile: Optional[str] = None,
) -> Dict:
    """Full JSON payload for the dynamo live GUI."""
    from api.velos import calculate_session_velos
    from dynamo.physics import (
        CHARGER_PROFILE_DIRECT,
        charger_profile_catalog,
        compare_chargers_at_speed,
        interpolate_power,
        normalize_charger_profile,
        parse_power_curve,
        usable_power_w,
    )

    settings_obj = DynamoDisplaySettings.get_settings()
    filter_group, group_ids = resolve_top_group_filter(group_name)

    if show_cyclist_ride_stats is None:
        show_cyclist_ride_stats = bool(settings_obj.show_cyclist_ride_stats)

    charger_overrides = settings_obj.charger_efficiency_profiles or None
    enable_compare = bool(getattr(settings_obj, 'enable_charger_compare', True))
    selected_charger = normalize_charger_profile(charger_profile)
    if not enable_compare:
        selected_charger = CHARGER_PROFILE_DIRECT

    sessions = get_active_sessions(group_ids)
    total_power = sum(float(s.last_power_w or 0) for s in sessions)
    session_energy = sum((s.session_energy_wh or Decimal('0')) for s in sessions)
    day_energy = daily_energy_wh(group_ids)
    week_energy = weekly_energy_wh(group_ids)
    year_energy = yearly_energy_wh(group_ids)
    max_rpm = max((float(s.last_rpm or 0) for s in sessions), default=0.0)

    high_threshold = float(settings_obj.high_power_threshold_w)
    cyclists = []
    total_usable = 0.0
    speed_weight_sum = 0.0
    speed_power_sum = 0.0
    for s in sessions:
        leaf_name = ''
        for g in s.cyclist.groups.all():
            if g.is_leaf_group():
                leaf_name = g.get_kiosk_label() if hasattr(g, 'get_kiosk_label') else g.name
                break
        power = float(s.last_power_w or 0)
        speed = float(s.last_speed_kmh or 0)
        usable = usable_power_w(
            power,
            speed,
            selected_charger,
            charger_overrides,
        )
        total_usable += usable
        if power > 0:
            speed_weight_sum += power
            speed_power_sum += speed * power
        session_km = float(s.cumulative_mileage or 0)
        session_velos = calculate_session_velos(s.cumulative_mileage or 0, s.device)
        # Rough live estimate only — stored metrics stay dynamo Wh.
        session_usable_wh = float(s.session_energy_wh or 0)
        if selected_charger != CHARGER_PROFILE_DIRECT and speed > 0:
            eta_now = usable / power if power > 0 else 0.0
            session_usable_wh = float(s.session_energy_wh or 0) * eta_now

        cyclists.append({
            'id_tag': s.cyclist.id_tag,
            'user_id': s.cyclist.user_id,
            'group': leaf_name,
            'power_w': round(power, 2),
            'usable_power_w': round(usable, 2),
            'session_energy_wh': float(s.session_energy_wh or 0),
            'session_usable_energy_wh': round(session_usable_wh, 5),
            'session_km': round(session_km, 3),
            'session_velos': int(session_velos),
            'rpm': round(float(s.last_rpm or 0), 1),
            'speed_kmh': round(speed, 1),
            'high_power': power >= high_threshold,
            'device': s.device.display_name or s.device.name,
        })

    mean_speed = (speed_power_sum / speed_weight_sum) if speed_weight_sum > 0 else 12.0
    # Comparison is for ONE hub dynamo at the reference speed (not the group sum),
    # so the numbers stay pedagogically readable.
    dynamo_curve = parse_power_curve(settings_obj.power_curve or [])
    one_dynamo_power_w = interpolate_power(
        mean_speed,
        curve=dynamo_curve,
        power_cap_w=float(settings_obj.power_cap_w or 6.0),
    )
    charger_compare = compare_chargers_at_speed(
        one_dynamo_power_w,
        mean_speed,
        charger_overrides,
    )

    energy_periods = {
        'session': float(session_energy),
        'day': float(day_energy),
        'week': float(week_energy),
        'year': float(year_energy),
    }

    return {
        'filter_group': filter_group.name if filter_group else None,
        'group_filter': build_group_filter_catalog(filter_group),
        'update_interval_seconds': settings_obj.update_interval_seconds,
        'show_cyclist_ride_stats': show_cyclist_ride_stats,
        'enable_charger_compare': enable_compare,
        'charger_profile': selected_charger,
        'charger_profiles': charger_profile_catalog(charger_overrides),
        'charger_compare': {
            'scope': 'single_dynamo',
            'reference_speed_kmh': round(mean_speed, 1),
            'dynamo_power_w': round(one_dynamo_power_w, 2),
            'group_power_w': round(total_power, 2),
            'active_cyclists': len(sessions),
            'rows': charger_compare,
        },
        'totals': {
            'power_w': round(total_power, 2),
            'usable_power_w': round(total_usable, 2),
            'session_energy_wh': float(session_energy),
            'daily_energy_wh': float(day_energy),
            'weekly_energy_wh': float(week_energy),
            'yearly_energy_wh': float(year_energy),
            'active_cyclists': len(sessions),
            'max_rpm': round(max_rpm, 1),
        },
        'energy_periods': energy_periods,
        'cyclists': cyclists,
        # Default batteries for day; client recomputes for other periods from capacities.
        'batteries': battery_progress(day_energy),
        'appliances': appliance_runtimes(
            total_usable if selected_charger != CHARGER_PROFILE_DIRECT else total_power
        ),
        'leaf_groups': leaf_group_power_bars(sessions, group_ids),
        'history': {
            'daily': energy_timeseries(group_ids, days=7),
            'hourly_today': hourly_energy_today(group_ids),
        },
        'high_power_threshold_w': high_threshold,
    }
