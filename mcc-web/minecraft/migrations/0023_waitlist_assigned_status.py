from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0022_player_session_bootstrap_preset"),
    ]

    operations = [
        migrations.AlterField(
            model_name="minecraftsessionwaitlistentry",
            name="status",
            field=models.CharField(
                choices=[
                    ("waiting", "Wartend"),
                    ("assigned", "Zugewiesen"),
                    ("active", "Aktiv"),
                    ("done", "Erledigt"),
                    ("cancelled", "Abgebrochen"),
                ],
                db_index=True,
                default="waiting",
                max_length=16,
                verbose_name="Status",
            ),
        ),
    ]
