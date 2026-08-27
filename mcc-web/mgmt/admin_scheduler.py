# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin_scheduler.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Admin UI for data-driven scheduled jobs."""

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from mgmt.models_scheduler import ScheduledJob, ScheduledJobRun
from mgmt.services.job_runner import execute_job


class ScheduledJobRunInline(admin.TabularInline):
    """Recent notable runs (errors / manual / logged successes) — not every tick."""

    model = ScheduledJobRun
    extra = 0
    can_delete = False
    verbose_name_plural = _("Letzte Läufe (Fehler / manuell / geloggte Erfolge)")
    fields = (
        "started_at",
        "finished_at",
        "status",
        "exit_code",
        "trigger",
        "message",
        "triggered_by",
    )
    readonly_fields = fields
    ordering = ("-started_at",)
    show_change_link = True

    def get_queryset(self, request):
        return super().get_queryset(request).order_by("-started_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ScheduledJob)
class ScheduledJobAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "enabled",
        "job_type",
        "schedule_display",
        "last_status",
        "success_count",
        "error_count",
        "last_finished_at",
        "sort_order",
    )
    list_filter = ("enabled", "job_type", "schedule_type", "last_status")
    search_fields = ("name", "slug", "command", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")
    actions = ("enable_jobs", "disable_jobs", "run_jobs_now")
    inlines = [ScheduledJobRunInline]
    readonly_fields = (
        "last_started_at",
        "last_finished_at",
        "last_status",
        "last_message",
        "success_count",
        "error_count",
        "skip_count",
        "updated_at",
        "updated_by",
        "run_now_button",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "slug",
                    "description",
                    "enabled",
                    "sort_order",
                    "run_now_button",
                )
            },
        ),
        (
            _("Ausführung"),
            {
                "fields": (
                    "job_type",
                    "command",
                    "arguments",
                    "working_directory",
                    "timeout_seconds",
                    "allow_overlap",
                    "max_runtime_log_chars",
                    "log_success_runs",
                )
            },
        ),
        (
            _("Zeitplan"),
            {
                "fields": (
                    "schedule_type",
                    "interval_seconds",
                    "cron_expression",
                )
            },
        ),
        (
            _("Letzter Lauf / Zähler"),
            {
                "fields": (
                    "last_started_at",
                    "last_finished_at",
                    "last_status",
                    "last_message",
                    "success_count",
                    "error_count",
                    "skip_count",
                    "updated_at",
                    "updated_by",
                )
            },
        ),
    )

    def schedule_display(self, obj):
        return obj.schedule_summary()

    schedule_display.short_description = _("Zeitplan")

    def run_now_button(self, obj):
        if not obj or not obj.pk:
            return "—"
        url = reverse("admin:mgmt_scheduledjob_run_now", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">{}</a>',
            url,
            _("Jetzt ausführen"),
        )

    run_now_button.short_description = _("Manuell")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/run-now/",
                self.admin_site.admin_view(self.run_now_view),
                name="mgmt_scheduledjob_run_now",
            ),
        ]
        return custom + urls

    def _user_can_run(self, user) -> bool:
        return user.is_superuser or user.has_perm("mgmt.run_scheduledjob")

    def run_now_view(self, request, object_id):
        job = self.get_object(request, object_id)
        if job is None:
            messages.error(request, _("Job nicht gefunden."))
            return HttpResponseRedirect(reverse("admin:mgmt_scheduledjob_changelist"))
        if not self._user_can_run(request.user):
            messages.error(request, _("Keine Berechtigung zum manuellen Starten."))
            return HttpResponseRedirect(
                reverse("admin:mgmt_scheduledjob_change", args=[job.pk])
            )
        result = execute_job(
            job,
            trigger=ScheduledJobRun.TRIGGER_MANUAL,
            user=request.user,
            force=True,
        )
        if result.skipped:
            messages.warning(request, _("Übersprungen: %(msg)s") % {"msg": result.message})
        elif result.status == ScheduledJob.STATUS_OK:
            messages.success(request, _("Job erfolgreich ausgeführt."))
        else:
            messages.error(
                request,
                _("Job beendet mit Status %(status)s: %(msg)s")
                % {"status": result.status, "msg": result.message},
            )
        return HttpResponseRedirect(
            reverse("admin:mgmt_scheduledjob_change", args=[job.pk])
        )

    @admin.action(description=_("Ausgewählte Jobs aktivieren"))
    def enable_jobs(self, request, queryset):
        updated = queryset.update(enabled=True)
        self.message_user(
            request,
            _("%(count)d Job(s) aktiviert.") % {"count": updated},
            messages.SUCCESS,
        )

    @admin.action(description=_("Ausgewählte Jobs deaktivieren"))
    def disable_jobs(self, request, queryset):
        updated = queryset.update(enabled=False)
        self.message_user(
            request,
            _("%(count)d Job(s) deaktiviert.") % {"count": updated},
            messages.SUCCESS,
        )

    @admin.action(description=_("Ausgewählte Jobs jetzt ausführen"))
    def run_jobs_now(self, request, queryset):
        if not self._user_can_run(request.user):
            self.message_user(
                request,
                _("Keine Berechtigung zum manuellen Starten."),
                messages.ERROR,
            )
            return
        ok = 0
        fail = 0
        for job in queryset:
            result = execute_job(
                job,
                trigger=ScheduledJobRun.TRIGGER_MANUAL,
                user=request.user,
                force=True,
            )
            if result.status == ScheduledJob.STATUS_OK:
                ok += 1
            else:
                fail += 1
        self.message_user(
            request,
            _("Manuelle Läufe: %(ok)d OK, %(fail)d nicht OK.")
            % {"ok": ok, "fail": fail},
            messages.SUCCESS if fail == 0 else messages.WARNING,
        )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ScheduledJobRun)
class ScheduledJobRunAdmin(admin.ModelAdmin):
    list_display = (
        "job",
        "started_at",
        "finished_at",
        "status",
        "exit_code",
        "trigger",
        "triggered_by",
    )
    list_filter = ("status", "trigger", "job")
    search_fields = ("job__slug", "job__name", "message", "stdout_excerpt", "stderr_excerpt")
    readonly_fields = (
        "job",
        "started_at",
        "finished_at",
        "status",
        "exit_code",
        "trigger",
        "stdout_excerpt",
        "stderr_excerpt",
        "message",
        "triggered_by",
    )
    ordering = ("-started_at",)
    date_hierarchy = "started_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
