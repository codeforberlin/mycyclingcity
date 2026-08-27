# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin_backup.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Admin UI for MCC remote backup SSH configuration."""

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from mgmt.models_backup import MccBackupConfig
from mgmt.services.backup_config import get_backup_conf_path, write_backup_conf


@admin.register(MccBackupConfig)
class MccBackupConfigAdmin(admin.ModelAdmin):
    list_display = ("ssh_user", "ssh_host", "ssh_port", "remote_backup_dir", "updated_at")
    readonly_fields = ("updated_at", "updated_by", "conf_path_display")
    fieldsets = (
        (
            _("SSH / Remote"),
            {
                "fields": (
                    "ssh_host",
                    "ssh_user",
                    "ssh_port",
                    "ssh_key",
                    "remote_backup_dir",
                    "retention_days",
                )
            },
        ),
        (
            _("Status"),
            {
                "fields": (
                    "conf_path_display",
                    "updated_at",
                    "updated_by",
                )
            },
        ),
    )

    def conf_path_display(self, obj):
        return str(get_backup_conf_path())

    conf_path_display.short_description = _(
        "Conf-Datei (geschrieben bei Speichern; Standard: Datenverzeichnis)"
    )

    def changelist_view(self, request, extra_context=None):
        config_obj = MccBackupConfig.get_config()
        return self.change_view(request, str(config_obj.pk), extra_context)

    def has_add_permission(self, request):
        return not MccBackupConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        try:
            path = write_backup_conf(obj)
            messages.success(
                request,
                _("Konfiguration gespeichert und nach %(path)s geschrieben.")
                % {"path": path},
            )
        except OSError as exc:
            messages.error(
                request,
                _("Speichern ok, aber Conf-Datei konnte nicht geschrieben werden: %(err)s")
                % {"err": exc},
            )
