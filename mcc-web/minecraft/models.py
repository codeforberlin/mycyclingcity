from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class MinecraftOutboxEvent(models.Model):
    EVENT_UPDATE_PLAYER_COINS = "update_player_coins"
    EVENT_UPDATE_GROUP_VELOS = "update_group_velos"  # legacy alias
    EVENT_SYNC_ALL = "sync_all"  # legacy alias
    EVENT_REGISTER_TEAM = "register_team"
    EVENT_UNREGISTER_TEAM = "unregister_team"
    EVENT_UPDATE_TEAM_VELOS = "update_team_velos"
    EVENT_SYNC_REGISTERED_TEAMS = "sync_registered_teams"
    EVENT_ENSURE_OBJECTIVES = "ensure_objectives"

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    EVENT_TYPE_CHOICES = [
        (EVENT_UPDATE_PLAYER_COINS, _("Update Player Coins (deprecated)")),
        (EVENT_UPDATE_GROUP_VELOS, _("Update Group Velos (legacy)")),
        (EVENT_SYNC_ALL, _("Sync All Groups (legacy)")),
        (EVENT_REGISTER_TEAM, _("Register Team")),
        (EVENT_UNREGISTER_TEAM, _("Unregister Team")),
        (EVENT_UPDATE_TEAM_VELOS, _("Update Team Velos")),
        (EVENT_SYNC_REGISTERED_TEAMS, _("Sync Registered Teams")),
        (EVENT_ENSURE_OBJECTIVES, _("Ensure Objectives")),
    ]

    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pending")),
        (STATUS_PROCESSING, _("Processing")),
        (STATUS_DONE, _("Done")),
        (STATUS_FAILED, _("Failed")),
    ]

    event_type = models.CharField(max_length=64, choices=EVENT_TYPE_CHOICES)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Minecraft Outbox Event")
        verbose_name_plural = _("Minecraft Outbox Events")

    def mark_done(self):
        self.status = self.STATUS_DONE
        self.processed_at = timezone.now()
        self.last_error = ""
        self.save(update_fields=["status", "processed_at", "last_error"])

    def mark_failed(self, error_message: str):
        self.status = self.STATUS_FAILED
        self.processed_at = timezone.now()
        self.last_error = error_message[:5000]
        self.save(update_fields=["status", "processed_at", "last_error"])

    def mark_retry(self, error_message: str):
        """Keep event pending after a transient failure (retry with short backoff)."""
        self.status = self.STATUS_PENDING
        self.processed_at = timezone.now()  # last attempt; used as backoff anchor
        self.last_error = error_message[:5000]
        self.save(update_fields=["status", "processed_at", "last_error"])

    def mark_processing(self):
        self.status = self.STATUS_PROCESSING
        self.attempts = self.attempts + 1
        self.save(update_fields=["status", "attempts"])


class MinecraftIntegrationConfig(models.Model):
    """Singleton configuration for the team spendable scoreboard."""

    team_display_name = models.CharField(
        max_length=64,
        default="Velo-Arena",
        verbose_name=_("Scoreboard-Anzeigename"),
        help_text=_("Sidebar-Titel in Minecraft (ausgebare Velos)"),
    )
    objective_spendable = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Objective-Slug"),
        help_text=_("Leer = Wert aus Umgebungsvariable / settings.py"),
    )
    sync_on_earn = models.BooleanField(
        default=True,
        verbose_name=_("Bei Velos-Earn synchronisieren"),
    )
    sidebar_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Sidebar-Anzeige aktiv"),
        help_text=_("Objective automatisch in der Sidebar anzeigen (setdisplay)"),
    )

    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Zuletzt aktualisiert"))
    updated_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Geändert von"),
    )

    class Meta:
        verbose_name = _("Minecraft Integration Config")
        verbose_name_plural = _("Minecraft Integration Config")

    def __str__(self):
        return self.team_display_name

    @classmethod
    def get_config(cls):
        config, _created = cls.objects.get_or_create(pk=1)
        return config


class MinecraftTeamRegistration(models.Model):
    """Explicit approval for a group to appear on the Minecraft scoreboard."""

    group = models.OneToOneField(
        "api.Group",
        on_delete=models.CASCADE,
        related_name="minecraft_registration",
        verbose_name=_("Gruppe"),
    )
    mc_username = models.CharField(max_length=100, db_index=True, verbose_name=_("Minecraft-Name"))
    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv in Minecraft"))
    was_ever_registered = models.BooleanField(
        default=True,
        verbose_name=_("War schon einmal registriert"),
    )
    registered_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Registriert am"))
    registered_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Registriert von"),
    )
    deactivated_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Deaktiviert am"))
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Zuletzt synchronisiert"))
    last_sync_error = models.TextField(blank=True, verbose_name=_("Letzter Sync-Fehler"))

    class Meta:
        verbose_name = _("Minecraft Team Registration")
        verbose_name_plural = _("Minecraft Team Registrations")
        constraints = [
            models.UniqueConstraint(
                fields=["mc_username"],
                condition=models.Q(is_active=True),
                name="minecraft_unique_active_mc_username",
            ),
        ]

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.mc_username} ({self.group.name}, {status})"


class MinecraftPlayerScoreboardSnapshot(models.Model):
    player_name = models.CharField(max_length=64, db_index=True)
    group = models.ForeignKey(
        "api.Group",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="minecraft_scoreboard_snapshots",
    )
    cyclist = models.ForeignKey(
        "api.Cyclist",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="minecraft_scoreboard_snapshots",
    )
    velos_total = models.PositiveIntegerField(default=0)
    velos_spendable = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=32, default="rcon")
    captured_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["player_name"]
        ordering = ["player_name"]
        verbose_name = _("Minecraft Scoreboard Snapshot")
        verbose_name_plural = _("Minecraft Scoreboard Snapshots")

    def __str__(self):
        return f"{self.player_name} ({self.velos_spendable} ausgebbar)"


class MinecraftShopCategory(models.Model):
    """Shop section synced to EconomyShopGUI via MCC-Bridge."""

    slug = models.SlugField(max_length=64, unique=True, verbose_name=_("Slug"))
    name = models.CharField(max_length=64, verbose_name=_("Name"))
    esgui_section = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("EconomyShopGUI-Section"),
        help_text=_("Leer = Slug"),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    enabled = models.BooleanField(default=True, verbose_name=_("Aktiv"))

    class Meta:
        ordering = ["sort_order", "slug"]
        verbose_name = _("Minecraft Shop Category")
        verbose_name_plural = _("Minecraft Shop Categories")

    def __str__(self):
        return self.name

    @property
    def section_key(self) -> str:
        return self.esgui_section or self.slug


class MinecraftShopItem(models.Model):
    """Buy-only shop item priced in Velos."""

    category = models.ForeignKey(
        MinecraftShopCategory,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Kategorie"),
    )
    material = models.CharField(max_length=64, verbose_name=_("Material"))
    display_name = models.CharField(max_length=128, blank=True, verbose_name=_("Anzeigename"))
    esgui_item_key = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("EconomyShopGUI Item-Key"),
        help_text=_("Kurzschlüssel aus der Shop-YAML (z. B. super_pickaxe)"),
    )
    esgui_item_loc = models.CharField(
        max_length=128,
        verbose_name=_("EconomyShopGUI Item-Index"),
        help_text=_("Eindeutige Position in der Shop-YAML, z. B. page1.items.super_pickaxe"),
    )
    buy_price_velos = models.PositiveIntegerField(verbose_name=_("Kaufpreis (Velos)"))
    stack_size = models.PositiveIntegerField(default=1, verbose_name=_("Stack-Größe"))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    enabled = models.BooleanField(default=True, verbose_name=_("Aktiv"))

    class Meta:
        ordering = ["category", "sort_order", "esgui_item_key", "material"]
        verbose_name = _("Minecraft Shop Item")
        verbose_name_plural = _("Minecraft Shop Items")
        constraints = [
            models.UniqueConstraint(
                fields=["category", "esgui_item_loc"],
                name="minecraft_shop_item_unique_loc",
            ),
        ]

    def __str__(self):
        label = self.display_name or self.esgui_item_key or self.material
        return f"{label} ({self.buy_price_velos} Velos)"


class MinecraftWorkerState(models.Model):
    is_running = models.BooleanField(default=False)
    pid = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Minecraft Worker State")
        verbose_name_plural = _("Minecraft Worker States")

    @classmethod
    def get_state(cls):
        state, _created = cls.objects.get_or_create(pk=1)
        return state


class MinecraftRconPreset(models.Model):
    """Editable RCON command bundle for one-click world/city control."""

    CATEGORY_WORLD = "world"
    CATEGORY_GAMERULE = "gamerule"
    CATEGORY_OTHER = "other"

    CATEGORY_CHOICES = [
        (CATEGORY_WORLD, _("Welt & Wetter")),
        (CATEGORY_GAMERULE, _("Spielregeln")),
        (CATEGORY_OTHER, _("Sonstiges")),
    ]

    slug = models.SlugField(max_length=64, unique=True, verbose_name=_("Slug"))
    name = models.CharField(max_length=64, verbose_name=_("Name"))
    category = models.CharField(
        max_length=32,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_WORLD,
        verbose_name=_("Kategorie"),
    )
    description = models.TextField(blank=True, verbose_name=_("Beschreibung"))
    commands = models.JSONField(
        default=list,
        verbose_name=_("RCON-Befehle"),
        help_text=_("Liste von Befehlen, die nacheinander ausgeführt werden."),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    enabled = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    is_system = models.BooleanField(
        default=False,
        verbose_name=_("System-Preset"),
        help_text=_("Von Migration geliefert; Löschen nur mit Sonderberechtigung."),
    )
    moderator_can_run = models.BooleanField(
        default=False,
        verbose_name=_("Moderator darf ausführen"),
        help_text=_("Erlaubt Ausführung auch außerhalb der Kategorie „Welt & Wetter“."),
    )
    requires_confirmation = models.BooleanField(
        default=True,
        verbose_name=_("Bestätigung vor Ausführung"),
    )
    stop_on_error = models.BooleanField(
        default=True,
        verbose_name=_("Bei Fehler abbrechen"),
    )
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Zuletzt ausgeführt"))
    last_run_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Zuletzt ausgeführt von"),
    )
    last_run_success = models.BooleanField(null=True, blank=True, verbose_name=_("Letzter Lauf erfolgreich"))
    last_run_output = models.TextField(blank=True, verbose_name=_("Letzte Ausgabe"))

    class Meta:
        ordering = ["category", "sort_order", "name"]
        verbose_name = _("Minecraft RCON Preset")
        verbose_name_plural = _("Minecraft RCON Presets")
        permissions = [
            ("run_rconpreset", _("RCON-Presets ausführen")),
            ("change_system_rconpreset", _("System-Presets bearbeiten")),
            ("delete_system_rconpreset", _("System-Presets löschen")),
            ("export_rconpreset", _("RCON-Presets exportieren")),
        ]

    def __str__(self):
        return self.name

    @property
    def command_count(self) -> int:
        return len(self.commands or [])


class MinecraftBridgeConnection(models.Model):
    """Tracks MCC-Bridge WebSocket presence (shared across Gunicorn and Daphne)."""

    server_id = models.CharField(max_length=64, primary_key=True, verbose_name=_("Server ID"))
    is_connected = models.BooleanField(default=False, verbose_name=_("Verbunden"))
    connected_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Verbunden seit"))
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Zuletzt gesehen"))

    class Meta:
        verbose_name = _("Minecraft Bridge Connection")
        verbose_name_plural = _("Minecraft Bridge Connections")

    def __str__(self):
        state = "online" if self.is_connected else "offline"
        return f"{self.server_id} ({state})"
