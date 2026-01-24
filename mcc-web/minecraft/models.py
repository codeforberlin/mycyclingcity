from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class MinecraftOutboxEvent(models.Model):
    EVENT_UPDATE_PLAYER_COINS = "update_player_coins"
    EVENT_SYNC_ALL = "sync_all"

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    EVENT_TYPE_CHOICES = [
        (EVENT_UPDATE_PLAYER_COINS, _("Update Player Coins")),
        (EVENT_SYNC_ALL, _("Sync All Players")),
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

    def mark_processing(self):
        self.status = self.STATUS_PROCESSING
        self.attempts = self.attempts + 1
        self.save(update_fields=["status", "attempts"])


class MinecraftPlayerScoreboardSnapshot(models.Model):
    player_name = models.CharField(max_length=64, db_index=True)
    cyclist = models.ForeignKey(
        "api.Cyclist",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="minecraft_scoreboard_snapshots",
    )
    coins_total = models.PositiveIntegerField(default=0)
    coins_spendable = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=32, default="rcon")
    captured_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["player_name"]
        ordering = ["player_name"]
        verbose_name = _("Minecraft Scoreboard Snapshot")
        verbose_name_plural = _("Minecraft Scoreboard Snapshots")

    def __str__(self):
        return f"{self.player_name} ({self.coins_spendable}/{self.coins_total})"


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
