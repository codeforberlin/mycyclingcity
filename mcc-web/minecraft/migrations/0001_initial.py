from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("api", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MinecraftOutboxEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("update_player_coins", "Update Player Coins"), ("sync_all", "Sync All Players")], max_length=64)),
                ("payload", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("done", "Done"), ("failed", "Failed")], default="pending", max_length=16)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MinecraftWorkerState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_running", models.BooleanField(default=False)),
                ("pid", models.CharField(blank=True, max_length=64)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("last_heartbeat", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Minecraft Worker State",
                "verbose_name_plural": "Minecraft Worker State",
            },
        ),
        migrations.CreateModel(
            name="MinecraftPlayerScoreboardSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("player_name", models.CharField(db_index=True, max_length=64)),
                ("coins_total", models.PositiveIntegerField(default=0)),
                ("coins_spendable", models.PositiveIntegerField(default=0)),
                ("source", models.CharField(default="rcon", max_length=32)),
                ("captured_at", models.DateTimeField(auto_now=True)),
                ("cyclist", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="minecraft_scoreboard_snapshots", to="api.cyclist")),
            ],
            options={
                "ordering": ["player_name"],
                "unique_together": {("player_name",)},
            },
        ),
    ]
