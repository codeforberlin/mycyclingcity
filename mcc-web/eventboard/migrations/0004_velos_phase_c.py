# Generated manually for Velos Phase C — Eventboard km → Velos

from django.db import migrations, models
from decimal import Decimal


def _km_to_velos(km):
    if km is None:
        return None
    return int(float(km) * 100)


def migrate_eventboard_km_to_velos(apps, schema_editor):
    Event = apps.get_model('eventboard', 'Event')
    GroupEventStatus = apps.get_model('eventboard', 'GroupEventStatus')
    LeafGroupEventContribution = apps.get_model('eventboard', 'LeafGroupEventContribution')
    EventHistory = apps.get_model('eventboard', 'EventHistory')

    for event in Event.objects.all():
        event.target_velos = _km_to_velos(event.target_distance_km)
        event.save(update_fields=['target_velos'])

    for status in GroupEventStatus.objects.all():
        status.current_velos = _km_to_velos(status.current_distance_km) or 0
        status.start_velos_offset = _km_to_velos(status.start_km_offset) or 0
        status.save(update_fields=['current_velos', 'start_velos_offset'])

    for contribution in LeafGroupEventContribution.objects.all():
        contribution.current_event_velos = _km_to_velos(contribution.current_event_distance) or 0
        contribution.save(update_fields=['current_event_velos'])

    for entry in EventHistory.objects.all():
        entry.total_velos = _km_to_velos(entry.total_distance_km) or 0
        entry.save(update_fields=['total_velos'])


def drop_contribution_distance_indexes(apps, schema_editor):
    """
    SQLite cannot drop a column that is still referenced by an index.
    Legacy DBs may use api_* index names from the pre-eventboard app split.
    """
    connection = schema_editor.connection
    table = 'eventboard_leafgroupeventcontribution'
    legacy_names = (
        'eventboard__event_i_34e159_idx',
        'api_leafgro_event_i_b62a30_idx',
    )
    with connection.cursor() as cursor:
        for name in legacy_names:
            if connection.vendor == 'sqlite':
                cursor.execute(f'DROP INDEX IF EXISTS "{name}"')
            else:
                cursor.execute(f'DROP INDEX IF EXISTS {connection.ops.quote_name(name)}')

        if connection.vendor == 'sqlite':
            cursor.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=%s",
                [table],
            )
            for name, sql in cursor.fetchall():
                if sql and 'current_event_distance' in sql:
                    cursor.execute(f'DROP INDEX "{name}"')


class Migration(migrations.Migration):

    dependencies = [
        ('eventboard', '0003_add_unique_name_constraint'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='target_velos',
            field=models.IntegerField(
                blank=True,
                null=True,
                verbose_name='Velos-Ziel',
                help_text='Gesamtes Velos-Ziel für dieses Event (optional). Wird für Fortschrittsanzeige verwendet.',
            ),
        ),
        migrations.AddField(
            model_name='groupeventstatus',
            name='current_velos',
            field=models.IntegerField(default=0, verbose_name='Aktuelle Velos'),
        ),
        migrations.AddField(
            model_name='groupeventstatus',
            name='start_velos_offset',
            field=models.IntegerField(default=0, verbose_name='Start-Offset (Velos)'),
        ),
        migrations.AddField(
            model_name='leafgroupeventcontribution',
            name='current_event_velos',
            field=models.IntegerField(default=0, verbose_name='Aktuelle Event-Velos'),
        ),
        migrations.AddField(
            model_name='eventhistory',
            name='total_velos',
            field=models.IntegerField(default=0, verbose_name='Gesammelte Velos'),
        ),
        migrations.RunPython(migrate_eventboard_km_to_velos, migrations.RunPython.noop),
        migrations.RunPython(drop_contribution_distance_indexes, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='event',
            name='target_distance_km',
        ),
        migrations.RemoveField(
            model_name='groupeventstatus',
            name='current_distance_km',
        ),
        migrations.RemoveField(
            model_name='groupeventstatus',
            name='start_km_offset',
        ),
        migrations.RemoveField(
            model_name='leafgroupeventcontribution',
            name='current_event_distance',
        ),
        migrations.RemoveField(
            model_name='eventhistory',
            name='total_distance_km',
        ),
        migrations.AddIndex(
            model_name='leafgroupeventcontribution',
            index=models.Index(
                fields=['event', '-current_event_velos'],
                name='eventboard__event_velos_idx',
            ),
        ),
    ]
