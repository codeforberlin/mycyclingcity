# Generated manually — track real event kilometers alongside Velos.

from decimal import Decimal

from django.db import migrations, models


def drop_stale_distance_index_if_exists(apps, schema_editor):
    """0004 dropped this index in DB but left it in migration state."""
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute('DROP INDEX IF EXISTS "eventboard__event_i_34e159_idx"')


class Migration(migrations.Migration):

    dependencies = [
        ('eventboard', '0004_velos_phase_c'),
    ]

    operations = [
        # Legacy index from 0001 still in migration state after 0004 removed
        # current_event_distance; SQLite table rebuild in AddField would fail.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    drop_stale_distance_index_if_exists,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.RemoveIndex(
                    model_name='leafgroupeventcontribution',
                    name='eventboard__event_i_34e159_idx',
                ),
            ],
        ),
        migrations.AddField(
            model_name='groupeventstatus',
            name='current_event_km',
            field=models.DecimalField(
                decimal_places=5,
                default=Decimal('0.00000'),
                help_text='Während des Events erstrampelte Kilometer (real, unabhängig vom Radumfang)',
                max_digits=15,
                verbose_name='Aktuelle Event-km',
            ),
        ),
        migrations.AddField(
            model_name='leafgroupeventcontribution',
            name='current_event_km',
            field=models.DecimalField(
                decimal_places=5,
                default=Decimal('0.00000'),
                help_text='Die von dieser Leaf-Gruppe während des aktuellen Events erstrampelten Kilometer',
                max_digits=15,
                verbose_name='Aktuelle Event-km',
            ),
        ),
        migrations.AddField(
            model_name='eventhistory',
            name='total_km',
            field=models.DecimalField(
                decimal_places=5,
                default=Decimal('0.00000'),
                max_digits=15,
                verbose_name='Gesammelte Kilometer',
            ),
        ),
    ]
