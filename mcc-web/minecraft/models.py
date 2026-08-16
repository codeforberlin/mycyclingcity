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
    world_ticket_enabled = models.BooleanField(
        default=True,
        verbose_name=_("MCC-Welt-Tickets aktiv"),
        help_text=_(
            "Zeigt den Ticket-Zähler auf den Session-Kacheln und vergibt "
            "Paper-Tickets per RCON beim Freischalten."
        ),
    )
    world_ticket_velos = models.PositiveIntegerField(
        default=100,
        validators=[MinValueValidator(1)],
        verbose_name=_("Velos pro MCC-Ticket"),
        help_text=_(
            "Preis eines Paper-Tickets. Bei Radler-Konto (RFID/Warteliste) "
            "wird Anzahl × dieser Betrag vom Guthaben abgezogen."
        ),
    )
    world_ticket_max = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        verbose_name=_("Max. Tickets pro Freigabe"),
        help_text=_("Obergrenze für den Ticket-Zähler auf den Session-Kacheln."),
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
    region_outline_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Region-Markierung (Partikel) aktiv"),
        help_text=_(
            "Wenn aktiv: MCC-Bridge zeichnet farbige Partikel-Umrandungen "
            "für geschützte Regionen in Spieler-Nähe."
        ),
    )
    region_outline_enter_hint = models.BooleanField(
        default=True,
        verbose_name=_("Hinweis beim Betreten der Region"),
        help_text=_("Actionbar mit Anzeigename, wenn ein Spieler eine Region betritt."),
    )
    region_outline_view_distance = models.PositiveIntegerField(
        default=48,
        validators=[MinValueValidator(8)],
        verbose_name=_("Sichtweite Region-Markierung (Blöcke)"),
        help_text=_("Partikel nur, wenn ein Spieler so nah an der Region ist. Minimum 8."),
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
            (
                "manage_assigned_protected_regions",
                _("Zugewiesene Bauzonen (Subregionen der eigenen TOP-Gruppe)"),
            ),
            (
                "manage_minecraft_accounts",
                _("Minecraft-Accounts (Spieler und Bau) verwalten"),
            ),
            (
                "manage_minecraft_operators",
                _("Vanilla-Operatorrechte (/op, /deop) verwalten"),
            ),
            (
                "manage_minecraft_stations",
                _("Minecraft-Stationen (PCs) und MS-Allowlist verwalten"),
            ),
            (
                "manage_grant_catalog",
                _("Vergabe-Katalog (Fahrzeuge, Items) verwalten"),
            ),
            (
                "manage_vehiclesplus_packs",
                _("VehiclesPlus Resourcepacks erzeugen/erweitern"),
            ),
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


class MinecraftVanillaOpLog(models.Model):
    """Audit log for Vanilla /op and /deop actions from the Admin GUI."""

    ACTION_OP = "op"
    ACTION_DEOP = "deop"
    ACTION_CHOICES = [
        (ACTION_OP, _("op")),
        (ACTION_DEOP, _("deop")),
    ]

    action = models.CharField(max_length=8, choices=ACTION_CHOICES)
    player_name = models.CharField(max_length=32, verbose_name=_("Spielername"))
    account_type = models.CharField(max_length=16, blank=True, verbose_name=_("Account-Typ"))
    account_ref = models.CharField(max_length=64, blank=True, verbose_name=_("Account-Ref"))
    ok = models.BooleanField(default=False)
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
        verbose_name = _("Vanilla-OP-Aktion")
        verbose_name_plural = _("Vanilla-OP-Aktionen")

    def __str__(self):
        status = "ok" if self.ok else "fail"
        return f"{self.action} {self.player_name} ({status})"


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
    session_unlimited = models.BooleanField(
        default=False,
        verbose_name=_("Unbegrenzte Session"),
        help_text=_(
            "Kein Zeitlimit beim Admin-Start. Session endet bei manuellem Kick "
            "oder wenn der Spieler den Server verlässt (Logout). "
            "Wartelisten-Zuweisungen bleiben zeitbegrenzt."
        ),
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
    session_unlimited = models.BooleanField(
        default=False,
        verbose_name=_("Unbegrenzte Session"),
        help_text=_(
            "Kein Zeitlimit beim Admin-Start. Session endet bei manuellem Kick "
            "oder wenn der Spieler den Server verlässt (Logout). "
            "Wartelisten-Zuweisungen bleiben zeitbegrenzt."
        ),
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
    assigned_to_group = models.ForeignKey(
        "api.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_play_accounts",
        verbose_name=_("TOP-Gruppe"),
        help_text=_(
            "Optionale Zuordnung zu einer TOP-Gruppe (parent is None) "
            "für Filter und Organisation in der Account-Verwaltung."
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
    duration_minutes = models.PositiveIntegerField(
        verbose_name=_("Dauer (Minuten)"),
        help_text=_("0 = unbegrenzte Session (ends_at ist dann leer)."),
    )
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Geplantes Ende"),
        help_text=_("Leer bei unbegrenzter Session (kein Timeout)."),
    )
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
    spawn_region = models.ForeignKey(
        "MinecraftProtectedRegion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions_spawned_here",
        verbose_name=_("Spawn-Region"),
        help_text=_(
            "Wenn gesetzt: Session startete mit Teleport in diese geschützte Region "
            "(statt Welt-Spawn)."
        ),
    )
    station = models.ForeignKey(
        "MinecraftStation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name=_("Station (PC)"),
        help_text=_("Physischer PC, an dem diese Session freigegeben wurde."),
    )
    world_ticket_count = models.PositiveSmallIntegerField(
        default=0,
        db_default=0,
        verbose_name=_("MCC-Welt-Tickets"),
        help_text=_(
            "Anzahl Paper-Tickets (custom_data mcc_ticket), die beim Bootstrap "
            "per RCON ins Inventar gelegt werden."
        ),
    )
    grant_catalog_slugs = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Vergabe-Katalog (Slugs)"),
        help_text=_(
            "Katalog-Slugs, die beim Session-Bootstrap per RCON vergeben werden "
            "(z. B. VehiclesPlus-Garage). Für Pending-Retry persistiert."
        ),
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
    def is_unlimited(self) -> bool:
        return self.ends_at is None

    @property
    def remaining_seconds(self) -> int:
        if self.status != self.STATUS_ACTIVE:
            return 0
        if self.ends_at is None:
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

    SOURCE_MANUAL = "manual"
    SOURCE_VELOS_REDEEM = "velos_redeem"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, _("Manuell (Flyer/Counter)")),
        (SOURCE_VELOS_REDEEM, _("Velos-Einlösung (RFID)")),
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
    source = models.CharField(
        max_length=16,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
        db_index=True,
        verbose_name=_("Herkunft"),
    )
    cyclist = models.ForeignKey(
        "api.Cyclist",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="minecraft_waitlist_entries",
        verbose_name=_("Radler (RFID-Einlösung)"),
    )
    velos_redemption = models.ForeignKey(
        "api.CyclistVelosRedemption",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="minecraft_waitlist_entries",
        verbose_name=_("Velos-Einlösung"),
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


class MinecraftStation(models.Model):
    """Physical PC used for play and/or builder sessions."""

    ROLE_PLAY = "play"
    ROLE_BUILDER = "builder"
    ROLE_BOTH = "both"
    ROLE_CHOICES = [
        (ROLE_PLAY, _("Nur Spiel")),
        (ROLE_BUILDER, _("Nur Bau")),
        (ROLE_BOTH, _("Spiel und Bau")),
    ]

    name = models.CharField(max_length=64, unique=True, verbose_name=_("Name"))
    location = models.CharField(max_length=120, blank=True, verbose_name=_("Standort"))
    role = models.CharField(
        max_length=16,
        choices=ROLE_CHOICES,
        default=ROLE_BOTH,
        db_index=True,
        verbose_name=_("Rolle"),
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Aktiv"))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Reihenfolge"))
    default_play_account = models.ForeignKey(
        "MinecraftPlayAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_stations",
        verbose_name=_("Standard-Spiel-Slot"),
    )
    note = models.CharField(max_length=255, blank=True, verbose_name=_("Notiz"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = _("Station (PC)")
        verbose_name_plural = _("Stationen (PCs)")

    def __str__(self):
        return self.name

    def supports_play(self) -> bool:
        return self.role in (self.ROLE_PLAY, self.ROLE_BOTH)

    def supports_builder(self) -> bool:
        return self.role in (self.ROLE_BUILDER, self.ROLE_BOTH)


class MinecraftMsAllowlistEntry(models.Model):
    """Allowed Microsoft logins for session freigabe (global or per station)."""

    ms_username = models.CharField(
        max_length=32,
        db_index=True,
        verbose_name=_("Microsoft-Login"),
    )
    station = models.ForeignKey(
        MinecraftStation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ms_allowlist_entries",
        verbose_name=_("Nur für Station"),
        help_text=_("Leer = global für alle Stationen."),
    )
    note = models.CharField(max_length=255, blank=True, verbose_name=_("Notiz"))
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Aktiv"))
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Angelegt von"),
    )

    class Meta:
        ordering = ["ms_username", "station_id"]
        verbose_name = _("MS-Allowlist-Eintrag")
        verbose_name_plural = _("MS-Allowlist")
        constraints = [
            models.UniqueConstraint(
                fields=["ms_username", "station"],
                name="minecraft_ms_allowlist_user_station_uniq",
            ),
        ]

    def __str__(self):
        scope = self.station.name if self.station_id else "global"
        return f"{self.ms_username} ({scope})"

    def save(self, *args, **kwargs):
        self.ms_username = (self.ms_username or "").strip()
        super().save(*args, **kwargs)


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
    """Cuboid WorldGuard region managed from Stadtsteuerung, linked to Bau-Accounts.

    Master regions may be permanently assigned to a TOP group (api.Group without
    parent). Subregions reference a master via ``parent`` and must lie inside the
    master cuboid; TOP operators may manage only those subregions.
    """

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
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subregions",
        verbose_name=_("Master-Region"),
        help_text=_(
            "Leer = Master-Region. Gesetzt = Subregion innerhalb der Master-Bounds."
        ),
    )
    assigned_to_group = models.ForeignKey(
        "api.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_protected_regions",
        verbose_name=_("TOP-Gruppe"),
        help_text=_(
            "Nur bei Master-Regionen: permanente Zuordnung zur TOP-Gruppe. "
            "Subregionen erben die Ownership über die Master-Region."
        ),
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Sortierung"),
        help_text=_("Reihenfolge in der Liste (Master untereinander, Subs je Master)."),
    )
    min_x = models.IntegerField(verbose_name=_("Min X"))
    min_y = models.IntegerField(default=-64, verbose_name=_("Min Y"))
    min_z = models.IntegerField(verbose_name=_("Min Z"))
    max_x = models.IntegerField(verbose_name=_("Max X"))
    max_y = models.IntegerField(default=320, verbose_name=_("Max Y"))
    max_z = models.IntegerField(verbose_name=_("Max Z"))
    spawn_x = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Spawn X"),
        help_text=_("Optionaler Session-Spawn. Leer = automatische Cuboid-Mitte."),
    )
    spawn_y = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Spawn Y"),
    )
    spawn_z = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Spawn Z"),
    )
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
        ordering = ["sort_order", "region_id"]
        verbose_name = _("Geschützte Region")
        verbose_name_plural = _("Geschützte Regionen")

    def __str__(self):
        label = (self.display_name or "").strip() or self.region_id
        return f"{label} ({self.region_id})"

    @property
    def is_master(self) -> bool:
        return self.parent_id is None

    @property
    def region_kind(self) -> str:
        return "master" if self.is_master else "sub"

    def effective_top_group(self):
        """TOP group owning this region (direct for master, inherited for sub)."""
        if self.parent_id:
            return self.parent.assigned_to_group
        return self.assigned_to_group

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

    @property
    def has_custom_spawn(self) -> bool:
        return (
            self.spawn_x is not None
            and self.spawn_y is not None
            and self.spawn_z is not None
        )

    def contains_point(self, x: int, y: int, z: int) -> bool:
        """True if block coordinates lie inside this region's cuboid."""
        return self.contains_bounds(x, y, z, x, y, z)

    def overlaps_bounds(
        self,
        min_x: int,
        min_y: int,
        min_z: int,
        max_x: int,
        max_y: int,
        max_z: int,
    ) -> bool:
        """True if cuboids share interior volume (touching faces is allowed)."""
        a_min_x, a_min_y, a_min_z, a_max_x, a_max_y, a_max_z = self.normalized_bounds()
        b_min_x, b_min_y, b_min_z = (
            min(min_x, max_x),
            min(min_y, max_y),
            min(min_z, max_z),
        )
        b_max_x, b_max_y, b_max_z = (
            max(min_x, max_x),
            max(min_y, max_y),
            max(min_z, max_z),
        )
        return (
            a_min_x < b_max_x
            and a_max_x > b_min_x
            and a_min_y < b_max_y
            and a_max_y > b_min_y
            and a_min_z < b_max_z
            and a_max_z > b_min_z
        )

    def find_overlapping_peer(self):
        """
        Another region in the same world and sibling group that overlaps.

        Masters are checked against other masters; subs against siblings under
        the same parent. Touching edges are OK.
        """
        qs = (
            type(self)
            .objects.filter(world=self.world, parent_id=self.parent_id)
            .only(
                "region_id",
                "min_x",
                "min_y",
                "min_z",
                "max_x",
                "max_y",
                "max_z",
            )
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        bounds = self.normalized_bounds()
        for other in qs:
            if other.overlaps_bounds(*bounds):
                return other
        return None

    def contains_bounds(
        self,
        min_x: int,
        min_y: int,
        min_z: int,
        max_x: int,
        max_y: int,
        max_z: int,
    ) -> bool:
        """True if the given cuboid lies fully inside this region's bounds."""
        a_min_x, a_min_y, a_min_z, a_max_x, a_max_y, a_max_z = self.normalized_bounds()
        b_min_x, b_min_y, b_min_z = (
            min(min_x, max_x),
            min(min_y, max_y),
            min(min_z, max_z),
        )
        b_max_x, b_max_y, b_max_z = (
            max(min_x, max_x),
            max(min_y, max_y),
            max(min_z, max_z),
        )
        return (
            b_min_x >= a_min_x
            and b_min_y >= a_min_y
            and b_min_z >= a_min_z
            and b_max_x <= a_max_x
            and b_max_y <= a_max_y
            and b_max_z <= a_max_z
        )

    def clean(self):
        from django.core.exceptions import ValidationError

        errors: dict[str, str] = {}

        if self.parent_id:
            parent = self.parent
            if parent is None:
                errors["parent"] = _("Master-Region nicht gefunden.")
            else:
                if parent.parent_id is not None:
                    errors["parent"] = _(
                        "Subregionen dürfen nur einer Master-Region (ohne Parent) "
                        "untergeordnet sein."
                    )
                if self.pk and parent.pk == self.pk:
                    errors["parent"] = _("Eine Region kann nicht ihr eigener Parent sein.")
                if self.assigned_to_group_id:
                    errors["assigned_to_group"] = _(
                        "TOP-Zuordnung nur bei Master-Regionen; "
                        "Subregionen erben über den Parent."
                    )
                if parent.world and self.world and parent.world != self.world:
                    errors["world"] = _(
                        "Subregion muss in derselben Welt wie die Master-Region liegen."
                    )
                if not parent.contains_bounds(*self.normalized_bounds()):
                    errors["min_x"] = _(
                        "Subregion muss vollständig innerhalb der Master-Region liegen."
                    )
        elif self.assigned_to_group_id:
            group = self.assigned_to_group
            if group is not None and group.parent_id is not None:
                errors["assigned_to_group"] = _(
                    "Nur TOP-Gruppen (ohne übergeordnete Gruppe) dürfen zugewiesen werden."
                )

        if self.pk and not self.parent_id:
            # Prevent shrinking a master so existing subregions fall outside.
            for sub in type(self).objects.filter(parent_id=self.pk).only(
                "min_x", "min_y", "min_z", "max_x", "max_y", "max_z", "region_id"
            ):
                if not self.contains_bounds(*sub.normalized_bounds()):
                    errors["min_x"] = _(
                        "Master-Bounds würden Subregion „%(id)s“ ausschließen."
                    ) % {"id": sub.region_id}
                    break

        spawn_vals = (self.spawn_x, self.spawn_y, self.spawn_z)
        if any(v is not None for v in spawn_vals) and any(v is None for v in spawn_vals):
            errors["spawn_x"] = _(
                "Spawn-Punkt: X, Y und Z müssen zusammen gesetzt werden (oder alle leer)."
            )
        elif self.has_custom_spawn:
            if not self.contains_point(self.spawn_x, self.spawn_y, self.spawn_z):
                errors["spawn_x"] = _(
                    "Spawn-Punkt muss innerhalb der Regions-Bounds liegen."
                )

        peer = self.find_overlapping_peer()
        if peer is not None:
            if self.parent_id:
                errors["min_x"] = _(
                    "Subregion überlappt mit Geschwister-Region „%(id)s“."
                ) % {"id": peer.region_id}
            else:
                errors["min_x"] = _(
                    "Master-Region überlappt mit anderer Master-Region „%(id)s“."
                ) % {"id": peer.region_id}

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        # Skip full_clean for RCON sync metadata updates (avoids blocking on
        # legacy overlaps when only member-sync timestamps change).
        skip_clean = False
        if update_fields is not None:
            allowed = {
                "synced_members",
                "last_synced_at",
                "last_sync_error",
                "updated_at",
            }
            skip_clean = set(update_fields).issubset(allowed)
        if not skip_clean:
            self.full_clean()
        return super().save(*args, **kwargs)


class MinecraftGrantCatalogItem(models.Model):
    """
    Generic grant catalog for Stadtsteuerung (VehiclesPlus garage, diamonds, tickets, …).

    RCON templates may use ``{player}``, ``{model}``, ``{quantity}``, ``{slug}``.
    """

    KIND_VEHICLE_GARAGE = "vehicle_garage"
    KIND_INVENTORY = "inventory"
    KIND_CURRENCY = "currency"
    KIND_OTHER = "other"
    KIND_CHOICES = [
        (KIND_VEHICLE_GARAGE, _("Fahrzeug (Garage)")),
        (KIND_INVENTORY, _("Inventar-Item")),
        (KIND_CURRENCY, _("Währung / Guthaben")),
        (KIND_OTHER, _("Sonstiges")),
    ]

    slug = models.SlugField(max_length=64, unique=True, verbose_name=_("Slug"))
    name = models.CharField(max_length=128, verbose_name=_("Anzeigename"))
    kind = models.CharField(
        max_length=32,
        choices=KIND_CHOICES,
        default=KIND_VEHICLE_GARAGE,
        db_index=True,
        verbose_name=_("Art"),
    )
    enabled = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    sort_order = models.PositiveIntegerField(default=100, verbose_name=_("Sortierung"))
    applies_to_player = models.BooleanField(
        default=True,
        verbose_name=_("Spieler-Sessions"),
    )
    applies_to_builder = models.BooleanField(
        default=True,
        verbose_name=_("Bau-Sessions"),
    )
    model_id = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Modell-ID"),
        help_text=_("z. B. VehiclesPlus ExampleBike — Platzhalter {model}."),
    )
    quantity_default = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("Standard-Menge"),
    )
    velos_cost = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Velos-Kosten"),
        help_text=_("0 = kostenlose Session-Vergabe; >0 = Einlösung vom Radler-Konto."),
    )
    repair_velos_cost = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Reparatur-Velos"),
        help_text=_("Admin-Reparatur (VehiclesPlus); 0 = keine Reparatur-Aktion."),
    )
    rcon_grant_template = models.CharField(
        max_length=512,
        verbose_name=_("RCON Vergabe"),
        help_text=_("z. B. v give {player} {model}"),
    )
    rcon_revoke_template = models.CharField(
        max_length=512,
        blank=True,
        verbose_name=_("RCON Entfernen"),
        help_text=_(
            "Optional beim Slot-Clear. Leer = nur DB-Status; "
            "Ingame-Garage ggf. manuell/andere Mittel."
        ),
    )
    rcon_repair_template = models.CharField(
        max_length=512,
        blank=True,
        verbose_name=_("RCON Reparatur"),
        help_text=_("z. B. v repair {player}. Leer = Art ohne Admin-Reparatur."),
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name=_("Hinweis"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = _("Vergabe-Katalogeintrag")
        verbose_name_plural = _("Vergabe-Katalog")

    def __str__(self) -> str:
        return self.name


class MinecraftGrantRecord(models.Model):
    """Active/revoked grant of a catalog item on a play/builder slot."""

    STATUS_ACTIVE = "active"
    STATUS_REVOKED = "revoked"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, _("Aktiv")),
        (STATUS_REVOKED, _("Widerrufen")),
    ]

    SOURCE_SESSION = "session_grant"
    SOURCE_VELOS = "velos_redeem"
    SOURCE_CHOICES = [
        (SOURCE_SESSION, _("Session-Vergabe")),
        (SOURCE_VELOS, _("Velos-Einlösung")),
    ]

    catalog_item = models.ForeignKey(
        MinecraftGrantCatalogItem,
        on_delete=models.CASCADE,
        related_name="records",
        verbose_name=_("Katalog"),
    )
    account_name = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_("Account-Slot"),
    )
    account_type = models.CharField(
        max_length=16,
        choices=MCSession.ACCOUNT_TYPE_CHOICES,
        verbose_name=_("Account-Typ"),
    )
    session = models.ForeignKey(
        MCSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grant_records",
        verbose_name=_("Session"),
    )
    ms_username = models.CharField(max_length=32, blank=True, verbose_name=_("MS-Login"))
    source = models.CharField(
        max_length=16,
        choices=SOURCE_CHOICES,
        default=SOURCE_SESSION,
        verbose_name=_("Herkunft"),
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        verbose_name=_("Status"),
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name=_("Menge"))
    velos_charged = models.PositiveIntegerField(default=0, verbose_name=_("Velos abgezogen"))
    granted_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Vergeben"))
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Widerrufen"))
    granted_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Vergeben von"),
    )
    last_error = models.TextField(blank=True, verbose_name=_("Letzter Fehler"))

    class Meta:
        ordering = ["-granted_at"]
        verbose_name = _("Vergabe-Eintrag")
        verbose_name_plural = _("Vergabe-Einträge")
        indexes = [
            models.Index(
                fields=["account_name", "status"],
                name="minecraft_grant_acct_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.account_name}: {self.catalog_item_id} [{self.status}]"
