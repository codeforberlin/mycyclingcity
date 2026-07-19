from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from minecraft.models import (
    MinecraftIntegrationConfig,
    MinecraftOutboxEvent,
    MinecraftPlayerScoreboardSnapshot,
    MinecraftRconPreset,
    MinecraftShopCategory,
    MinecraftShopItem,
    MinecraftTeamRegistration,
    MinecraftWorkerState,
)


@admin.register(MinecraftIntegrationConfig)
class MinecraftIntegrationConfigAdmin(admin.ModelAdmin):
    list_display = (
        "team_display_name",
        "objective_spendable",
        "sidebar_enabled",
        "sync_on_earn",
        "updated_at",
        "updated_by",
    )
    readonly_fields = ("updated_at", "updated_by")

    def has_add_permission(self, request):
        return not MinecraftIntegrationConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MinecraftTeamRegistration)
class MinecraftTeamRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "mc_username",
        "group",
        "is_active",
        "was_ever_registered",
        "registered_at",
        "last_synced_at",
    )
    list_filter = ("is_active", "was_ever_registered")
    search_fields = ("mc_username", "group__name")
    readonly_fields = ("registered_at", "deactivated_at", "last_synced_at", "last_sync_error")


@admin.register(MinecraftOutboxEvent)
class MinecraftOutboxEventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "status", "attempts", "created_at", "processed_at")
    list_filter = ("event_type", "status", "created_at")
    search_fields = ("payload", "last_error")
    readonly_fields = ("created_at", "processed_at", "attempts")

    def has_add_permission(self, request):
        return False


@admin.register(MinecraftPlayerScoreboardSnapshot)
class MinecraftPlayerScoreboardSnapshotAdmin(admin.ModelAdmin):
    list_display = ("player_name", "group", "velos_spendable", "velos_total", "captured_at", "source")
    list_filter = ("source",)
    search_fields = ("player_name",)
    readonly_fields = ("captured_at",)


@admin.register(MinecraftWorkerState)
class MinecraftWorkerStateAdmin(admin.ModelAdmin):
    list_display = ("is_running", "pid", "started_at", "last_heartbeat", "last_error")
    readonly_fields = ("is_running", "pid", "started_at", "last_heartbeat", "last_error")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class MinecraftShopItemInline(admin.TabularInline):
    model = MinecraftShopItem
    extra = 1
    fields = (
        "esgui_item_key",
        "esgui_item_loc",
        "material",
        "display_name",
        "buy_price_velos",
        "stack_size",
        "sort_order",
        "enabled",
    )


@admin.register(MinecraftShopCategory)
class MinecraftShopCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "esgui_section", "sort_order", "enabled")
    list_filter = ("enabled",)
    search_fields = ("name", "slug", "esgui_section")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MinecraftShopItemInline]


@admin.register(MinecraftRconPreset)
class MinecraftRconPresetAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "category",
        "command_count_display",
        "sort_order",
        "enabled",
        "is_system",
        "last_run_at",
    )
    list_filter = ("category", "enabled", "is_system")
    search_fields = ("name", "slug", "description")
    readonly_fields = (
        "last_run_at",
        "last_run_by",
        "last_run_success",
        "last_run_output",
    )
    ordering = ("category", "sort_order", "name")

    @admin.display(description=_("Befehle"))
    def command_count_display(self, obj):
        return obj.command_count

    def has_module_permission(self, request):
        return False


@admin.register(MinecraftShopItem)
class MinecraftShopItemAdmin(admin.ModelAdmin):
    list_display = (
        "esgui_item_key",
        "material",
        "display_name",
        "category",
        "buy_price_velos",
        "esgui_item_loc",
        "sort_order",
        "enabled",
    )
    list_filter = ("enabled", "category")
    search_fields = (
        "material",
        "display_name",
        "esgui_item_key",
        "esgui_item_loc",
        "category__name",
        "category__slug",
        "category__esgui_section",
    )
    search_help_text = _(
        "Suche in allen Shop-Artikeln: Material, Anzeigename, Item-Key, "
        "Item-Loc oder Kategoriename."
    )
    list_per_page = 50
    show_full_result_count = True
    ordering = ("category__sort_order", "category__name", "sort_order", "material")
