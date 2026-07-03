# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

"""PDF report builder for the analytics dashboard."""

from __future__ import annotations

import base64
import binascii
import re
from io import BytesIO
from typing import Any, Dict, List, Optional

from django.utils.translation import gettext as _

from api.velos import format_velos_de


def _format_km_de(value: float) -> str:
    fixed = f"{float(value):,.2f}"
    parts = fixed.split('.')
    integer_part = parts[0].replace(',', '.')
    decimal_part = parts[1] if len(parts) > 1 else '00'
    return f"{integer_part},{decimal_part}"


def _format_metric(value: float, metric_mode: str, with_unit: bool = False) -> str:
    if metric_mode == 'km':
        text = _format_km_de(value) + (' km' if with_unit else '')
    else:
        text = format_velos_de(int(round(value))) + (' Velos' if with_unit else '')
    return text


def _record_label(holder: Optional[Dict[str, Any]]) -> str:
    if not holder:
        return '–'
    name = holder.get('name') or '–'
    parent = holder.get('parent_group_name')
    if parent:
        return f"{parent} / {name}"
    return name


def _build_ranked_table(
    headers: List[str],
    rows: List[List[str]],
    col_widths: Optional[List[float]] = None,
):
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    data = [headers] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#417690')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return table


def _decode_chart_image(data_url: str) -> Optional[bytes]:
    """Decode a Chart.js data-URL or raw base64 PNG payload."""
    if not data_url or not str(data_url).strip():
        return None
    data = str(data_url).strip()
    if data.startswith('data:'):
        match = re.match(r'data:image/\w+;base64,(.+)', data, re.DOTALL)
        if not match:
            return None
        data = match.group(1)
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error):
        return None
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return raw


def _append_chart_section(story, section_style, png_bytes: Optional[bytes], title: str, max_width):
    from reportlab.lib.units import cm
    from reportlab.platypus import Image as RLImage, Paragraph, Spacer

    if not png_bytes:
        return
    img = RLImage(BytesIO(png_bytes))
    aspect = img.imageHeight / float(img.imageWidth or 1)
    img.drawWidth = max_width
    img.drawHeight = max_width * aspect
    story.append(Paragraph(title, section_style))
    story.append(Spacer(1, 0.2 * cm))
    story.append(img)
    story.append(Spacer(1, 0.4 * cm))


def build_analytics_pdf(
    aggregated: Dict[str, Any],
    meta: Dict[str, Any],
    chart_images: Optional[Dict[str, Optional[bytes]]] = None,
) -> bytes:
    """Build a compact analytics summary PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors

    metric_mode = aggregated.get('metric_mode') or meta.get('metric_mode') or 'velos'
    total_label = _('Gesamtdistanz') if metric_mode == 'km' else _('Gesamt-Velos')
    metric_unit_header = _('km') if metric_mode == 'km' else _('Velos')

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=_('MyCyclingCity Analytics Report'),
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#417690'),
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#444444'),
        spaceAfter=4,
    )
    section_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#417690'),
        spaceBefore=10,
        spaceAfter=6,
    )

    story: List[Any] = []
    story.append(Paragraph(_('MyCyclingCity – Analysebericht'), title_style))
    story.append(Paragraph(
        _('Zeitraum: %(start)s bis %(end)s') % {
            'start': meta.get('start_date', ''),
            'end': meta.get('end_date', ''),
        },
        subtitle_style,
    ))
    story.append(Paragraph(
        _('Erstellt am: %(ts)s') % {
            'ts': meta.get('generated_at_display', ''),
        },
        subtitle_style,
    ))

    filters = meta.get('filters') or []
    if filters:
        story.append(Paragraph(_('Filter: %(filters)s') % {
            'filters': '; '.join(filters),
        }, subtitle_style))
    if meta.get('group_type_label'):
        story.append(Paragraph(
            _('Gruppentabelle: %(level)s') % {'level': meta['group_type_label']},
            subtitle_style,
        ))

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        f"<b>{total_label}:</b> {_format_metric(aggregated.get('total_distance', 0), metric_mode, with_unit=True)}",
        styles['Normal'],
    ))

    chart_images = chart_images or {}
    chart_width = doc.width
    _append_chart_section(
        story,
        section_style,
        chart_images.get('daily'),
        _('Tägliche Auslastung'),
        chart_width,
    )
    _append_chart_section(
        story,
        section_style,
        chart_images.get('hourly'),
        _('Stündliche Auslastung'),
        chart_width,
    )

    record_rows = [
        [_('Tagesrekord'), _record_label(aggregated.get('daily_record_holder')),
         _format_metric(aggregated.get('daily_record_value', 0) or aggregated.get('daily_total', 0), metric_mode, with_unit=True)],
        [_('Wochenrekord'), _record_label(aggregated.get('weekly_record_holder')),
         _format_metric(aggregated.get('weekly_record_value', 0) or aggregated.get('weekly_total', 0), metric_mode, with_unit=True)],
        [_('Monatsrekord'), _record_label(aggregated.get('monthly_record_holder')),
         _format_metric(aggregated.get('monthly_record_value', 0) or aggregated.get('monthly_total', 0), metric_mode, with_unit=True)],
        [_('Jahresrekord'), _record_label(aggregated.get('yearly_record_holder')),
         _format_metric(aggregated.get('yearly_record_value', 0) or aggregated.get('yearly_total', 0), metric_mode, with_unit=True)],
    ]
    record_table = Table(
        [[_('Periode'), _('Rekordhalter'), metric_unit_header]] + record_rows,
        colWidths=[3.2 * cm, 8.5 * cm, 4.5 * cm],
    )
    record_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#417690')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(_('Kalender-Rekorde'), section_style))
    story.append(record_table)

    def _append_top_table(title: str, headers: List[str], items: List[Dict[str, Any]], row_builder):
        story.append(Paragraph(title, section_style))
        if not items:
            story.append(Paragraph(_('Keine Daten für die gewählten Filter.'), styles['Italic']))
            return
        rows = [row_builder(index, item) for index, item in enumerate(items, start=1)]
        story.append(_build_ranked_table(headers, rows))

    _append_top_table(
        _('Top Gruppen'),
        [_('Rang'), _('Gruppe'), _('Typ'), metric_unit_header],
        aggregated.get('top_groups') or [],
        lambda rank, item: [
            str(rank),
            item.get('name') or '–',
            item.get('type') or '',
            _format_metric(item.get('distance', 0), metric_mode),
        ],
    )

    _append_top_table(
        _('Top Radler'),
        [_('Rang'), _('Radler'), _('ID-Tag'), _('Gruppe'), metric_unit_header],
        aggregated.get('top_cyclists') or [],
        lambda rank, item: [
            str(rank),
            item.get('user_id') or '–',
            item.get('id_tag') or '',
            item.get('group') or '',
            _format_metric(item.get('distance', 0), metric_mode),
        ],
    )

    _append_top_table(
        _('Top Geräte'),
        [_('Rang'), _('Gerät'), metric_unit_header],
        aggregated.get('top_devices') or [],
        lambda rank, item: [
            str(rank),
            item.get('name') or '–',
            _format_metric(item.get('distance', 0), metric_mode),
        ],
    )

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
