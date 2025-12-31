"""Add Team model and Player.team FK.

Generated manually for repository changes.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0002_alter_player_position_importrun"),
    ]

    operations = [
        migrations.CreateModel(
            name="Team",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="player",
            name="team",
            field=models.ForeignKey(
                related_name="players",
                on_delete=django.db.models.deletion.SET_NULL,
                blank=True,
                to="web.team",
                null=True,
            ),
        ),
    ]
