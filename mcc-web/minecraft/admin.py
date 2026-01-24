from django.contrib import admin
from minecraft.models import (
    MinecraftOutboxEvent,
    MinecraftPlayerScoreboardSnapshot,
    MinecraftWorkerState,
)


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
    list_display = ("player_name", "coins_spendable", "coins_total", "captured_at", "source")
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
