# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Admin for dynamo display settings and battery targets."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from dynamo.models import DynamoBatteryTarget, DynamoDisplaySettings


@admin.register(DynamoDisplaySettings)
class DynamoDisplaySettingsAdmin(admin.ModelAdmin):
    list_display = (
        'update_interval_seconds',
        'power_cap_w',
        'high_power_threshold_w',
        'updated_at',
    )
    fieldsets = (
        (_('Anzeige'), {
            'fields': (
                'update_interval_seconds',
                'high_power_threshold_w',
                'show_cyclist_ride_stats',
                'enable_charger_compare',
            ),
        }),
        (_('Kennlinie'), {
            'fields': (
                'power_cap_w',
                'power_curve',
                'assumed_speed_kmh_for_estimates',
                'charger_efficiency_profiles',
            ),
        }),
        (_('Äquivalente'), {
            'fields': ('appliance_equivalents',),
        }),
    )

    def has_module_permission(self, request):
        return (
            request.user.is_superuser
            or request.user.has_perm('dynamo.view_dynamodisplaysettings')
            or request.user.has_perm('dynamo.manage_dynamo_display')
            or request.user.has_perm('dynamo.change_dynamodisplaysettings')
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.has_perm('dynamo.manage_dynamo_display')
            or request.user.has_perm('dynamo.change_dynamodisplaysettings')
        )

    def has_add_permission(self, request):
        if DynamoDisplaySettings.objects.exists():
            return False
        return self.has_change_permission(request)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(DynamoBatteryTarget)
class DynamoBatteryTargetAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'capacity_wh',
        'icon_key',
        'sort_order',
        'is_active',
        'use_daily_energy',
    )
    list_editable = ('sort_order', 'is_active')
    list_filter = ('is_active', 'icon_key')
    search_fields = ('name',)
    ordering = ('sort_order', 'capacity_wh')

    def has_module_permission(self, request):
        return (
            request.user.is_superuser
            or request.user.has_perm('dynamo.view_dynamobatterytarget')
            or request.user.has_perm('dynamo.manage_dynamo_batteries')
            or request.user.has_perm('dynamo.change_dynamobatterytarget')
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return (
            request.user.is_superuser
            or request.user.has_perm('dynamo.manage_dynamo_batteries')
            or request.user.has_perm('dynamo.add_dynamobatterytarget')
        )

    def has_change_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.has_perm('dynamo.manage_dynamo_batteries')
            or request.user.has_perm('dynamo.change_dynamobatterytarget')
        )

    def has_delete_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.has_perm('dynamo.manage_dynamo_batteries')
            or request.user.has_perm('dynamo.delete_dynamobatterytarget')
        )
