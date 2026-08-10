# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Admin view: redeem Velos from cyclists (full or partial amounts).

from __future__ import annotations

from typing import Optional

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from api.models import Cyclist, Group
from api.services.velos_minecraft_redemption import (
    redeem_velos_for_builder_session,
    redeem_velos_for_player_session,
)
from api.services.velos_redemption import redeem_cyclist_velos
from api.velos import format_velos_de
from eventboard.utils import get_all_subgroup_ids
from minecraft.models import MinecraftIntegrationConfig
from minecraft.services.waitlist_service import duration_from_velos

VELOS_REDEEM_PERMISSION = 'api.redeem_velos'
PRESET_AMOUNTS = (100, 200, 300, 400, 500, 600, 800, 900)
PRODUCT_FREE = 'free'
PRODUCT_PLAYER_SESSION = 'player_session'
PRODUCT_BUILDER_SESSION = 'builder_session'


def user_can_redeem_velos(user) -> bool:
    if not user.is_authenticated or not user.is_staff:
        return False
    return user.is_superuser or user.has_perm(VELOS_REDEEM_PERMISSION)


def get_selectable_top_groups(user):
    """TOP groups the user may filter by when redeeming Velos."""
    if user.is_superuser:
        return Group.objects.filter(parent__isnull=True, is_visible=True).order_by('name')
    managed_top_ids = list(
        user.managed_groups.filter(parent__isnull=True, is_visible=True).values_list('id', flat=True)
    )
    if managed_top_ids:
        return Group.objects.filter(id__in=managed_top_ids).order_by('name')
    from mgmt.admin import get_operator_managed_group_ids

    managed_group_ids = get_operator_managed_group_ids(user)
    if not managed_group_ids:
        return Group.objects.none()
    return Group.objects.filter(
        id__in=managed_group_ids,
        parent__isnull=True,
        is_visible=True,
    ).order_by('name')


def _resolve_top_group(user, top_group_id: Optional[str]) -> Optional[Group]:
    top_groups = get_selectable_top_groups(user)
    if not top_groups.exists():
        return None
    if top_group_id:
        try:
            top_group = top_groups.get(pk=int(top_group_id))
        except (Group.DoesNotExist, ValueError, TypeError):
            return top_groups.first()
        return top_group
    return top_groups.first()


def _find_cyclist_in_top_group(identifier: str, top_group: Group) -> Optional[Cyclist]:
    identifier = (identifier or '').strip()
    if not identifier:
        return None
    group_ids = get_all_subgroup_ids(top_group)
    return (
        Cyclist.objects.filter(
            Q(user_id__iexact=identifier) | Q(id_tag__iexact=identifier),
            groups__id__in=group_ids,
        )
        .distinct()
        .first()
    )


def get_cyclists_for_top_group(top_group: Group):
    """Cyclists belonging to the TOP group tree, ordered for list selection."""
    group_ids = get_all_subgroup_ids(top_group)
    return (
        Cyclist.objects.filter(groups__id__in=group_ids)
        .distinct()
        .prefetch_related('groups')
        .order_by('user_id')
    )


def _resolve_cyclist(
    top_group: Optional[Group],
    cyclist_id: Optional[str] = None,
    identifier: Optional[str] = None,
) -> Optional[Cyclist]:
    if not top_group:
        return None
    group_ids = get_all_subgroup_ids(top_group)
    if cyclist_id:
        try:
            cyclist = (
                Cyclist.objects.filter(pk=int(cyclist_id), groups__id__in=group_ids)
                .distinct()
                .prefetch_related('groups')
                .first()
            )
            if cyclist:
                return cyclist
        except (ValueError, TypeError):
            pass
    return _find_cyclist_in_top_group(identifier or '', top_group)


def _parse_amount(raw_value: str) -> Optional[int]:
    value = (raw_value or '').strip()
    if not value:
        return None
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


@require_http_methods(['GET', 'POST'])
def velos_redeem_view(request):
    if not user_can_redeem_velos(request.user):
        return HttpResponseForbidden(_("Keine Berechtigung für Velos-Einlösung."))

    top_groups = get_selectable_top_groups(request.user)
    top_group = _resolve_top_group(request.user, request.GET.get('top_group') or request.POST.get('top_group'))
    cyclist_id = (request.GET.get('cyclist_id') or request.POST.get('cyclist_id') or '').strip()
    identifier = (request.GET.get('identifier') or request.POST.get('identifier') or '').strip()
    note = (request.POST.get('note') or request.GET.get('note') or '').strip()
    external_currency = (
        request.POST.get('external_currency') or request.GET.get('external_currency') or ''
    ).strip()
    amount_raw = request.POST.get('amount') or request.GET.get('amount') or ''
    product = (
        request.POST.get('product') or request.GET.get('product') or PRODUCT_FREE
    ).strip()
    allowed_products = (PRODUCT_FREE, PRODUCT_PLAYER_SESSION, PRODUCT_BUILDER_SESSION)
    if product not in allowed_products:
        product = PRODUCT_FREE
    mc_config = MinecraftIntegrationConfig.get_config()
    player_min_velos = int(mc_config.player_min_velos or 300)
    player_velos_per_minute = int(mc_config.player_velos_per_minute or 20)
    minutes_for_min_velos = duration_from_velos(player_min_velos, config=mc_config)
    selected_cyclist = None
    cyclists = get_cyclists_for_top_group(top_group) if top_group else Cyclist.objects.none()

    if top_group and (cyclist_id or identifier):
        selected_cyclist = _resolve_cyclist(top_group, cyclist_id=cyclist_id, identifier=identifier)
        if selected_cyclist and not cyclist_id:
            cyclist_id = str(selected_cyclist.pk)
        if selected_cyclist:
            identifier = selected_cyclist.user_id

    if request.method == 'POST' and request.POST.get('action') == 'redeem':
        amount = _parse_amount(amount_raw)
        if not top_group:
            messages.error(request, _("Bitte wählen Sie eine TOP-Gruppe."))
        elif not cyclist_id and not identifier:
            messages.error(request, _("Bitte wählen Sie einen Radler aus der Liste oder geben Sie Name/RFID-Tag ein."))
        elif amount is None:
            messages.error(request, _("Bitte wählen oder geben Sie einen gültigen Velos-Betrag ein."))
        elif not selected_cyclist:
            messages.error(
                request,
                _("Radler nicht gefunden oder gehört nicht zur ausgewählten TOP-Gruppe."),
            )
        else:
            if product == PRODUCT_PLAYER_SESSION:
                result = redeem_velos_for_player_session(
                    selected_cyclist,
                    amount,
                    redeemed_by=request.user,
                    note=note,
                    external_currency=external_currency,
                )
            elif product == PRODUCT_BUILDER_SESSION:
                result = redeem_velos_for_builder_session(
                    selected_cyclist,
                    amount,
                    redeemed_by=request.user,
                    note=note,
                    external_currency=external_currency,
                )
            else:
                result = redeem_cyclist_velos(
                    selected_cyclist,
                    redeemed_by=request.user,
                    note=note,
                    external_currency=external_currency,
                    amount=amount,
                )
            if result.success:
                selected_cyclist.refresh_from_db()
                messages.success(request, result.message)
                identifier = selected_cyclist.user_id
            else:
                messages.warning(request, result.message)

    context = {
        'title': _('Velos einlösen'),
        'top_groups': top_groups,
        'selected_top_group': top_group,
        'cyclist_id': cyclist_id,
        'identifier': identifier,
        'cyclists': cyclists,
        'note': note,
        'external_currency': external_currency,
        'amount_raw': amount_raw,
        'preset_amounts': PRESET_AMOUNTS,
        'product': product,
        'product_free': PRODUCT_FREE,
        'product_player_session': PRODUCT_PLAYER_SESSION,
        'product_builder_session': PRODUCT_BUILDER_SESSION,
        'player_min_velos': player_min_velos,
        'player_velos_per_minute': player_velos_per_minute,
        'minutes_for_min_velos': minutes_for_min_velos,
        'selected_cyclist': selected_cyclist,
        'velos_balance_display': (
            format_velos_de(selected_cyclist.velos_balance) if selected_cyclist else None
        ),
        'history_url': '/admin/api/cyclistvelosredemption/',
    }
    return render(request, 'admin/api/velos_redeem.html', context)


@require_http_methods(['GET'])
def velos_redeem_lookup_api(request):
    """JSON lookup for cyclist balance within a TOP group."""
    if not user_can_redeem_velos(request.user):
        return JsonResponse({'error': str(_("Keine Berechtigung."))}, status=403)

    top_group = _resolve_top_group(request.user, request.GET.get('top_group'))
    identifier = (request.GET.get('identifier') or '').strip()
    if not top_group:
        return JsonResponse({'error': str(_("Keine TOP-Gruppe verfügbar."))}, status=400)
    if not identifier:
        return JsonResponse({'error': str(_("identifier ist erforderlich"))}, status=400)

    cyclist = _resolve_cyclist(top_group, identifier=identifier)
    if not cyclist:
        return JsonResponse({'error': str(_("Radler nicht gefunden."))}, status=404)

    groups = list(cyclist.groups.filter(is_visible=True).order_by('name').values_list('name', flat=True))
    return JsonResponse({
        'cyclist_id': cyclist.id,
        'user_id': cyclist.user_id,
        'id_tag': cyclist.id_tag or '',
        'velos_balance': int(cyclist.velos_balance or 0),
        'velos_balance_display': format_velos_de(cyclist.velos_balance),
        'groups': groups,
    })
