# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models_backup.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Singleton configuration for MCC remote backup (SSH/rsync)."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class MccBackupConfig(models.Model):
    """
    SSH/rsync settings for scripts/backup_mcc.sh.

    Singleton (pk=1). Values are written to the on-disk conf file used by the
    shell script (see MCC_BACKUP_CONF_PATH).
    """

    ssh_host = models.CharField(
        max_length=255,
        default="cbm-srv2",
        verbose_name=_("SSH-Host"),
        help_text=_("Hostname oder IP des Backup-Servers"),
    )
    ssh_user = models.CharField(
        max_length=128,
        default="mccweb",
        verbose_name=_("SSH-Benutzer"),
    )
    ssh_port = models.PositiveIntegerField(
        default=22,
        verbose_name=_("SSH-Port"),
    )
    ssh_key = models.CharField(
        max_length=512,
        blank=True,
        verbose_name=_("SSH-Private-Key"),
        help_text=_("Optionaler Pfad zum Private Key (leer = SSH-Default)"),
    )
    remote_backup_dir = models.CharField(
        max_length=512,
        default="/home/mccweb/backup",
        verbose_name=_("Remote-Backup-Verzeichnis"),
        help_text=_(
            "Zielverzeichnis auf dem Remote-Server "
            "(Unterordner backups/ und media/ werden verwendet)"
        ),
    )
    retention_days = models.PositiveIntegerField(
        default=30,
        verbose_name=_("Lokale Retention (Tage)"),
        help_text=_("Aufbewahrung lokaler DB-Kopien unter /data/var/mcc/backups/database"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Zuletzt aktualisiert"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_mcc_backup_configs",
        verbose_name=_("Aktualisiert von"),
    )

    class Meta:
        verbose_name = _("MCC Backup-Konfiguration")
        verbose_name_plural = _("MCC Backup-Konfiguration")

    def __str__(self):
        return f"MCC Backup: {self.ssh_user}@{self.ssh_host}:{self.ssh_port}"

    @classmethod
    def get_config(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config
