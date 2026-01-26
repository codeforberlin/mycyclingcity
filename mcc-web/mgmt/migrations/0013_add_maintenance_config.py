# Generated manually
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('mgmt', '0012_add_enable_request_logging_back'),
    ]

    operations = [
        migrations.CreateModel(
            name='MaintenanceConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_whitelist', models.TextField(blank=True, help_text='Eine IP-Adresse oder ein CIDR-Block pro Zeile. Beispiel:\n192.168.1.100\n10.0.0.0/8\n172.16.0.0/12\nDiese IPs können während der Wartung auf die Website zugreifen.', null=True, verbose_name='IP Whitelist')),
                ('allow_admin_during_maintenance', models.BooleanField(default=True, help_text='Wenn aktiviert, können Superuser auch ohne IP-Whitelist auf /admin/ zugreifen', verbose_name='Admin-Zugriff während Wartung erlauben')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Zuletzt aktualisiert')),
                ('updated_by', models.ForeignKey(blank=True, help_text='Benutzer, der diese Einstellung zuletzt geändert hat', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Aktualisiert von')),
            ],
            options={
                'verbose_name': 'Maintenance Configuration',
                'verbose_name_plural': 'Maintenance Configuration',
            },
        ),
    ]
