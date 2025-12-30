"""Add optional middle_name to Player model.

Generated manually to add the `middle_name` CharField (nullable, blankable).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0002_alter_player_position_importrun"),
    ]

    operations = [
        migrations.AddField(
            model_name="player",
            name="middle_name",
            field=models.CharField(max_length=50, null=True, blank=True),
        ),
    ]

