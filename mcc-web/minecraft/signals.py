# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import transaction
from django.db.models.signals import m2m_changed, post_save

from api.models import Cyclist, Group
from config.logger_utils import get_logger
from minecraft.services.outbox import queue_register_team
from minecraft.services.team_registration import (
    deactivate_registration,
    get_active_registration_for_group,
    reactivate_registration,
)


logger = get_logger("minecraft")


def _queue_luckperms_resync_for_group(group: Group, *, reason: str) -> None:
    registration = get_active_registration_for_group(group)
    if not registration:
        return
    queue_register_team(registration.id, reason=reason)
    logger.info(
        "[minecraft_signals] queued luckperms resync group=%s mc=%s reason=%s",
        group.name,
        registration.mc_username,
        reason,
    )


def on_group_pre_delete(sender, instance, **kwargs):
    try:
        registration = instance.minecraft_registration
    except Exception:
        return
    if registration.is_active:
        deactivate_registration(registration, reason="group_deleted")


def on_group_post_save(sender, instance, created, **kwargs):
    if created:
        return

    try:
        registration = instance.minecraft_registration
    except Exception:
        registration = None

    if registration and registration.mc_username != (instance.mc_username or ""):
        old_username = registration.mc_username
        with transaction.atomic():
            if registration.is_active:
                deactivate_registration(registration, reason="mc_username_changed")
            registration.mc_username = instance.mc_username or ""
            registration.is_active = False
            registration.was_ever_registered = False
            registration.save(
                update_fields=["mc_username", "is_active", "was_ever_registered"]
            )
        logger.info(
            "[minecraft_signals] mc_username changed for group=%s old=%s new=%s",
            instance.name,
            old_username,
            instance.mc_username,
        )
        return

    if not registration:
        return

    if not instance.is_visible:
        if registration.is_active:
            deactivate_registration(registration, reason="group_hidden")
        return

    if (
        instance.mc_username
        and registration.was_ever_registered
        and not registration.is_active
    ):
        reactivate_registration(registration)


def on_cyclist_post_save(sender, instance, created, **kwargs):
    if not instance.mc_username:
        return
    for group in instance.groups.filter(is_visible=True):
        _queue_luckperms_resync_for_group(group, reason="cyclist_mc_username_updated")


def on_cyclist_groups_changed(sender, instance, action, pk_set, **kwargs):
    if action not in ("post_add", "post_remove"):
        return
    if not instance.mc_username:
        return
    for group_id in pk_set or []:
        try:
            group = Group.objects.get(pk=group_id, is_visible=True)
        except Group.DoesNotExist:
            continue
        _queue_luckperms_resync_for_group(group, reason="cyclist_group_membership_changed")
