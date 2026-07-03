# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Time-series chart data grouped by TOP or leaf groups."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from django.db.models import Count, Sum

from api.models import Group

CHART_DEFAULT_VISIBLE_GROUPS = 5


def _propagate_group_values(
    group_values: Dict[int, float],
    parent_map: Dict[int, Optional[int]],
) -> Dict[int, float]:
    """Roll child group values up to their parents (bottom-up, each child once)."""
    result = dict(group_values)
    processed: Set[int] = set()
    for _ in range(10):
        changed = False
        for group_id in list(result.keys()):
            if group_id in processed:
                continue
            parent_id = parent_map.get(group_id)
            if parent_id:
                result[parent_id] = result.get(parent_id, 0.0) + result[group_id]
                processed.add(group_id)
                changed = True
        if not changed:
            break
    return result


def _group_display_name(group: Group) -> str:
    if group.short_name and str(group.short_name).strip():
        return str(group.short_name).strip()
    return group.name


def build_timeseries_by_group(
    metrics_qs,
    *,
    period_annotation: Dict[str, Any],
    period_key: str,
    period_label_fmt: Callable[[datetime], str],
    group_type: str,
    metric_field: str,
    sum_output_field,
) -> Dict[str, Any]:
    """Aggregate HourlyMetric rows into chart-ready group time series."""
    rows = (
        metrics_qs.filter(group_at_time__isnull=False)
        .annotate(**period_annotation)
        .values(period_key, 'group_at_time_id')
        .annotate(total=Sum(metric_field, output_field=sum_output_field))
        .order_by(period_key)
    )

    raw_by_period: Dict[str, Dict[int, float]] = defaultdict(dict)
    period_dt_by_label: Dict[str, datetime] = {}

    for row in rows:
        period_dt = row.get(period_key)
        if not period_dt:
            continue
        label = period_label_fmt(period_dt)
        period_dt_by_label[label] = period_dt
        group_id = row.get('group_at_time_id')
        if group_id:
            raw_by_period[label][group_id] = float(row.get('total') or 0)

    if not raw_by_period:
        return {
            'labels': [],
            'total': [],
            'groups': [],
            'default_visible_group_ids': [],
        }

    labels = sorted(raw_by_period.keys(), key=lambda lbl: period_dt_by_label[lbl])

    visible_groups = list(
        Group.objects.filter(is_visible=True).annotate(
            _child_count=Count('children'),
        ).select_related('group_type')
    )
    parent_map = {g.id: g.parent_id for g in visible_groups}
    top_ids = {g.id for g in visible_groups if g.parent_id is None}
    leaf_ids = {g.id for g in visible_groups if g._child_count == 0}
    groups_by_id = {g.id: g for g in visible_groups}

    period_values_by_group: Dict[int, Dict[str, float]] = defaultdict(dict)
    total_by_label: Dict[str, float] = {}

    for label in labels:
        raw_values = raw_by_period[label]
        propagated = _propagate_group_values(raw_values, parent_map)
        total_by_label[label] = sum(propagated.get(gid, 0.0) for gid in top_ids)

        if group_type == 'top_groups':
            target_ids = top_ids
            source = propagated
        else:
            target_ids = leaf_ids
            source = raw_values

        for group_id in target_ids:
            value = source.get(group_id, 0.0)
            if value:
                period_values_by_group[group_id][label] = value

    group_totals: List[tuple[int, float]] = []
    for group_id, per_label in period_values_by_group.items():
        group_totals.append((group_id, sum(per_label.values())))
    group_totals.sort(key=lambda item: item[1], reverse=True)

    groups_payload = []
    for group_id, _total in group_totals:
        group = groups_by_id.get(group_id)
        if not group:
            continue
        groups_payload.append({
            'id': group_id,
            'name': _group_display_name(group),
            'type': group.group_type.name if group.group_type else '',
            'data': [period_values_by_group[group_id].get(label, 0.0) for label in labels],
        })

    default_visible = [g['id'] for g in groups_payload[:CHART_DEFAULT_VISIBLE_GROUPS]]

    return {
        'labels': labels,
        'total': [total_by_label.get(label, 0.0) for label in labels],
        'groups': groups_payload,
        'default_visible_group_ids': default_visible,
    }
