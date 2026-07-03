# Generated manually for Velos Phase C

from django.db import migrations, models
from decimal import Decimal


def copy_coins_to_velos_year_end(apps, schema_editor):
    YearEndSnapshot = apps.get_model('api', 'YearEndSnapshot')
    YearEndSnapshotDetail = apps.get_model('api', 'YearEndSnapshotDetail')
    Group = apps.get_model('api', 'Group')
    Cyclist = apps.get_model('api', 'Cyclist')

    for snapshot in YearEndSnapshot.objects.all():
        group = Group.objects.filter(pk=snapshot.group_id).first()
        if group:
            snapshot.group_total_velos = int(getattr(group, 'velos_total', 0) or 0)
        else:
            snapshot.group_total_velos = int(getattr(snapshot, 'group_total_coins', 0) or 0)
        snapshot.save(update_fields=['group_total_velos'])

    for detail in YearEndSnapshotDetail.objects.all():
        if detail.cyclist_id:
            cyclist = Cyclist.objects.filter(pk=detail.cyclist_id).first()
            detail.velos_total = int(getattr(cyclist, 'velos_balance', 0) or 0) if cyclist else 0
        elif detail.group_id:
            group = Group.objects.filter(pk=detail.group_id).first()
            detail.velos_total = int(getattr(group, 'velos_total', 0) or 0) if group else 0
        else:
            detail.velos_total = int(getattr(detail, 'coins_total', 0) or 0)
        detail.save(update_fields=['velos_total'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_velos_phase_a'),
    ]

    operations = [
        migrations.AddField(
            model_name='yearendsnapshot',
            name='group_total_velos',
            field=models.IntegerField(default=0, verbose_name='Gruppen-Velos gesamt'),
        ),
        migrations.AddField(
            model_name='yearendsnapshotdetail',
            name='velos_total',
            field=models.IntegerField(default=0, verbose_name='Velos zum Abschlusszeitpunkt'),
        ),
        migrations.RunPython(copy_coins_to_velos_year_end, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='yearendsnapshot',
            name='group_total_coins',
        ),
        migrations.RemoveField(
            model_name='yearendsnapshotdetail',
            name='coins_total',
        ),
        migrations.RemoveField(
            model_name='cyclist',
            name='coin_conversion_factor',
        ),
        migrations.RemoveField(
            model_name='cyclist',
            name='coins_spendable',
        ),
        migrations.RemoveField(
            model_name='cyclist',
            name='coins_total',
        ),
        migrations.RemoveField(
            model_name='group',
            name='coins_total',
        ),
    ]
