# Generated manually for team scoreboard v4

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0019_velos_travel_progress'),
        ('minecraft', '0003_velos_phase_f'),
    ]

    operations = [
        migrations.CreateModel(
            name='MinecraftIntegrationConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('team_display_name', models.CharField(default='Velo-Arena', help_text='Sidebar-Titel in Minecraft (ausgebare Velos)', max_length=64, verbose_name='Scoreboard-Anzeigename')),
                ('objective_spendable', models.CharField(blank=True, help_text='Leer = Wert aus Umgebungsvariable / settings.py', max_length=64, verbose_name='Objective-Slug')),
                ('sync_on_earn', models.BooleanField(default=True, verbose_name='Bei Velos-Earn synchronisieren')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Zuletzt aktualisiert')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Geändert von')),
            ],
            options={
                'verbose_name': 'Minecraft Integration Config',
                'verbose_name_plural': 'Minecraft Integration Config',
            },
        ),
        migrations.CreateModel(
            name='MinecraftTeamRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mc_username', models.CharField(db_index=True, max_length=100, verbose_name='Minecraft-Name')),
                ('is_active', models.BooleanField(default=True, verbose_name='Aktiv in Minecraft')),
                ('was_ever_registered', models.BooleanField(default=True, verbose_name='War schon einmal registriert')),
                ('registered_at', models.DateTimeField(auto_now_add=True, verbose_name='Registriert am')),
                ('deactivated_at', models.DateTimeField(blank=True, null=True, verbose_name='Deaktiviert am')),
                ('last_synced_at', models.DateTimeField(blank=True, null=True, verbose_name='Zuletzt synchronisiert')),
                ('last_sync_error', models.TextField(blank=True, verbose_name='Letzter Sync-Fehler')),
                ('group', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='minecraft_registration', to='api.group', verbose_name='Gruppe')),
                ('registered_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Registriert von')),
            ],
            options={
                'verbose_name': 'Minecraft Team Registration',
                'verbose_name_plural': 'Minecraft Team Registrations',
            },
        ),
        migrations.AddConstraint(
            model_name='minecraftteamregistration',
            constraint=models.UniqueConstraint(condition=models.Q(('is_active', True)), fields=('mc_username',), name='minecraft_unique_active_mc_username'),
        ),
        migrations.AlterField(
            model_name='minecraftoutboxevent',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('update_player_coins', 'Update Player Coins (deprecated)'),
                    ('update_group_velos', 'Update Group Velos (legacy)'),
                    ('sync_all', 'Sync All Groups (legacy)'),
                    ('register_team', 'Register Team'),
                    ('unregister_team', 'Unregister Team'),
                    ('update_team_velos', 'Update Team Velos'),
                    ('sync_registered_teams', 'Sync Registered Teams'),
                    ('ensure_objectives', 'Ensure Objectives'),
                ],
                max_length=64,
            ),
        ),
    ]
