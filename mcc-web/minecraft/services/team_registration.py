# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from api.models import Group
from config.logger_utils import get_logger
from minecraft.models import MinecraftIntegrationConfig, MinecraftTeamRegistration
from minecraft.services.outbox import queue_register_team, queue_team_velos_update, queue_unregister_team


logger = get_logger("minecraft")


def get_objective_spendable() -> str:
    config = MinecraftIntegrationConfig.get_config()
    if config.objective_spendable:
        return config.objective_spendable
    return settings.MCC_MINECRAFT_SCOREBOARD_TEAM_SPENDABLE


def get_display_name() -> str:
    config = MinecraftIntegrationConfig.get_config()
    return config.team_display_name or settings.MCC_MINECRAFT_SCOREBOARD_TEAM_DISPLAY_NAME_DEFAULT


def pending_team_candidates() -> QuerySet[Group]:
    """Visible groups with mc_username that were never registered."""
    return (
        Group.objects.filter(
            is_visible=True,
            mc_username__isnull=False,
        )
        .exclude(mc_username="")
        .filter(
            Q(minecraft_registration__isnull=True)
            | Q(minecraft_registration__was_ever_registered=False)
        )
        .select_related("group_type")
        .order_by("mc_username")
    )


def active_registrations() -> QuerySet[MinecraftTeamRegistration]:
    return (
        MinecraftTeamRegistration.objects.filter(
            is_active=True,
            group__is_visible=True,
        )
        .select_related("group", "group__group_type")
        .order_by("mc_username")
    )


def deactivated_registrations() -> QuerySet[MinecraftTeamRegistration]:
    return (
        MinecraftTeamRegistration.objects.filter(
            was_ever_registered=True,
            is_active=False,
        )
        .select_related("group", "group__group_type")
        .order_by("-deactivated_at", "mc_username")
    )


def get_active_registration_for_group(group: Group) -> MinecraftTeamRegistration | None:
    try:
        registration = group.minecraft_registration
    except MinecraftTeamRegistration.DoesNotExist:
        return None
    if not registration.is_active or not group.is_visible:
        return None
    return registration


def get_active_registration_by_mc_username(mc_username: str) -> MinecraftTeamRegistration | None:
    return (
        MinecraftTeamRegistration.objects.filter(
            mc_username__iexact=mc_username,
            is_active=True,
            group__is_visible=True,
        )
        .select_related("group")
        .first()
    )


def should_sync_group_to_minecraft(group: Group) -> bool:
    if not group.is_visible or not group.mc_username:
        return False
    config = MinecraftIntegrationConfig.get_config()
    if not config.sync_on_earn:
        return False
    return get_active_registration_for_group(group) is not None


@transaction.atomic
def register_group_for_minecraft(group: Group, user=None) -> MinecraftTeamRegistration:
    if not group.mc_username:
        raise ValueError("Group has no mc_username")
    if not group.is_visible:
        raise ValueError("Group is not visible")

    registration, created = MinecraftTeamRegistration.objects.get_or_create(
        group=group,
        defaults={
            "mc_username": group.mc_username,
            "is_active": True,
            "was_ever_registered": True,
            "registered_by": user,
        },
    )
    if not created:
        registration.mc_username = group.mc_username
        registration.is_active = True
        registration.was_ever_registered = True
        registration.deactivated_at = None
        registration.registered_by = user
        registration.save(
            update_fields=[
                "mc_username",
                "is_active",
                "was_ever_registered",
                "deactivated_at",
                "registered_by",
            ]
        )

    queue_register_team(registration.id, reason="manual_register")
    logger.info(
        "[minecraft_registration] registered group=%s mc=%s",
        group.name,
        registration.mc_username,
    )
    return registration


@transaction.atomic
def deactivate_registration(
    registration: MinecraftTeamRegistration,
    *,
    reason: str = "manual_deactivate",
) -> None:
    if not registration.is_active:
        return
    mc_username = registration.mc_username
    registration.is_active = False
    registration.deactivated_at = timezone.now()
    registration.save(update_fields=["is_active", "deactivated_at"])
    queue_unregister_team(mc_username, reason=reason)
    logger.info(
        "[minecraft_registration] deactivated group=%s mc=%s reason=%s",
        registration.group.name,
        mc_username,
        reason,
    )


@transaction.atomic
def reactivate_registration(registration: MinecraftTeamRegistration) -> None:
    group = registration.group
    if not group.is_visible or not group.mc_username:
        raise ValueError("Group is not visible or has no mc_username")

    registration.mc_username = group.mc_username
    registration.is_active = True
    registration.deactivated_at = None
    registration.was_ever_registered = True
    registration.save(
        update_fields=["mc_username", "is_active", "deactivated_at", "was_ever_registered"]
    )
    queue_register_team(registration.id, reason="reactivate")
    logger.info(
        "[minecraft_registration] reactivated group=%s mc=%s",
        group.name,
        registration.mc_username,
    )


def push_team_velos_to_minecraft(
    group: Group,
    *,
    spendable_delta: int | None = None,
    spendable_action: str = "add",
    reason: str = "db_update",
) -> bool:
    if not should_sync_group_to_minecraft(group):
        return False

    registration = group.minecraft_registration
    group.refresh_from_db(fields=["velos_spendable"])
    try:
        queue_team_velos_update(
            player=registration.mc_username,
            velos_spendable=int(group.velos_spendable or 0),
            reason=reason,
            spendable_action=spendable_action,
            spendable_delta=spendable_delta,
        )
        logger.info(
            "[push_team_velos_to_minecraft] queued for group=%s mc=%s",
            group.name,
            registration.mc_username,
        )
        return True
    except Exception as exc:
        logger.error("[push_team_velos_to_minecraft] failed: %s", exc)
        return False
