# Generated manually for Velos Phase F — Minecraft group Velos snapshots

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_velos_phase_c_remove_coins'),
        ('minecraft', '0002_alter_minecraftoutboxevent_options_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='minecraftplayerscoreboardsnapshot',
            old_name='coins_total',
            new_name='velos_total',
        ),
        migrations.RenameField(
            model_name='minecraftplayerscoreboardsnapshot',
            old_name='coins_spendable',
            new_name='velos_spendable',
        ),
        migrations.AddField(
            model_name='minecraftplayerscoreboardsnapshot',
            name='group',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='minecraft_scoreboard_snapshots',
                to='api.group',
            ),
        ),
        migrations.AlterField(
            model_name='minecraftoutboxevent',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('update_player_coins', 'Update Player Coins (deprecated)'),
                    ('update_group_velos', 'Update Group Velos'),
                    ('sync_all', 'Sync All Groups'),
                ],
                max_length=64,
            ),
        ),
    ]
