# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models.py
# @note    Luanti integration models (accounts, sessions, shop, city, arena, stations).

from __future__ import annotations

import secrets
import uuid

from django.conf import settings as django_settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class LuantiIntegrationConfig(models.Model):
    """Singleton configuration for the Luanti bridge."""

    session_active_hint = models.CharField(
        max_length=200,
        default="Session ist aktiv",
        blank=True,
        verbose_name=_("Hinweis aktive Session"),
    )
    default_session_minutes = models.PositiveIntegerField(
        default=45,
        verbose_name=_("Standard-Sessiondauer (Min.)"),
    )
    session_add_minutes = models.PositiveIntegerField(
        default=15,
        verbose_name=_("Zeit hinzufügen/kürzen (Min.)"),
    )
    session_min_minutes = models.PositiveIntegerField(
        default=5,
        verbose_name=_("Standard-Minimum Dauer (Min.)"),
        help_text=_("Fallback, wenn am Account kein Minimum gesetzt ist."),
    )
    session_max_minutes = models.PositiveIntegerField(
        default=180,
        verbose_name=_("Standard-Maximum Dauer (Min.)"),
        help_text=_("Fallback, wenn am Account kein Maximum gesetzt ist."),
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = _("Luanti-Konfiguration")
        verbose_name_plural = _("Luanti-Konfiguration")
        permissions = [
            ("access_luanti_control", _("Control öffnen")),
            ("access_luanti_city", _("Stadtsteuerung öffnen")),
            ("access_luanti_shop", _("Shop öffnen")),
            ("access_luanti_arena", _("Arena/Loren öffnen")),
            ("manage_luanti_accounts", _("Accounts verwalten")),
            ("manage_luanti_sessions", _("Sessions verwalten")),
            ("manage_luanti_stations", _("Stationen verwalten")),
        ]

    def __str__(self):
        return "Luanti Integration Config"

    @classmethod
    def get_config(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class LuantiBridgeConnection(models.Model):
    """Tracks MCC Luanti bridge presence (HTTP heartbeat / WebSocket)."""

    server_id = models.CharField(max_length=64, primary_key=True, verbose_name=_("Server-ID"))
    is_connected = models.BooleanField(default=False, verbose_name=_("Verbunden"))
    connected_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Verbunden seit"))
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Zuletzt gesehen"))

    class Meta:
        verbose_name = _("Bridge-Verbindung")
        verbose_name_plural = _("Bridge-Verbindungen")

    def __str__(self):
        return self.server_id


class LuantiPendingCommand(models.Model):
    """HTTP fallback queue when no Luanti WebSocket bridge is connected."""

    server_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        verbose_name=_("Server-ID"),
        help_text=_("Leer = für alle Server."),
    )
    payload = models.JSONField(verbose_name=_("Payload"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt"))
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Zugestellt"))

    class Meta:
        ordering = ["id"]
        verbose_name = _("Ausstehender Bridge-Befehl")
        verbose_name_plural = _("Ausstehende Bridge-Befehle")
        indexes = [
            models.Index(fields=["delivered_at", "id"]),
        ]

    def __str__(self):
        cmd = ""
        if isinstance(self.payload, dict):
            cmd = str(self.payload.get("type") or "")
        return f"{cmd or 'cmd'}@{self.server_id or '*'}"


class LuantiAccount(models.Model):
    """Unified play/build account (mode switches privileges + inventory)."""

    MODE_PLAY = "play"
    MODE_BUILD = "build"
    MODE_WATCH = "watch"
    MODE_CHOICES = [
        (MODE_PLAY, _("Spielen")),
        (MODE_BUILD, _("Bauen")),
        (MODE_WATCH, _("Zuschauen")),
    ]

    login_name = models.CharField(
        max_length=32,
        unique=True,
        verbose_name=_("Login-Name"),
        help_text=_("Luanti-Spielername (ohne Leerzeichen)."),
    )
    id_tag = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("RFID-UID"),
        help_text=_("Token für RFID-Session-Start."),
    )
    display_name = models.CharField(max_length=64, blank=True, verbose_name=_("Anzeigename"))
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Aktiv"))
    allowed_modes = models.JSONField(
        default=list,
        verbose_name=_("Erlaubte Modi"),
        help_text=_('Liste z. B. ["play","build","watch"]. Leer = alle drei.'),
    )
    default_mode = models.CharField(
        max_length=16,
        choices=MODE_CHOICES,
        default=MODE_PLAY,
        verbose_name=_("Standard-Modus"),
    )
    session_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Session-Dauer (Min.)"),
        help_text=_("Leer = globaler Standard."),
    )
    session_duration_min_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Min. Dauer (Min.)"),
        help_text=_("Untergrenze für Start/Kürzung. Leer = globaler Standard."),
    )
    session_duration_max_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Max. Dauer (Min.)"),
        help_text=_("Obergrenze für Start/Verlängerung. Leer = globaler Standard."),
    )
    session_add_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Zeit-Schrittgröße (Min.)"),
        help_text=_(
            "Schrittweite der ±-Buttons auf Session-Kacheln. Leer = globaler Standard."
        ),
    )
    session_unlimited = models.BooleanField(default=False, verbose_name=_("Unbegrenzte Session"))
    login_password = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Login-Passwort"),
        help_text=_(
            "Klartext für Admin-Anzeige und Linux-Station-Launcher. "
            "Wird auch auf dem Luanti-Server gesetzt."
        ),
    )
    password_provisioned = models.BooleanField(
        default=False,
        verbose_name=_("Passwort auf Server gesetzt"),
    )
    password_last_set_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Passwort gesetzt am"),
    )
    WALLET_FIXED = "fixed"
    WALLET_AUTO_LEAF = "auto_leaf"
    WALLET_POOL = "pool"
    WALLET_MODE_CHOICES = [
        (WALLET_FIXED, _("Festes Wallet")),
        (WALLET_AUTO_LEAF, _("Auto: Leaf mit meistem Spendable")),
        (WALLET_POOL, _("Pool: Heimat-Gruppe")),
    ]

    assigned_to_group = models.ForeignKey(
        "api.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="luanti_accounts",
        verbose_name=_("Heimat-Gruppe"),
        help_text=_("Organisation / TOP (Filter, Pool-Modus)."),
    )
    active_wallet = models.ForeignKey(
        "api.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="luanti_wallet_accounts",
        verbose_name=_("Aktives Wallet"),
        help_text=_("Gruppe, deren velos_spendable belastet wird (bei Modus „Fest“)."),
    )
    wallet_mode = models.CharField(
        max_length=16,
        choices=WALLET_MODE_CHOICES,
        default=WALLET_FIXED,
        verbose_name=_("Wallet-Modus"),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "login_name"]
        verbose_name = _("Luanti-Account")
        verbose_name_plural = _("Luanti-Accounts")

    def __str__(self):
        return self.display_name or self.login_name

    @property
    def label(self) -> str:
        return self.display_name or self.login_name

    def resolved_allowed_modes(self) -> list[str]:
        modes = self.allowed_modes or []
        if not modes:
            return [self.MODE_PLAY, self.MODE_BUILD, self.MODE_WATCH]
        return [m for m in modes if m in dict(self.MODE_CHOICES)]

    def save(self, *args, **kwargs):
        self.login_name = (self.login_name or "").strip()
        self.id_tag = (self.id_tag or "").strip()
        if not self.id_tag and self.login_name:
            self.id_tag = self.login_name
        if not self.login_name and self.id_tag:
            self.login_name = self.id_tag
        super().save(*args, **kwargs)


class LuantiSession(models.Model):
    """Active/history session for a Luanti account."""

    STATUS_READY = "READY"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_PAUSED = "PAUSED"
    STATUS_FINISHED = "FINISHED"
    STATUS_CHOICES = [
        (STATUS_READY, _("Bereit")),
        (STATUS_ACTIVE, _("Aktiv")),
        (STATUS_PAUSED, _("Pausiert")),
        (STATUS_FINISHED, _("Beendet")),
    ]
    OPEN_STATUSES = (STATUS_ACTIVE, STATUS_PAUSED)

    SOURCE_ADMIN = "admin"
    SOURCE_RFID = "rfid"
    SOURCE_SYSTEM = "system"
    SOURCE_CHOICES = [
        (SOURCE_ADMIN, _("Admin-GUI")),
        (SOURCE_RFID, _("RFID-Scan")),
        (SOURCE_SYSTEM, _("System")),
    ]

    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        LuantiAccount,
        on_delete=models.CASCADE,
        related_name="sessions",
        verbose_name=_("Account"),
    )
    login_name = models.CharField(max_length=32, db_index=True, verbose_name=_("Login-Name"))
    mode = models.CharField(
        max_length=16,
        choices=LuantiAccount.MODE_CHOICES,
        default=LuantiAccount.MODE_PLAY,
        verbose_name=_("Modus"),
    )
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
        verbose_name=_("Quelle"),
    )
    timestamp_start = models.DateTimeField(default=timezone.now, verbose_name=_("Start"))
    duration_minutes = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Dauer (Minuten)"),
        help_text=_("0 = unbegrenzt."),
    )
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name=_("Geplantes Ende"))
    paused_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Pausiert seit"))
    remaining_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Restzeit bei Pause (Sek.)"),
        help_text=_("Gespeicherte Restzeit während STATUS_PAUSED."),
    )
    timestamp_end = models.DateTimeField(null=True, blank=True, verbose_name=_("Tatsächliches Ende"))
    station = models.ForeignKey(
        "LuantiStation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name=_("Station"),
    )
    started_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    wallet_group = models.ForeignKey(
        "api.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="luanti_session_wallets",
        verbose_name=_("Session-Wallet"),
        help_text=_("Optional: überschreibt Account-Wallet nur für diese Session."),
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-timestamp_start"]
        verbose_name = _("Luanti-Session")
        verbose_name_plural = _("Luanti-Sessions")

    def __str__(self):
        return f"{self.login_name} ({self.mode}/{self.status})"

    @property
    def is_active(self) -> bool:
        return self.status == self.STATUS_ACTIVE

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    @property
    def is_paused(self) -> bool:
        return self.status == self.STATUS_PAUSED


class LuantiPlayerInventory(models.Model):
    """Per-account inventory payload for play or build mode."""

    account = models.ForeignKey(
        LuantiAccount,
        on_delete=models.CASCADE,
        related_name="inventories",
        verbose_name=_("Account"),
    )
    mode = models.CharField(
        max_length=16,
        choices=[
            (LuantiAccount.MODE_PLAY, _("Spielen")),
            (LuantiAccount.MODE_BUILD, _("Bauen")),
        ],
        verbose_name=_("Modus"),
    )
    payload = models.JSONField(default=list, verbose_name=_("Inventar (JSON)"))
    revision = models.PositiveIntegerField(default=0, verbose_name=_("Revision"))
    updated_at = models.DateTimeField(auto_now=True)
    last_server_id = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = _("Spieler-Inventar")
        verbose_name_plural = _("Spieler-Inventare")
        constraints = [
            models.UniqueConstraint(
                fields=["account", "mode"],
                name="luanti_inventory_account_mode_unique",
            ),
        ]

    def __str__(self):
        return f"{self.account.login_name}:{self.mode} r{self.revision}"


class LuantiShopCategory(models.Model):
    slug = models.SlugField(max_length=64, unique=True, verbose_name=_("Slug"))
    name = models.CharField(max_length=64, verbose_name=_("Name"))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    enabled = models.BooleanField(default=True, verbose_name=_("Aktiv"))

    class Meta:
        ordering = ["sort_order", "slug"]
        verbose_name = _("Shop-Kategorie")
        verbose_name_plural = _("Shop-Kategorien")

    def __str__(self):
        return self.name


class LuantiShopItem(models.Model):
    category = models.ForeignKey(
        LuantiShopCategory,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Kategorie"),
    )
    item_name = models.CharField(
        max_length=128,
        verbose_name=_("Item-Name"),
        help_text=_("Luanti itemstring, z. B. mcl_core:diamond"),
    )
    display_name = models.CharField(max_length=128, blank=True, verbose_name=_("Anzeigename"))
    buy_price_velos = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("Kaufpreis (Velos)"),
    )
    stack_size = models.PositiveIntegerField(default=1, verbose_name=_("Stack-Größe"))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    enabled = models.BooleanField(default=True, verbose_name=_("Aktiv"))

    class Meta:
        ordering = ["category", "sort_order", "item_name"]
        verbose_name = _("Shop-Artikel")
        verbose_name_plural = _("Shop-Artikel")
        constraints = [
            models.UniqueConstraint(
                fields=["category", "item_name"],
                name="luanti_shop_item_unique",
            ),
        ]

    def __str__(self):
        label = self.display_name or self.item_name
        return f"{label} ({self.buy_price_velos} Velos)"


class LuantiShopPurchaseCredit(models.Model):
    group = models.ForeignKey(
        "api.Group",
        on_delete=models.CASCADE,
        related_name="luanti_shop_credits",
        verbose_name=_("Gruppe"),
    )
    item_name = models.CharField(max_length=128, verbose_name=_("Item-Name"))
    quantity = models.PositiveIntegerField(default=0, verbose_name=_("Restmenge"))

    class Meta:
        verbose_name = _("Shop-Kaufguthaben")
        verbose_name_plural = _("Shop-Kaufguthaben")
        constraints = [
            models.UniqueConstraint(
                fields=["group", "item_name"],
                name="luanti_shop_credit_unique",
            ),
        ]

    def __str__(self):
        return f"{self.group} {self.item_name}: {self.quantity}"


class LuantiShopTransaction(models.Model):
    SIDE_BUY = "buy"
    SIDE_SELL = "sell"
    SIDE_CHOICES = [(SIDE_BUY, _("Kauf")), (SIDE_SELL, _("Verkauf"))]

    client_tx_id = models.CharField(max_length=64, unique=True, verbose_name=_("Client-Tx-ID"))
    side = models.CharField(max_length=8, choices=SIDE_CHOICES)
    login_name = models.CharField(max_length=32, db_index=True)
    group = models.ForeignKey(
        "api.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="luanti_shop_txs",
    )
    item_name = models.CharField(max_length=128)
    quantity = models.PositiveIntegerField(default=1)
    velos_delta = models.IntegerField(verbose_name=_("Velos-Delta"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Shop-Transaktion")
        verbose_name_plural = _("Shop-Transaktionen")


class LuantiCityPreset(models.Model):
    """Semantic city/world control steps executed by the Lua bridge."""

    CATEGORY_WORLD = "world"
    CATEGORY_OTHER = "other"
    CATEGORY_CHOICES = [
        (CATEGORY_WORLD, _("Welt & Wetter")),
        (CATEGORY_OTHER, _("Sonstiges")),
    ]

    slug = models.SlugField(max_length=64, unique=True, verbose_name=_("Slug"))
    name = models.CharField(max_length=64, verbose_name=_("Name"))
    category = models.CharField(
        max_length=16,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_WORLD,
        verbose_name=_("Kategorie"),
    )
    description = models.TextField(blank=True, verbose_name=_("Beschreibung"))
    steps = models.JSONField(
        default=list,
        verbose_name=_("Schritte"),
        help_text=_(
            'Semantische Bridge-Commands, z. B. [{"op":"set_time","value":6000}]. '
            "Im Preset-Editor als Zeilen bearbeitbar — nicht im Code verdrahtet."
        ),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    enabled = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    is_system = models.BooleanField(
        default=False,
        verbose_name=_("System-Preset"),
        help_text=_("Geschützt: Löschen/Slug nur mit System-Rechten."),
    )
    moderator_can_run = models.BooleanField(
        default=False,
        verbose_name=_("Moderator darf ausführen"),
        help_text=_("Erlaubt Ausführen auch ohne change-Recht (Stadtsteuerung)."),
    )
    requires_confirmation = models.BooleanField(default=True, verbose_name=_("Bestätigung"))
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    last_run_success = models.BooleanField(null=True, blank=True)
    last_run_output = models.TextField(blank=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = _("Stadt-Preset")
        verbose_name_plural = _("Stadt-Presets")
        permissions = [
            ("run_citypreset", _("Stadt-Preset ausführen")),
            ("change_system_citypreset", _("System-Stadt-Preset bearbeiten")),
            ("delete_system_citypreset", _("System-Stadt-Preset löschen")),
        ]

    def __str__(self):
        return self.name

    @property
    def step_count(self) -> int:
        return len(self.steps or [])


class LuantiProtectedRegion(models.Model):
    region_id = models.SlugField(max_length=64, unique=True, verbose_name=_("Region-ID"))
    display_name = models.CharField(max_length=120, blank=True, verbose_name=_("Anzeigename"))
    world = models.CharField(max_length=64, default="world", verbose_name=_("Welt"))
    min_x = models.IntegerField()
    min_y = models.IntegerField(default=-64)
    min_z = models.IntegerField()
    max_x = models.IntegerField()
    max_y = models.IntegerField(default=320)
    max_z = models.IntegerField()
    protect_build = models.BooleanField(default=True, verbose_name=_("Bauen schützen"))
    assigned_to_group = models.ForeignKey(
        "api.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="luanti_regions",
        verbose_name=_("TOP-Gruppe"),
    )
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "region_id"]
        verbose_name = _("Geschützte Region")
        verbose_name_plural = _("Geschützte Regionen")

    def __str__(self):
        return self.display_name or self.region_id


class LuantiArenaMotionSettings(models.Model):
    """Singleton arena motion settings."""

    enabled = models.BooleanField(default=False, verbose_name=_("Arena aktiv"))
    default_speed = models.FloatField(default=3.0, verbose_name=_("Standardgeschwindigkeit"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Arena-Einstellungen")
        verbose_name_plural = _("Arena-Einstellungen")

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Luanti Arena Settings"


class LuantiArenaLane(models.Model):
    name = models.CharField(max_length=64, unique=True, verbose_name=_("Name"))
    sort_order = models.PositiveIntegerField(default=0)
    start_x = models.FloatField(default=0)
    start_y = models.FloatField(default=3)
    start_z = models.FloatField(default=0)
    direction_x = models.FloatField(default=1)
    direction_y = models.FloatField(default=0)
    direction_z = models.FloatField(default=0)
    enabled = models.BooleanField(default=True)
    assigned_account = models.ForeignKey(
        LuantiAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="arena_lanes",
    )

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = _("Arena-Spur")
        verbose_name_plural = _("Arena-Spuren")

    def __str__(self):
        return self.name


class LuantiWaitingPlayer(models.Model):
    """Online player waiting for admin session freigabe (reported by mcc_bridge)."""

    login_name = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        verbose_name=_("Login-Name"),
    )
    account = models.ForeignKey(
        LuantiAccount,
        on_delete=models.CASCADE,
        related_name="waiting_entries",
        verbose_name=_("Account"),
    )
    server_id = models.CharField(max_length=64, blank=True, verbose_name=_("Server-ID"))
    first_seen_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstmals gesehen"))
    last_seen_at = models.DateTimeField(auto_now=True, verbose_name=_("Zuletzt gesehen"))

    class Meta:
        ordering = ["-last_seen_at"]
        verbose_name = _("Wartender Spieler")
        verbose_name_plural = _("Wartende Spieler")

    def __str__(self):
        return self.login_name


class LuantiStation(models.Model):
    """Linux game PC managed from Django (desired config + heartbeat)."""

    name = models.CharField(max_length=64, unique=True, verbose_name=_("Name"))
    hostname = models.CharField(max_length=120, blank=True, verbose_name=_("Hostname"))
    location = models.CharField(max_length=120, blank=True, verbose_name=_("Standort"))
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Aktiv"))
    api_key = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
        verbose_name=_("API-Key"),
        help_text=_("Wird beim Speichern erzeugt, wenn leer."),
    )
    default_account = models.ForeignKey(
        LuantiAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_stations",
        verbose_name=_("Standard-Account"),
    )
    desired_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Desired Config"),
        help_text=_("Launcher/Server-Einstellungen für den Station-Agent."),
    )
    reported_config = models.JSONField(default=dict, blank=True, verbose_name=_("Gemeldete Config"))
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Zuletzt gesehen"))
    last_error = models.TextField(blank=True, verbose_name=_("Letzter Fehler"))
    sort_order = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = _("Station (PC)")
        verbose_name_plural = _("Stationen (PCs)")

    def __str__(self):
        return self.name

    def ensure_api_key(self) -> str:
        if not self.api_key:
            self.api_key = secrets.token_urlsafe(24)
        return self.api_key

    def save(self, *args, **kwargs):
        self.ensure_api_key()
        super().save(*args, **kwargs)
