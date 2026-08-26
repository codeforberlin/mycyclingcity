# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.contrib import admin

from luanti.models import (
    LuantiAccount,
    LuantiArenaLane,
    LuantiArenaMotionSettings,
    LuantiBridgeConnection,
    LuantiCityPreset,
    LuantiIntegrationConfig,
    LuantiPendingCommand,
    LuantiPlayerInventory,
    LuantiProtectedRegion,
    LuantiSession,
    LuantiShopCategory,
    LuantiShopItem,
    LuantiShopPurchaseCredit,
    LuantiShopTransaction,
    LuantiStation,
    LuantiWaitingPlayer,
)


@admin.register(LuantiIntegrationConfig)
class LuantiIntegrationConfigAdmin(admin.ModelAdmin):
    list_display = ("pk", "default_session_minutes", "updated_at")

    def has_add_permission(self, request):
        return not LuantiIntegrationConfig.objects.exists()


@admin.register(LuantiBridgeConnection)
class LuantiBridgeConnectionAdmin(admin.ModelAdmin):
    list_display = ("server_id", "is_connected", "connected_at", "last_seen_at")
    readonly_fields = ("server_id", "is_connected", "connected_at", "last_seen_at")


@admin.register(LuantiPendingCommand)
class LuantiPendingCommandAdmin(admin.ModelAdmin):
    list_display = ("id", "server_id", "created_at", "delivered_at")
    readonly_fields = ("server_id", "payload", "created_at", "delivered_at")
    list_filter = ("delivered_at",)


@admin.register(LuantiAccount)
class LuantiAccountAdmin(admin.ModelAdmin):
    list_display = (
        "login_name",
        "id_tag",
        "login_password",
        "password_provisioned",
        "is_active",
        "default_mode",
        "assigned_to_group",
        "active_wallet",
        "wallet_mode",
        "sort_order",
    )
    list_filter = ("is_active", "default_mode", "wallet_mode", "password_provisioned")
    search_fields = ("login_name", "id_tag", "display_name")
    readonly_fields = ("password_last_set_at", "created_at", "updated_at")
    autocomplete_fields = ("assigned_to_group", "active_wallet")


@admin.register(LuantiSession)
class LuantiSessionAdmin(admin.ModelAdmin):
    list_display = ("login_name", "mode", "status", "source", "timestamp_start", "ends_at")
    list_filter = ("status", "mode", "source")
    search_fields = ("login_name",)


@admin.register(LuantiPlayerInventory)
class LuantiPlayerInventoryAdmin(admin.ModelAdmin):
    list_display = ("account", "mode", "revision", "updated_at")
    list_filter = ("mode",)


class LuantiShopItemInline(admin.TabularInline):
    model = LuantiShopItem
    extra = 0


@admin.register(LuantiShopCategory)
class LuantiShopCategoryAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "enabled", "sort_order")
    inlines = [LuantiShopItemInline]


@admin.register(LuantiShopItem)
class LuantiShopItemAdmin(admin.ModelAdmin):
    list_display = ("item_name", "category", "buy_price_velos", "enabled", "sort_order")
    list_filter = ("enabled", "category")


@admin.register(LuantiShopPurchaseCredit)
class LuantiShopPurchaseCreditAdmin(admin.ModelAdmin):
    list_display = ("group", "item_name", "quantity")


@admin.register(LuantiShopTransaction)
class LuantiShopTransactionAdmin(admin.ModelAdmin):
    list_display = ("client_tx_id", "side", "login_name", "item_name", "velos_delta", "created_at")
    list_filter = ("side",)


@admin.register(LuantiCityPreset)
class LuantiCityPresetAdmin(admin.ModelAdmin):
    """Hidden from app index — use custom Preset-Editor GUI instead."""

    list_display = ("slug", "name", "category", "enabled", "is_system", "last_run_at", "last_run_success")
    list_filter = ("category", "enabled", "is_system")
    search_fields = ("slug", "name")

    def has_module_permission(self, request):
        return False


@admin.register(LuantiProtectedRegion)
class LuantiProtectedRegionAdmin(admin.ModelAdmin):
    list_display = ("region_id", "display_name", "world", "protect_build", "enabled")


@admin.register(LuantiArenaMotionSettings)
class LuantiArenaMotionSettingsAdmin(admin.ModelAdmin):
    list_display = ("pk", "enabled", "default_speed", "updated_at")

    def has_add_permission(self, request):
        return not LuantiArenaMotionSettings.objects.exists()


@admin.register(LuantiArenaLane)
class LuantiArenaLaneAdmin(admin.ModelAdmin):
    list_display = ("name", "enabled", "sort_order", "assigned_account")


@admin.register(LuantiStation)
class LuantiStationAdmin(admin.ModelAdmin):
    list_display = ("name", "hostname", "is_active", "default_account", "last_seen_at")
    readonly_fields = ("api_key", "last_seen_at", "reported_config", "last_error")


@admin.register(LuantiWaitingPlayer)
class LuantiWaitingPlayerAdmin(admin.ModelAdmin):
    list_display = ("login_name", "account", "server_id", "first_seen_at", "last_seen_at")
    readonly_fields = ("login_name", "account", "server_id", "first_seen_at", "last_seen_at")
    search_fields = ("login_name",)
