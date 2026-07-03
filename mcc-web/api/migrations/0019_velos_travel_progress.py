# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from decimal import Decimal

from django.db import migrations, models

from api.velos import track_reference_velos


def backfill_travel_velos_fields(apps, schema_editor):
    TravelTrack = apps.get_model('api', 'TravelTrack')
    Milestone = apps.get_model('api', 'Milestone')
    GroupTravelStatus = apps.get_model('api', 'GroupTravelStatus')
    LeafGroupTravelContribution = apps.get_model('api', 'LeafGroupTravelContribution')

    for track in TravelTrack.objects.all():
        track.goal_velos = track_reference_velos(track.total_length_km or 0)
        track.save(update_fields=['goal_velos'])

    for milestone in Milestone.objects.all():
        milestone.position_velos = track_reference_velos(milestone.distance_km or 0)
        milestone.save(update_fields=['position_velos'])

    for status in GroupTravelStatus.objects.all():
        velos = track_reference_velos(status.current_travel_distance or 0)
        offset = track_reference_velos(status.start_km_offset or 0)
        status.current_travel_velos = velos
        status.start_velos_offset = offset
        status.save(update_fields=['current_travel_velos', 'start_velos_offset'])

    for contribution in LeafGroupTravelContribution.objects.all():
        contribution.current_travel_velos = track_reference_velos(
            contribution.current_travel_distance or 0,
        )
        contribution.save(update_fields=['current_travel_velos'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0018_fezitty_game_workflow'),
    ]

    operations = [
        migrations.AddField(
            model_name='traveltrack',
            name='goal_velos',
            field=models.IntegerField(
                default=0,
                help_text='Referenz-Velos für die volle Streckenlänge (29"-Basis).',
                verbose_name='Ziel (Velos)',
            ),
        ),
        migrations.AddField(
            model_name='milestone',
            name='position_velos',
            field=models.IntegerField(
                default=0,
                help_text='Velos-Schwelle für diese Position (29"-Basis).',
                verbose_name='Velos-Marke',
            ),
        ),
        migrations.AddField(
            model_name='grouptravelstatus',
            name='current_travel_velos',
            field=models.IntegerField(
                default=0,
                help_text='Fairer Reise-Fortschritt basierend auf erstrampelten Velos.',
                verbose_name='Aktuelle Reise-Velos',
            ),
        ),
        migrations.AddField(
            model_name='grouptravelstatus',
            name='start_velos_offset',
            field=models.IntegerField(default=0, verbose_name='Start-Offset (Velos)'),
        ),
        migrations.AddField(
            model_name='leafgrouptravelcontribution',
            name='current_travel_velos',
            field=models.IntegerField(
                default=0,
                help_text='Velos-Beitrag dieser Leaf-Gruppe zur aktuellen Reise.',
                verbose_name='Aktuelle Reise-Velos',
            ),
        ),
        migrations.AddIndex(
            model_name='leafgrouptravelcontribution',
            index=models.Index(
                fields=['track', '-current_travel_velos'],
                name='api_leafgro_track_velos_idx',
            ),
        ),
        migrations.RunPython(backfill_travel_velos_fields, migrations.RunPython.noop),
    ]
