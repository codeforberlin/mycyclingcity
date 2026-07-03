# Generated manually for Velos Phase A

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0015_add_year_end_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='hourlymetric',
            name='velos',
            field=models.IntegerField(default=0, verbose_name='Velos'),
        ),
        migrations.AddField(
            model_name='cyclist',
            name='velos_balance',
            field=models.IntegerField(
                default=0,
                help_text='Aktuelles einlösbares Guthaben des RFID-Accounts. Wird bei Einlösung auf 0 gesetzt.',
                verbose_name='Velos-Guthaben (einlösbar)',
            ),
        ),
        migrations.AddField(
            model_name='group',
            name='velos_total',
            field=models.IntegerField(default=0, verbose_name='Velos gesamt (Ledger)'),
        ),
        migrations.AddField(
            model_name='group',
            name='velos_spendable',
            field=models.IntegerField(default=0, verbose_name='Velos ausgebbar'),
        ),
        migrations.AddField(
            model_name='group',
            name='mc_username',
            field=models.CharField(
                blank=True,
                help_text='Nur für Leaf-Gruppen. Überschreibt Radler-Minecraft-Namen für die Synchronisation.',
                max_length=100,
                null=True,
                verbose_name='Minecraft-Name (Gruppe)',
            ),
        ),
        migrations.CreateModel(
            name='CyclistVelosRedemption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('velos_redeemed', models.IntegerField(verbose_name='Eingelöste Velos')),
                ('redeemed_at', models.DateTimeField(auto_now_add=True, verbose_name='Eingelöst am')),
                ('note', models.TextField(blank=True, verbose_name='Notiz')),
                ('external_currency', models.CharField(
                    blank=True,
                    help_text='z.B. Wuhlis',
                    max_length=100,
                    verbose_name='Externe Währung',
                )),
                ('cyclist', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='velos_redemptions',
                    to='api.cyclist',
                    verbose_name='Radler',
                )),
                ('leaf_group', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='velos_redemptions',
                    to='api.group',
                    verbose_name='Leaf-Gruppe',
                )),
                ('redeemed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Eingelöst von',
                )),
            ],
            options={
                'verbose_name': 'Velos-Einlösung',
                'verbose_name_plural': 'Velos-Einlösungen',
                'ordering': ['-redeemed_at'],
            },
        ),
    ]
