# Generated manually for Velos Phase E — Game km target → Velos target

from django.db import migrations, models


def _km_to_velos(km):
    if not km:
        return 0
    return int(float(km) * 100)


def migrate_game_target_km_to_velos(apps, schema_editor):
    GameRoom = apps.get_model('game', 'GameRoom')
    for room in GameRoom.objects.all():
        room.current_target_velos = _km_to_velos(room.current_target_km)
        room.save(update_fields=['current_target_velos'])


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0003_alter_gameroom_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='gameroom',
            name='current_target_velos',
            field=models.IntegerField(
                default=0,
                verbose_name='Aktuelles Ziel (Velos)',
                help_text='Das aktuelle Velos-Ziel für dieses Spiel',
            ),
        ),
        migrations.RunPython(migrate_game_target_km_to_velos, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='gameroom',
            name='current_target_km',
        ),
        migrations.RenameField(
            model_name='gamesession',
            old_name='has_target_km',
            new_name='has_target_velos',
        ),
    ]
