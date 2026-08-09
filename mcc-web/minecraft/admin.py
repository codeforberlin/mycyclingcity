from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from minecraft.models import (
    MCSession,
    MinecraftArenaLane,
    MinecraftArenaMotionSettings,
    MinecraftBuilderAccount,
    MinecraftIntegrationConfig,
    MinecraftOutboxEvent,
    MinecraftPlayAccount,
    MinecraftPlayerScoreboardSnapshot,
    MinecraftRconPreset,
    MinecraftShopCategory,
    MinecraftShopItem,
    MinecraftShopPurchaseCredit,
    MinecraftTeamRegistration,
    MinecraftWorkerState,
)
from minecraft.services.builder_account_provision import register_builder_account_on_minecraft
from minecraft.services.play_account_provision import register_play_account_on_minecraft
from minecraft.services.preset_permissions import (
    user_can_manage_builder_sessions,
)
from minecraft.services.bridge_team_mapping import push_player_override_to_bridge
from minecraft.services.session_control import RconSequenceError, SessionControlError
from django.conf import settings as django_settings


@admin.register(MinecraftIntegrationConfig)
class MinecraftIntegrationConfigAdmin(admin.ModelAdmin):
    list_display = (
        "team_display_name",
        "objective_spendable",
        "sidebar_enabled",
        "sync_on_earn",
        "waitlist_public_enabled",
        "player_session_active_hint",
        "builder_session_active_hint",
        "updated_at",
        "updated_by",
    )
    readonly_fields = ("updated_at", "updated_by")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "team_display_name",
                    "objective_spendable",
                    "sync_on_earn",
                    "sidebar_enabled",
                ),
            },
        ),
        (
            _("Spieler-Sessions"),
            {
                "fields": ("player_session_active_hint",),
            },
        ),
        (
            _("Bau-Sessions"),
            {
                "fields": ("builder_session_active_hint",),
            },
        ),
        (
            _("Proxy / Presence"),
            {
                "fields": (
                    "proxy_presence_poll_seconds",
                    "session_login_wait_seconds",
                ),
                "description": _(
                    "Velocity-RCON-Abfragen der Session-Dashboards und "
                    "Wartezeit nach Session-Freigabe (bis Spieler auf Paper online)."
                ),
            },
        ),
        (
            _("Auth-Failover"),
            {
                "fields": (
                    "auth_ops_mode",
                    "auth_failover_at",
                    "auth_failback_at",
                    "auth_last_snapshot_dir",
                ),
                "description": _(
                    "Betriebsmodus für Microsoft-Auth-Failover. "
                    "Playerdata-Migrationen über die Auth-Failover-Admin-Seite."
                ),
            },
        ),
        (
            _("World Border"),
            {
                "fields": (
                    "world_border_enabled",
                    "world_border_center_x",
                    "world_border_center_z",
                    "world_border_size",
                    "world_border_warning_distance",
                    "world_border_damage_amount",
                ),
                "description": _(
                    "Quadratischer Spielbereich (Vanilla worldborder). "
                    "Primär über Stadtsteuerung anwenden; Werte hier speichern."
                ),
            },
        ),
        (
            _("Warteliste"),
            {
                "fields": (
                    "waitlist_public_enabled",
                    "waitlist_public_token",
                    "player_velos_per_minute",
                    "player_min_velos",
                ),
            },
        ),
        (
            _("Velo-Arena"),
            {
                "fields": ("arena_default_time_limit_minutes",),
                "description": _(
                    "Default-Zeitlimit für Velo-Rennen (Arena-Steuerung / Simulation). "
                    "Operatoren können den Wert pro Rennen weiter anpassen, sofern der Browser das zulässt."
                ),
            },
        ),
        (
            _("Metadaten"),
            {
                "fields": ("updated_at", "updated_by"),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        if "arena_default_time_limit_minutes" in form.changed_data:
            try:
                from minecraft.services.arena_motion.control import (
                    apply_integration_default_time_limit,
                )

                apply_integration_default_time_limit(obj.arena_default_time_limit_minutes)
            except Exception:
                # Arena state is optional; Integration save must still succeed.
                pass

    def has_add_permission(self, request):
        return not MinecraftIntegrationConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MinecraftPlayAccount)
class MinecraftPlayAccountAdmin(admin.ModelAdmin):
    list_display = (
        "short_name",
        "ms_username",
        "id_tag",
        "display_name",
        "session_duration_minutes",
        "add_time_minutes",
        "is_active",
        "sort_order",
        "updated_at",
    )
    list_display_links = ("short_name",)
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("short_name", "ms_username", "id_tag", "display_name")
    ordering = ("sort_order", "short_name")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id_tag",
                    "short_name",
                    "display_name",
                    "is_active",
                    "sort_order",
                ),
                "description": _(
                    "„Aktiv“ steuert die Sichtbarkeit in Spieler-Sessions, Warteliste und API. "
                    "Deaktivierte Accounts bleiben erhalten und können jederzeit wieder eingeschaltet werden."
                ),
            },
        ),
        (
            _("Microsoft / Online"),
            {
                "fields": ("ms_username", "ms_uuid"),
                "description": _(
                    "Microsoft-Gamertag für Velocity online-mode. "
                    "Inventar/Shop hängen an der UUID. "
                    "Bei wenigen Spiel-PCs Stations-Accounts (z. B. mccpc01) bevorzugen."
                ),
            },
        ),
        (
            _("Session"),
            {
                "fields": (
                    "session_duration_minutes",
                    "add_time_minutes",
                    "prefer_gamemode",
                    "prefer_spectator",
                ),
            },
        ),
        (
            _("AuthMe (Legacy)"),
            {
                "classes": ("collapse",),
                "fields": (
                    "authme_is_registered",
                    "authme_registered_at",
                    "authme_last_error",
                ),
            },
        ),
        (
            _("Metadaten"),
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "authme_is_registered",
        "authme_registered_at",
        "authme_last_error",
    )
    actions = ("register_on_minecraft_server",)

    def has_module_permission(self, request):
        return False

    @admin.action(description=_("Auf Minecraft-Server anlegen (AuthMe register, Legacy)"))
    def register_on_minecraft_server(self, request, queryset):
        if (getattr(django_settings, "MCC_MINECRAFT_SESSION_AUTH_MODE", "online") or "").lower() != "authme":
            self.message_user(
                request,
                _(
                    "AuthMe-Registrierung ist im Online-Modus deaktiviert "
                    "(MCC_MINECRAFT_SESSION_AUTH_MODE=online). Bitte Microsoft-Login setzen."
                ),
                level=messages.WARNING,
            )
            return
        ok_count = 0
        fail_count = 0
        for account in queryset:
            try:
                register_play_account_on_minecraft(account)
                ok_count += 1
            except SessionControlError as exc:
                fail_count += 1
                self.message_user(
                    request,
                    _("%(name)s: %(error)s")
                    % {"name": account.short_name, "error": str(exc)},
                    level=messages.ERROR,
                )
            except RconSequenceError as exc:
                fail_count += 1
                self.message_user(
                    request,
                    _("%(name)s: RCON/AuthMe-Fehler — %(error)s")
                    % {"name": account.short_name, "error": str(exc)[:300]},
                    level=messages.ERROR,
                )
        if ok_count:
            self.message_user(
                request,
                _("%(n)s Play-Account(s) auf dem Minecraft-Server angelegt bzw. bestätigt.")
                % {"n": ok_count},
                level=messages.SUCCESS,
            )
        if fail_count and not ok_count:
            self.message_user(
                request,
                _(
                    "Keine Accounts angelegt. Passwort in .env setzen? "
                    "(MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD)"
                ),
                level=messages.WARNING,
            )


@admin.register(MCSession)
class MCSessionAdmin(admin.ModelAdmin):
    list_display = (
        "account_name",
        "account_type",
        "status",
        "duration_minutes",
        "timestamp_start",
        "ends_at",
        "timestamp_end",
        "source",
        "started_by",
    )
    list_filter = ("account_type", "status", "source")
    search_fields = ("account_name",)
    readonly_fields = (
        "session_id",
        "account_name",
        "account_type",
        "timestamp_start",
        "duration_minutes",
        "ends_at",
        "timestamp_end",
        "status",
        "source",
        "started_by",
        "last_error",
    )
    ordering = ("-timestamp_start",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MinecraftTeamRegistration)
class MinecraftTeamRegistrationAdmin(admin.ModelAdmin):
    """Full registration records — hidden from sidebar; use Control + Bau-Accounts."""

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

    def has_module_permission(self, request):
        return False


@admin.register(MinecraftBuilderAccount)
class MinecraftBuilderAccountAdmin(admin.ModelAdmin):
    """Session settings for builder registrations (registration stays in Control)."""

    list_display = (
        "mc_username",
        "ms_username",
        "group",
        "is_active",
        "session_duration_minutes",
        "add_time_minutes",
        "registered_at",
    )
    list_display_links = ("mc_username",)
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("mc_username", "ms_username", "group__name")
    ordering = ("-is_active", "mc_username")
    readonly_fields = (
        "group",
        "mc_username",
        "registered_at",
        "registered_by",
        "last_synced_at",
        "last_sync_error",
        "authme_is_registered",
        "authme_registered_at",
        "authme_last_error",
    )
    actions = ("push_bridge_player_override", "register_on_minecraft_server")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "mc_username",
                    "group",
                    "is_active",
                    "session_duration_minutes",
                    "add_time_minutes",
                    "prefer_gamemode",
                    "prefer_spectator",
                ),
                "description": _(
                    "„Aktiv“ steuert die Sichtbarkeit in Bau-Sessions und Warteliste. "
                    "Scoreboard-Name bleibt mc_username (z. B. Kette). "
                    "Deaktivierte Bau-PCs bleiben erhalten und können jederzeit wieder eingeschaltet werden."
                ),
            },
        ),
        (
            _("Microsoft / Online"),
            {
                "fields": ("ms_username", "ms_uuid"),
                "description": _(
                    "Microsoft-Gamertag am Velocity-Proxy (z. B. mccpc01). "
                    "Shop-Inventar hängt an der UUID. "
                    "Bei wenigen Spiel-PCs Stations-Accounts bevorzugen (wenig OTP-Wechsel)."
                ),
            },
        ),
        (
            _("AuthMe (Legacy)"),
            {
                "classes": ("collapse",),
                "fields": (
                    "authme_is_registered",
                    "authme_registered_at",
                    "authme_last_error",
                ),
            },
        ),
        (
            _("Sync / Metadaten"),
            {
                "fields": (
                    "registered_at",
                    "registered_by",
                    "last_synced_at",
                    "last_sync_error",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        obj.ms_username = (obj.ms_username or "").strip()
        obj.ms_uuid = (obj.ms_uuid or "").strip()
        super().save_model(request, obj, form, change)
        if obj.ms_username and obj.is_active:
            sent = push_player_override_to_bridge(obj.ms_username, obj.mc_username)
            if sent:
                self.message_user(
                    request,
                    _("Bridge-Override gepusht: %(ms)s → %(mc)s")
                    % {"ms": obj.ms_username, "mc": obj.mc_username},
                    level=messages.SUCCESS,
                )

    @admin.action(description=_("Bridge-Override pushen (MS-Login → Scoreboard)"))
    def push_bridge_player_override(self, request, queryset):
        sent_total = 0
        for registration in queryset:
            ms = (registration.ms_username or "").strip()
            if not ms:
                self.message_user(
                    request,
                    _("%(name)s: kein Microsoft-Login gesetzt")
                    % {"name": registration.mc_username},
                    level=messages.WARNING,
                )
                continue
            sent_total += push_player_override_to_bridge(ms, registration.mc_username)
        if sent_total:
            self.message_user(
                request,
                _("%(n)s Override(s) an die Bridge gesendet.") % {"n": sent_total},
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _("Kein Override gesendet (Bridge offline oder kein MS-Login)."),
                level=messages.WARNING,
            )

    @admin.action(description=_("Auf Minecraft-Server anlegen (AuthMe register, Legacy)"))
    def register_on_minecraft_server(self, request, queryset):
        if (getattr(django_settings, "MCC_MINECRAFT_SESSION_AUTH_MODE", "online") or "").lower() != "authme":
            self.message_user(
                request,
                _(
                    "AuthMe-Registrierung ist im Online-Modus deaktiviert. "
                    "Bitte Microsoft-Login setzen und Bridge-Override pushen."
                ),
                level=messages.WARNING,
            )
            return
        ok_count = 0
        fail_count = 0
        for registration in queryset:
            try:
                register_builder_account_on_minecraft(registration)
                ok_count += 1
            except SessionControlError as exc:
                fail_count += 1
                self.message_user(
                    request,
                    _("%(name)s: %(error)s")
                    % {"name": registration.mc_username, "error": str(exc)},
                    level=messages.ERROR,
                )
            except RconSequenceError as exc:
                fail_count += 1
                self.message_user(
                    request,
                    _("%(name)s: RCON/AuthMe-Fehler — %(error)s")
                    % {"name": registration.mc_username, "error": str(exc)[:300]},
                    level=messages.ERROR,
                )
        if ok_count:
            self.message_user(
                request,
                _("%(n)s Bau-Account(s) auf dem Minecraft-Server angelegt bzw. bestätigt.")
                % {"n": ok_count},
                level=messages.SUCCESS,
            )
        if fail_count and not ok_count:
            self.message_user(
                request,
                _(
                    "Keine Accounts angelegt. Passwort in .env setzen? "
                    "(MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD oder "
                    "MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD)"
                ),
                level=messages.WARNING,
            )

    def get_queryset(self, request):
        # Show inactive rows too so operators can re-enable Bau-PCs without re-registering.
        return super().get_queryset(request).select_related("group", "registered_by")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return user_can_manage_builder_sessions(request.user) or super(
            MinecraftBuilderAccountAdmin, self
        ).has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return user_can_manage_builder_sessions(request.user) or super(
            MinecraftBuilderAccountAdmin, self
        ).has_change_permission(request, obj)


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


class ZeroVelosPriceFilter(admin.SimpleListFilter):
    title = _("Velos-Preis")
    parameter_name = "velos_price"

    def lookups(self, request, model_admin):
        return (
            ("zero", _("Ohne Velos (0)")),
            ("ok", _("Mit Velos (≥ 1)")),
        )

    def queryset(self, request, queryset):
        if self.value() == "zero":
            return queryset.filter(buy_price_velos=0)
        if self.value() == "ok":
            return queryset.filter(buy_price_velos__gte=1)
        return queryset


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
    list_filter = ("enabled", "category", ZeroVelosPriceFilter)
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
    actions = ("assign_minimum_one_velo",)

    @admin.action(description=_("Kaufpreis auf mindestens 1 Velo setzen"))
    def assign_minimum_one_velo(self, request, queryset):
        from minecraft.services.shop_pricing import DEFAULT_MINIMUM_VELOS

        updated = queryset.filter(buy_price_velos__lt=DEFAULT_MINIMUM_VELOS).update(
            buy_price_velos=DEFAULT_MINIMUM_VELOS
        )
        self.message_user(
            request,
            _("%(n)s Artikel auf mindestens %(min)s Velo gesetzt.")
            % {"n": updated, "min": DEFAULT_MINIMUM_VELOS},
            level=messages.SUCCESS,
        )


@admin.register(MinecraftShopPurchaseCredit)
class MinecraftShopPurchaseCreditAdmin(admin.ModelAdmin):
    """Per-team remaining sellable quantities for shop materials (sell-back ledger)."""

    list_display = ("group", "material", "quantity")
    list_filter = ("group",)
    search_fields = ("material", "group__name", "group__mc_username")
    ordering = ("group__name", "material")
    list_per_page = 100
    readonly_fields = ()

    def has_module_permission(self, request):
        # Shown via custom Minecraft menu entry for shop operators.
        return request.user.has_perm("minecraft.view_minecraftshoppurchasecredit") or (
            request.user.is_active
            and request.user.is_staff
            and (
                request.user.is_superuser
                or request.user.has_perm("minecraft.access_minecraft_shop")
            )
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("minecraft.change_minecraftshoppurchasecredit") or (
            request.user.is_superuser
        )

    def has_add_permission(self, request):
        return request.user.has_perm("minecraft.add_minecraftshoppurchasecredit") or (
            request.user.is_superuser
        )

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("minecraft.delete_minecraftshoppurchasecredit") or (
            request.user.is_superuser
        )


@admin.register(MinecraftArenaMotionSettings)
class MinecraftArenaMotionSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "prefer_database_lanes",
        "tick_interval_seconds",
        "reference_mps",
        "min_motion_speed",
        "max_motion_speed",
        "updated_at",
    )
    fieldsets = (
        (
            _("Quelle"),
            {"fields": ("prefer_database_lanes",)},
        ),
        (
            _("Timing"),
            {
                "fields": (
                    "tick_interval_seconds",
                    "motion_min_distance",
                    "lap_cooldown_ticks",
                    "actionbar_enabled",
                    "cart_label_mode",
                    "cart_name_visible",
                )
            },
        ),
        (
            _("Distance → Motion"),
            {
                "fields": (
                    "reference_mps",
                    "min_motion_speed",
                    "max_motion_speed",
                    "default_impulse_x",
                    "default_impulse_y",
                    "default_impulse_z",
                )
            },
        ),
        (
            _("MCC-Boxen / Sessions"),
            {"fields": ("end_device_sessions_on_race_start",)},
        ),
        (_("Meta"), {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)

    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("minecraft.view_minecraftarenamotionsettings")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("minecraft.change_minecraftarenamotionsettings")

    def has_add_permission(self, request):
        if not request.user.has_perm("minecraft.add_minecraftarenamotionsettings"):
            return False
        return not MinecraftArenaMotionSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = MinecraftArenaMotionSettings.get_solo()
        from django.shortcuts import redirect

        return redirect(
            "admin:minecraft_minecraftarenamotionsettings_change",
            obj.pk,
        )


@admin.register(MinecraftArenaLane)
class MinecraftArenaLaneAdmin(admin.ModelAdmin):
    list_display = (
        "sort_order",
        "lane_id",
        "name",
        "tag",
        "color",
        "start_x",
        "start_y",
        "start_z",
        "base_speed",
        "is_active",
        "updated_at",
    )
    list_display_links = ("lane_id",)
    list_editable = ("sort_order", "is_active", "name")
    list_filter = ("is_active", "color")
    search_fields = ("lane_id", "name", "tag", "notes")
    ordering = ("sort_order", "lane_id")
    actions = ("import_from_toml_action",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "lane_id",
                    "name",
                    "tag",
                    "color",
                    "sort_order",
                    "is_active",
                    "notes",
                )
            },
        ),
        (
            _("Startposition"),
            {"fields": ("start_x", "start_y", "start_z", "yaw", "pitch", "base_speed")},
        ),
        (
            _("Ziellinie"),
            {"fields": ("finish_x_min", "finish_x_max", "finish_z_trigger")},
        ),
        (
            _("Startimpuls"),
            {"fields": ("impulse_x", "impulse_y", "impulse_z")},
        ),
        (
            _("Bevorzugte Stationen (Auto-Zuweisung)"),
            {
                "fields": ("preferred_stations",),
                "description": _(
                    "Welche IoT-Counter bei „Aktive erkennen“ auf diese Bahn sollen "
                    "(z. B. Stationen mit kleinen Rädern auf Bahn 1 und 2)."
                ),
            },
        ),
        (
            _("Optionales Welt-Schild"),
            {
                "classes": ("collapse",),
                "fields": ("sign_x", "sign_y", "sign_z"),
            },
        ),
        (_("Meta"), {"fields": ("updated_at",)}),
    )
    filter_horizontal = ("preferred_stations",)
    readonly_fields = ("updated_at",)

    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("minecraft.view_minecraftarenalane")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("minecraft.change_minecraftarenalane")

    def has_add_permission(self, request):
        return request.user.has_perm("minecraft.add_minecraftarenalane")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("minecraft.delete_minecraftarenalane")

    @admin.action(description=_("TOML-Beispiel/Config in DB importieren"))
    def import_from_toml_action(self, request, queryset):
        from minecraft.services.arena_motion.lanes import import_lanes_from_toml

        try:
            count = import_lanes_from_toml()
        except Exception as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return
        self.message_user(
            request,
            _("Importiert/aktualisiert: %(n)s Bahn(en). Geometrie kommt jetzt aus der DB.")
            % {"n": count},
            level=messages.SUCCESS,
        )
