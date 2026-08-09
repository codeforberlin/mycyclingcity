import uuid

from django.conf import settings as django_settings
from django.core.validators import MinValueValidator
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
        verbose_name = _("Outbox-Ereignis")
        verbose_name_plural = _("Outbox")

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
    player_session_active_hint = models.CharField(
        max_length=200,
        default="⚠️ FEZitty-Pass eingesammelt?",
        blank=True,
        verbose_name=_("Hinweis aktive Spieler-Session"),
        help_text=_(
            "Gelber Hinweis auf dem Spieler-Sessions-Dashboard bei laufender Session. "
            "Leer lassen = Hinweis ausblenden."
        ),
    )
    builder_session_active_hint = models.CharField(
        max_length=200,
        default="⚠️ Session ist aktiv!",
        blank=True,
        verbose_name=_("Hinweis aktive Bau-Session"),
        help_text=_(
            "Gelber Hinweis auf dem Bau-Sessions-Dashboard bei laufender Session. "
            "Leer lassen = Hinweis ausblenden."
        ),
    )
    waitlist_public_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Öffentliche Wartelisten-Anzeige aktiv"),
        help_text=_(
            "Erlaubt die anonyme Live-Anzeige per Token-URL (nur Ticket-Nummern, keine Namen)."
        ),
    )
    waitlist_public_token = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Token öffentliche Anzeige"),
        help_text=_("Geheimer Token für die öffentliche Display-URL. Leer = automatisch generieren."),
    )
    player_velos_per_minute = models.PositiveIntegerField(
        default=20,
        verbose_name=_("Velos pro Spielminute"),
        help_text=_("Beispiel: 300 Velos ÷ 20 = 15 Minuten Minecraft-Spielzeit."),
    )
    player_min_velos = models.PositiveIntegerField(
        default=300,
        verbose_name=_("Mindest-Velos Spiel-Warteliste"),
        help_text=_("Mindestbetrag für eine Spiel-Session aus der Warteliste."),
    )
    proxy_presence_poll_seconds = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(2)],
        verbose_name=_("Update-Intervall Velocity-RCON (s)"),
        help_text=_(
            "Wie oft die Session-Dashboards den Spieler-Standort per Velocity-RCON "
            "(glist) abfragen, wenn niemand im Warteraum wartet. "
            "Bei Warteraum-Status wird automatisch häufiger abgefragt. "
            "Minimum 2 Sekunden, Standard 10."
        ),
    )
    session_login_wait_seconds = models.PositiveIntegerField(
        default=45,
        validators=[MinValueValidator(5)],
        verbose_name=_("Wartezeit nach Freigabe (s)"),
        help_text=_(
            "Nach Velocity-Send / AuthMe-Login wartet die Freigabe so lange, "
            "bis der Spieler auf dem Paper-Server online ist "
            "(Maus-Klick / Client-Fokus). Minimum 5, Standard 45."
        ),
    )
    arena_default_time_limit_minutes = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        verbose_name=_("Velo-Arena Default-Zeitlimit (Min.)"),
        help_text=_(
            "Standard-Zeitlimit für Velo-Rennen in der Arena-Steuerung "
            "(wenn noch kein Wert in der laufenden Session gespeichert ist). "
            "Nützlich, wenn das Zeitfeld auf älteren Browsern nicht änderbar ist. "
            "Minimum 1, Standard 5."
        ),
    )
    AUTH_OPS_ONLINE = "online"
    AUTH_OPS_FAILOVER = "failover"
    AUTH_OPS_RECOVERY = "recovery"
    AUTH_OPS_MODE_CHOICES = [
        (AUTH_OPS_ONLINE, _("Online (Microsoft)")),
        (AUTH_OPS_FAILOVER, _("Failover (Offline-Proxy)")),
        (AUTH_OPS_RECOVERY, _("Recovery (Rücktransfer)")),
    ]
    auth_ops_mode = models.CharField(
        max_length=16,
        choices=AUTH_OPS_MODE_CHOICES,
        default=AUTH_OPS_ONLINE,
        verbose_name=_("Auth-Betriebsmodus"),
        help_text=_(
            "Operativer Modus für Microsoft-Auth-Failover. "
            "Steuert Hinweise in der Admin-GUI; Velocity online-mode wird "
            "über die Failover-Aktionen umgeschaltet."
        ),
    )
    auth_failover_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Failover seit"),
    )
    auth_failback_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Letzter Failback"),
    )
    auth_last_snapshot_dir = models.CharField(
        max_length=512,
        blank=True,
        verbose_name=_("Letztes Playerdata-Backup"),
        help_text=_("Pfad des letzten Failover-/Migrate-Backups."),
    )
    world_border_enabled = models.BooleanField(
        default=True,
        verbose_name=_("World Border aktiv"),
        help_text=_(
            "Wenn aktiv: „Anwenden“ setzt die konfigurierte Größe. "
            "Wenn inaktiv bzw. „Deaktivieren“: Border auf Vanilla-Maximum."
        ),
    )
    world_border_center_x = models.FloatField(
        default=0.0,
        verbose_name=_("Border-Zentrum X"),
    )
    world_border_center_z = models.FloatField(
        default=0.0,
        verbose_name=_("Border-Zentrum Z"),
    )
    world_border_size = models.PositiveIntegerField(
        default=1000,
        validators=[MinValueValidator(1)],
        verbose_name=_("Border-Größe (Blöcke)"),
        help_text=_(
            "Durchmesser / Kantenlänge des quadratischen Bereichs "
            "(1000 → ca. 1000×1000 Blöcke)."
        ),
    )
    world_border_warning_distance = models.PositiveIntegerField(
        default=5,
        verbose_name=_("Warnung (Blöcke)"),
        help_text=_("Vanilla worldborder warning distance."),
    )
    world_border_damage_amount = models.FloatField(
        default=0.2,
        verbose_name=_("Schaden pro Sekunde"),
        help_text=_(
            "Vanilla worldborder damage amount. 0 = praktisch kein Schaden "
            "(Spieler werden weiterhin zurückgeschoben)."
        ),
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
        verbose_name = _("Integration")
        verbose_name_plural = _("Integration")
        permissions = [
            ("access_minecraft_control", _("Control öffnen")),
            ("access_minecraft_city", _("Stadtsteuerung öffnen")),
            ("access_minecraft_shop", _("Shop-Betrieb öffnen")),
            ("run_free_rcon", _("Freie RCON-Befehle senden")),
            ("manage_player_sessions", _("Spieler-Sessions verwalten")),
            ("manage_builder_sessions", _("Builder-Sessions verwalten")),
            ("run_arena_sim", _("Velo-Arena Simulation starten")),
            ("manage_minecraft_proxy", _("Velocity / Limbo / Paper steuern")),
            ("manage_auth_failover", _("Auth-Failover / Playerdata-Transfer")),
            ("manage_coreprotect", _("CoreProtect Rollback/Restore")),
            ("manage_protected_regions", _("Geschützte Regionen (WorldGuard)")),
        ]

    def __str__(self):
        return self.team_display_name

    @classmethod
    def get_config(cls):
        config, _created = cls.objects.get_or_create(pk=1)
        return config


class MinecraftPlayerdataTransferLog(models.Model):
    """Audit log for Auth-Failover playerdata copy operations."""

    DIRECTION_ONLINE_TO_OFFLINE = "online_to_offline"
    DIRECTION_OFFLINE_TO_ONLINE = "offline_to_online"
    DIRECTION_LEGACY_TO_TWIN = "legacy_to_twin"
    DIRECTION_CHOICES = [
        (DIRECTION_ONLINE_TO_OFFLINE, _("Online → Offline-Twin")),
        (DIRECTION_OFFLINE_TO_ONLINE, _("Offline-Twin → Online")),
        (DIRECTION_LEGACY_TO_TWIN, _("Legacy-Offline → MS-Offline-Twin")),
    ]

    direction = models.CharField(max_length=32, choices=DIRECTION_CHOICES)
    dry_run = models.BooleanField(default=True)
    ok = models.BooleanField(default=False)
    backup_dir = models.CharField(max_length=512, blank=True)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Playerdata-Transfer")
        verbose_name_plural = _("Playerdata-Transfers")

    def __str__(self):
        return f"{self.direction} ({'dry' if self.dry_run else 'run'}) @ {self.created_at}"


class MinecraftTeamRegistration(models.Model):
    """Explicit approval for a group to appear on the Minecraft scoreboard."""

    group = models.OneToOneField(
        "api.Group",
        on_delete=models.CASCADE,
        related_name="minecraft_registration",
        verbose_name=_("Gruppe"),
    )
    mc_username = models.CharField(max_length=100, db_index=True, verbose_name=_("Minecraft-Name"))
    ms_username = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        verbose_name=_("Microsoft-Login"),
        help_text=_(
            "Online-Gamertag am Velocity-Proxy (z. B. mccpc01). "
            "Scoreboard bleibt mc_username; RCON/send und Bridge-Override nutzen diesen Login."
        ),
    )
    ms_uuid = models.CharField(
        max_length=36,
        blank=True,
        verbose_name=_("Microsoft-UUID"),
        help_text=_("Optional; Inventar/Shop hängen an der UUID. Nach erstem Join ergänzbar."),
    )
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
    session_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Session-Dauer (Min.)"),
        help_text=_("Leer = globaler Standard (MCC_MINECRAFT_BUILDER_SESSION_MINUTES)"),
    )
    add_time_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Zeit hinzufügen (Min.)"),
        help_text=_("Leer = globaler Standard (MCC_MINECRAFT_SESSION_ADD_MINUTES)"),
    )
    authme_is_registered = models.BooleanField(
        default=False,
        verbose_name=_("Auf MC-Server angelegt"),
        help_text=_("AuthMe-Account wurde per RCON registriert"),
    )
    authme_registered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("MC-Registrierung am"),
    )
    authme_last_error = models.TextField(
        blank=True,
        verbose_name=_("Letzter MC-Registrierungsfehler"),
    )
    prefer_spectator = models.BooleanField(
        default=False,
        verbose_name=_("Spectator-Modus bevorzugen"),
        help_text=_(
            "Nächste Session startet im Spectator-Modus. "
            "Bei aktiver Session per Toggle auf der Session-Kachel umschaltbar."
        ),
    )
    prefer_gamemode = models.CharField(
        max_length=16,
        blank=True,
        default="",
        verbose_name=_("Bevorzugter Spielmodus"),
        help_text=_(
            "Leer = Adventure. Werte: survival, adventure, spectator. "
            "Überschreibt „Spectator bevorzugen“, wenn gesetzt. "
            "Für Bau typischerweise leer lassen und Survival über die Session-GUI setzen."
        ),
    )

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

    @property
    def online_login(self) -> str:
        """Microsoft login for RCON/proxy, or empty if not configured."""
        return (self.ms_username or "").strip()


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
        verbose_name = _("Scoreboard-Snapshot")
        verbose_name_plural = _("Scoreboard")

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
        verbose_name = _("Shop-Kategorie")
        verbose_name_plural = _("Shop-Kategorien")

    def __str__(self):
        return self.name

    @property
    def section_key(self) -> str:
        return self.esgui_section or self.slug


class MinecraftShopItem(models.Model):
    """Shop item priced in Velos (buy; sell refund is 100% of current buy price)."""

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
    buy_price_velos = models.PositiveIntegerField(
        verbose_name=_("Kaufpreis (Velos)"),
        validators=[MinValueValidator(1)],
        help_text=_("Mindestens 1 Velo — kostenlose Artikel (0) sind nicht erlaubt."),
    )
    stack_size = models.PositiveIntegerField(default=1, verbose_name=_("Stack-Größe"))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    enabled = models.BooleanField(default=True, verbose_name=_("Aktiv"))

    class Meta:
        ordering = ["category", "sort_order", "esgui_item_key", "material"]
        verbose_name = _("Shop-Artikel")
        verbose_name_plural = _("Shop-Artikel")
        constraints = [
            models.UniqueConstraint(
                fields=["category", "esgui_item_loc"],
                name="minecraft_shop_item_unique_loc",
            ),
        ]

    def __str__(self):
        label = self.display_name or self.esgui_item_key or self.material
        return f"{label} ({self.buy_price_velos} Velos)"


class MinecraftShopPurchaseCredit(models.Model):
    """
    Per-team remaining sellable quantity for shop materials.

    Incremented on successful EconomyShopGUI buys; decremented before sells.
    World-mined items of the same material are only sellable up to this credit.
    """

    group = models.ForeignKey(
        "api.Group",
        on_delete=models.CASCADE,
        related_name="shop_purchase_credits",
        verbose_name=_("Gruppe"),
    )
    material = models.CharField(max_length=64, verbose_name=_("Material"))
    quantity = models.PositiveIntegerField(default=0, verbose_name=_("Restmenge"))

    class Meta:
        verbose_name = _("Shop-Kaufguthaben")
        verbose_name_plural = _("Shop-Kaufguthaben")
        constraints = [
            models.UniqueConstraint(
                fields=["group", "material"],
                name="minecraft_shop_purchase_credit_unique",
            ),
        ]

    def __str__(self):
        return f"{self.group} {self.material}: {self.quantity}"


class MinecraftWorkerState(models.Model):
    is_running = models.BooleanField(default=False)
    pid = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Worker-Status")
        verbose_name_plural = _("Worker")

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
        verbose_name = _("RCON-Preset")
        verbose_name_plural = _("RCON-Presets")
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
        verbose_name = _("Bridge-Verbindung")
        verbose_name_plural = _("Bridge-Verbindungen")

    def __str__(self):
        state = "online" if self.is_connected else "offline"
        return f"{self.server_id} ({state})"


class MinecraftPlayAccount(models.Model):
    """Configurable play slot (Arena) with RFID key, analogous to Cyclist.id_tag."""

    id_tag = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("RFID-UID"),
        help_text=_("Eindeutiger Key (v1 oft gleich Kurzname, später echte RFID-UID)"),
    )
    short_name = models.CharField(
        max_length=32,
        unique=True,
        verbose_name=_("Kurzname / Login"),
        help_text=_("Internes Slot-Label (z. B. Arena1); Scoreboard/Warteliste."),
    )
    ms_username = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        verbose_name=_("Microsoft-Login"),
        help_text=_("Online-Gamertag am Velocity-Proxy für RCON/send."),
    )
    ms_uuid = models.CharField(
        max_length=36,
        blank=True,
        verbose_name=_("Microsoft-UUID"),
        help_text=_("Optional; Inventar hängt an der UUID."),
    )
    display_name = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Anzeigename"),
        help_text=_("Leer = Kurzname"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Wenn aus: nicht in Spieler-Sessions, Warteliste und API sichtbar."),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    authme_is_registered = models.BooleanField(
        default=False,
        verbose_name=_("Auf MC-Server angelegt"),
        help_text=_("AuthMe-Account wurde per RCON registriert"),
    )
    authme_registered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("MC-Registrierung am"),
    )
    authme_last_error = models.TextField(
        blank=True,
        verbose_name=_("Letzter MC-Registrierungsfehler"),
    )
    session_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Session-Dauer (Min.)"),
        help_text=_("Leer = globaler Standard (MCC_MINECRAFT_PLAYER_SESSION_MINUTES)"),
    )
    add_time_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Zeit hinzufügen (Min.)"),
        help_text=_("Leer = globaler Standard (MCC_MINECRAFT_SESSION_ADD_MINUTES)"),
    )
    prefer_spectator = models.BooleanField(
        default=False,
        verbose_name=_("Spectator-Modus bevorzugen"),
        help_text=_(
            "Nächste Session startet im Spectator-Modus. "
            "Bei aktiver Session per Toggle auf der Session-Kachel umschaltbar."
        ),
    )
    prefer_gamemode = models.CharField(
        max_length=16,
        blank=True,
        default="",
        verbose_name=_("Bevorzugter Spielmodus"),
        help_text=_(
            "Leer = Adventure (Spieler). Werte: survival, adventure, spectator. "
            "Überschreibt „Spectator bevorzugen“, wenn gesetzt."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Angelegt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Geändert am"))

    class Meta:
        ordering = ["sort_order", "short_name"]
        verbose_name = _("Spieler-Account")
        verbose_name_plural = _("Spieler-Accounts")

    def __str__(self):
        label = self.display_name or self.short_name
        return f"{label} ({self.id_tag})"

    def save(self, *args, **kwargs):
        self.id_tag = (self.id_tag or "").strip()
        self.short_name = (self.short_name or "").strip()
        self.ms_username = (self.ms_username or "").strip()
        if not self.id_tag and self.short_name:
            self.id_tag = self.short_name
        if not self.short_name and self.id_tag:
            self.short_name = self.id_tag
        super().save(*args, **kwargs)

    @property
    def label(self) -> str:
        return self.display_name or self.short_name

    @property
    def online_login(self) -> str:
        return (self.ms_username or "").strip()


class MinecraftBuilderAccount(MinecraftTeamRegistration):
    """Active builder registrations — session settings only (registration stays in Control)."""

    class Meta:
        proxy = True
        verbose_name = _("Bau-Account")
        verbose_name_plural = _("Bau-Accounts")


class MCSession(models.Model):
    """History and active state for play/builder Minecraft sessions."""

    ACCOUNT_PLAYER = "PLAYER"
    ACCOUNT_BUILDER = "BUILDER"
    ACCOUNT_TYPE_CHOICES = [
        (ACCOUNT_PLAYER, _("Spieler (Arena)")),
        (ACCOUNT_BUILDER, _("Bau-Team")),
    ]

    STATUS_READY = "READY"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_FINISHED = "FINISHED"
    STATUS_CHOICES = [
        (STATUS_READY, _("Bereit")),
        (STATUS_ACTIVE, _("Aktiv")),
        (STATUS_FINISHED, _("Beendet")),
    ]

    SOURCE_ADMIN = "admin"
    SOURCE_RFID = "rfid"
    SOURCE_SYSTEM = "system"
    SOURCE_CHOICES = [
        (SOURCE_ADMIN, _("Admin-GUI")),
        (SOURCE_RFID, _("RFID-Scan")),
        (SOURCE_SYSTEM, _("System")),
    ]

    GAMEMODE_SURVIVAL = "survival"
    GAMEMODE_ADVENTURE = "adventure"
    GAMEMODE_SPECTATOR = "spectator"
    GAMEMODE_CHOICES = [
        (GAMEMODE_SURVIVAL, _("Survival")),
        (GAMEMODE_ADVENTURE, _("Adventure")),
        (GAMEMODE_SPECTATOR, _("Spectator")),
    ]

    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account_name = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_("Account-Name"),
        help_text=_("Interner Slot-/Team-Name (short_name oder Team-mc_username)"),
    )
    ms_username = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        verbose_name=_("Microsoft-Login (Session)"),
        help_text=_("Online-Spielername für RCON während der Session."),
    )
    account_type = models.CharField(
        max_length=16,
        choices=ACCOUNT_TYPE_CHOICES,
        verbose_name=_("Account-Typ"),
    )
    timestamp_start = models.DateTimeField(default=timezone.now, verbose_name=_("Start"))
    duration_minutes = models.PositiveIntegerField(verbose_name=_("Dauer (Minuten)"))
    ends_at = models.DateTimeField(db_index=True, verbose_name=_("Geplantes Ende"))
    timestamp_end = models.DateTimeField(null=True, blank=True, verbose_name=_("Tatsächliches Ende"))
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_READY,
        db_index=True,
        verbose_name=_("Status"),
    )
    source = models.CharField(
        max_length=16,
        choices=SOURCE_CHOICES,
        default=SOURCE_ADMIN,
        verbose_name=_("Auslöser"),
    )
    started_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Gestartet von"),
    )
    last_error = models.TextField(blank=True, verbose_name=_("Letzter Fehler"))
    gamemode_spectator = models.BooleanField(
        default=False,
        db_default=False,
        verbose_name=_("Spectator aktiv"),
        help_text=_("Legacy-Flag; gespiegelt aus play_gamemode == spectator."),
    )
    play_gamemode = models.CharField(
        max_length=16,
        choices=GAMEMODE_CHOICES,
        default=GAMEMODE_ADVENTURE,
        db_default=GAMEMODE_ADVENTURE,
        verbose_name=_("Spielmodus"),
        help_text=_("Aktueller Gamemode der Session (survival / adventure / spectator)."),
    )
    teleport_to_spawn = models.BooleanField(
        default=False,
        db_default=False,
        verbose_name=_("Zum Welt-Spawn beim Start"),
        help_text=_(
            "Wenn gesetzt: nach Login zum Welt-/Lobby-Spawn teleportieren. "
            "Sonst Minecraft-Standard (letzte Position)."
        ),
    )
    spawn_offset_index = models.PositiveSmallIntegerField(
        default=0,
        db_default=0,
        verbose_name=_("Spawn-Versatz-Index"),
        help_text=_("Gitter-/Ring-Index beim Spawn-Teleport (0 = exakter Spawn)."),
    )

    class Meta:
        ordering = ["-timestamp_start"]
        verbose_name = _("Session")
        verbose_name_plural = _("Sessions")
        constraints = [
            models.UniqueConstraint(
                fields=["account_name"],
                condition=models.Q(status="ACTIVE"),
                name="minecraft_unique_active_session_per_account",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "ends_at"], name="minecraft_mcsess_status_ends"),
        ]

    def __str__(self):
        return f"{self.account_name} [{self.account_type}] {self.status}"

    @property
    def remaining_seconds(self) -> int:
        if self.status != self.STATUS_ACTIVE:
            return 0
        delta = (self.ends_at - timezone.now()).total_seconds()
        return max(0, int(delta))


class MinecraftSessionWaitlistEntry(models.Model):
    """Queue entry for Minecraft play or builder sessions (operator-managed)."""

    QUEUE_PLAYER = "player"
    QUEUE_BUILDER = "builder"
    QUEUE_TYPE_CHOICES = [
        (QUEUE_PLAYER, _("Spieler (Arena)")),
        (QUEUE_BUILDER, _("Bau-Team")),
    ]

    STATUS_WAITING = "waiting"
    STATUS_ASSIGNED = "assigned"
    STATUS_ACTIVE = "active"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_WAITING, _("Wartend")),
        (STATUS_ASSIGNED, _("Zugewiesen")),
        (STATUS_ACTIVE, _("Aktiv")),
        (STATUS_DONE, _("Erledigt")),
        (STATUS_CANCELLED, _("Abgebrochen")),
    ]

    queue_type = models.CharField(
        max_length=16,
        choices=QUEUE_TYPE_CHOICES,
        db_index=True,
        verbose_name=_("Wartelisten-Typ"),
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_WAITING,
        db_index=True,
        verbose_name=_("Status"),
    )
    ticket_number = models.CharField(
        max_length=16,
        db_index=True,
        verbose_name=_("Ticket-Nummer"),
        help_text=_("Anonyme Kennung vom Flyer (öffentliche Anzeige)."),
    )
    guest_label = models.CharField(
        max_length=120,
        blank=True,
        verbose_name=_("Interner Name"),
        help_text=_("Nur für Operatoren sichtbar, nicht auf öffentlicher Anzeige."),
    )
    velos_cost = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Velos (Einlösung)"),
    )
    duration_minutes = models.PositiveIntegerField(
        verbose_name=_("Session-Dauer (Min.)"),
    )
    internal_note = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Interne Notiz"),
    )
    assigned_play_account = models.ForeignKey(
        "MinecraftPlayAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="waitlist_entries",
        verbose_name=_("Zugewiesener Spiel-Account"),
    )
    assigned_builder_registration = models.ForeignKey(
        "MinecraftTeamRegistration",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="waitlist_entries",
        verbose_name=_("Zugewiesenes Bau-Team"),
    )
    mc_session = models.ForeignKey(
        "MCSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="waitlist_entries",
        verbose_name=_("Minecraft-Session"),
    )
    queued_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("Eingetragen am"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Gestartet am"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Beendet am"))
    queued_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Eingetragen von"),
    )
    started_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Gestartet von"),
    )

    class Meta:
        ordering = ["queued_at"]
        verbose_name = _("Session-Wartelisteneintrag")
        verbose_name_plural = _("Session-Warteliste")
        indexes = [
            models.Index(
                fields=["queue_type", "status", "queued_at"],
                name="minecraft_waitlist_q_status",
            ),
        ]

    def __str__(self):
        return f"#{self.ticket_number} [{self.queue_type}] {self.status}"


class MinecraftArenaMotionSettings(models.Model):
    """Singleton: global VeloArena motion parameters (not per-lane geometry)."""

    tick_interval_seconds = models.FloatField(
        default=0.1,
        verbose_name=_("Tick-Intervall (s)"),
    )
    motion_min_distance = models.FloatField(
        default=0.03,
        verbose_name=_("Min. Bewegungsdistanz für Motion"),
    )
    lap_cooldown_ticks = models.PositiveIntegerField(
        default=30,
        verbose_name=_("Lap-Cooldown (Ticks)"),
    )
    actionbar_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Actionbar-Ansagen"),
    )
    cart_label_mode = models.CharField(
        max_length=16,
        default="name_only",
        choices=(
            ("name_only", _("Nur Name (Status im HUD)")),
            ("full", _("Voll (Platz, km/h, Runden auf der Lore)")),
        ),
        verbose_name=_("Lore-Label-Modus"),
    )
    cart_name_visible = models.BooleanField(
        default=True,
        verbose_name=_("Floating-Labels an Loren"),
    )
    reference_mps = models.FloatField(
        default=2.0,
        verbose_name=_("Referenz-Geschwindigkeit (m/s)"),
    )
    min_motion_speed = models.FloatField(default=0.08, verbose_name=_("Min. Motion"))
    max_motion_speed = models.FloatField(default=0.55, verbose_name=_("Max. Motion"))
    default_impulse_x = models.FloatField(default=0.0, verbose_name=_("Default-Impuls X"))
    default_impulse_y = models.FloatField(default=0.0, verbose_name=_("Default-Impuls Y"))
    default_impulse_z = models.FloatField(default=1.0, verbose_name=_("Default-Impuls Z"))
    prefer_database_lanes = models.BooleanField(
        default=True,
        verbose_name=_("Bahn-Geometrie aus Datenbank nutzen"),
        help_text=_(
            "Wenn aktiv und mindestens eine aktive Bahn existiert, "
            "wird die TOML-Datei ignoriert."
        ),
    )
    end_device_sessions_on_race_start = models.BooleanField(
        default=True,
        verbose_name=_("Geräte-Sessions bei Rennstart beenden"),
        help_text=_(
            "Beim Velo-Arena-Start werden aktive Geräte-Sessions der zugewiesenen "
            "Radler beendet (Session-km/Velos starten bei 0; Standalone-Radler am "
            "Counter bleiben aktiv). OLED-Sperre wird unabhängig davon gelöst."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Arena-Motion-Einstellungen")
        verbose_name_plural = _("Arena-Motion-Einstellungen")

    def __str__(self):
        return "Arena-Motion-Einstellungen"

    @classmethod
    def get_solo(cls) -> "MinecraftArenaMotionSettings":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class MinecraftArenaLane(models.Model):
    """Physical Wirkbahn geometry for VeloArena minecart motion."""

    lane_id = models.SlugField(
        max_length=64,
        unique=True,
        verbose_name=_("Bahn-ID"),
        help_text=_("Stabiler Schlüssel, z. B. lane_1"),
    )
    name = models.CharField(max_length=64, verbose_name=_("Anzeigename"))
    tag = models.CharField(
        max_length=64,
        verbose_name=_("Minecart-Tag"),
        help_text=_("Minecraft-Entity-Tag, z. B. velo_lane_1"),
    )
    color = models.CharField(
        max_length=32,
        default="white",
        verbose_name=_("Label-Farbe"),
        help_text=_("Minecraft-Farbname für text_display"),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))

    start_x = models.FloatField(verbose_name=_("Start X"))
    start_y = models.FloatField(verbose_name=_("Start Y"))
    start_z = models.FloatField(verbose_name=_("Start Z"))
    yaw = models.FloatField(default=0.0, verbose_name=_("Yaw"))
    pitch = models.FloatField(default=0.0, verbose_name=_("Pitch"))
    base_speed = models.FloatField(default=0.4, verbose_name=_("Basis-Motion"))

    finish_x_min = models.FloatField(verbose_name=_("Ziel X min"))
    finish_x_max = models.FloatField(verbose_name=_("Ziel X max"))
    finish_z_trigger = models.FloatField(verbose_name=_("Ziel Z-Trigger"))

    impulse_x = models.FloatField(default=0.0, verbose_name=_("Impuls X"))
    impulse_y = models.FloatField(default=0.0, verbose_name=_("Impuls Y"))
    impulse_z = models.FloatField(default=1.0, verbose_name=_("Impuls Z"))

    sign_x = models.FloatField(null=True, blank=True, verbose_name=_("Schild X"))
    sign_y = models.FloatField(null=True, blank=True, verbose_name=_("Schild Y"))
    sign_z = models.FloatField(null=True, blank=True, verbose_name=_("Schild Z"))

    preferred_stations = models.ManyToManyField(
        "iot.Device",
        blank=True,
        related_name="preferred_arena_lanes",
        verbose_name=_("Bevorzugte Stationen"),
        help_text=_(
            "IoT-Stationen, die bei „Aktive erkennen“ bevorzugt dieser Bahn "
            "zugeordnet werden (z. B. kleine Räder → Bahn 1 und 2). "
            "Leer = beliebige freie Session."
        ),
    )

    notes = models.CharField(max_length=255, blank=True, verbose_name=_("Notiz"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "lane_id"]
        verbose_name = _("Arena-Bahn (Geometrie)")
        verbose_name_plural = _("Arena-Bahnen (Geometrie)")

    def __str__(self):
        return f"{self.name} ({self.lane_id})"

    def clean(self):
        from django.core.exceptions import ValidationError

        signs = [self.sign_x, self.sign_y, self.sign_z]
        if any(v is not None for v in signs) and any(v is None for v in signs):
            raise ValidationError(
                _("Schild-Koordinaten sign_x/y/z müssen zusammen gesetzt werden.")
            )


class MinecraftProtectedRegion(models.Model):
    """Cuboid WorldGuard region managed from Stadtsteuerung, linked to Bau-Accounts."""

    region_id = models.SlugField(
        max_length=64,
        unique=True,
        verbose_name=_("Region-ID"),
        help_text=_("WorldGuard-Regionsname (a–z, 0–9, _, -)."),
    )
    display_name = models.CharField(
        max_length=120,
        blank=True,
        verbose_name=_("Anzeigename"),
    )
    world = models.CharField(
        max_length=64,
        default="MyCyclingCity",
        verbose_name=_("Welt"),
    )
    min_x = models.IntegerField(verbose_name=_("Min X"))
    min_y = models.IntegerField(default=-64, verbose_name=_("Min Y"))
    min_z = models.IntegerField(verbose_name=_("Min Z"))
    max_x = models.IntegerField(verbose_name=_("Max X"))
    max_y = models.IntegerField(default=320, verbose_name=_("Max Y"))
    max_z = models.IntegerField(verbose_name=_("Max Z"))
    protect_build = models.BooleanField(
        default=True,
        verbose_name=_("Bauen schützen"),
        help_text=_(
            "Wenn aktiv: WorldGuard-Standardschutz (Nicht-Mitglieder dürfen nicht bauen). "
            "Nicht das Flag „build deny“ — das würde auch Members blockieren."
        ),
    )
    builders = models.ManyToManyField(
        "MinecraftTeamRegistration",
        blank=True,
        related_name="protected_regions",
        verbose_name=_("Bau-Accounts (Mitglieder)"),
        help_text=_(
            "Verknüpfte Bau-Registrierungen; Sync setzt WorldGuard-Members "
            "auf deren Microsoft-Login (ms_username)."
        ),
    )
    synced_members = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Zuletzt synchronisierte Members"),
        help_text=_("MS-Logins, die zuletzt per RCON als Member gesetzt wurden."),
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Zuletzt synchronisiert"),
    )
    last_sync_error = models.TextField(blank=True, verbose_name=_("Letzter Sync-Fehler"))
    notes = models.CharField(max_length=255, blank=True, verbose_name=_("Notiz"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Geändert von"),
    )

    class Meta:
        ordering = ["region_id"]
        verbose_name = _("Geschützte Region")
        verbose_name_plural = _("Geschützte Regionen")

    def __str__(self):
        label = (self.display_name or "").strip() or self.region_id
        return f"{label} ({self.region_id})"

    def normalized_bounds(self) -> tuple[int, int, int, int, int, int]:
        """Return (min_x, min_y, min_z, max_x, max_y, max_z) with min <= max per axis."""
        return (
            min(self.min_x, self.max_x),
            min(self.min_y, self.max_y),
            min(self.min_z, self.max_z),
            max(self.min_x, self.max_x),
            max(self.min_y, self.max_y),
            max(self.min_z, self.max_z),
        )
