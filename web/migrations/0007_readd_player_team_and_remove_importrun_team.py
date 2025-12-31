"""Re-add Player.team and remove stray ImportRun.team.

This migration reverses the accidental removal of the `player.team` FK
and removes the incorrect `importrun.team` field that was added earlier.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0006_alter_team_options_remove_player_team_importrun_team"),
    ]

    operations = [
        # Remove stray field from ImportRun if present
        migrations.RemoveField(
            model_name="importrun",
            name="team",
        ),

        # Re-add Player.team as nullable FK to Team
        migrations.AddField(
            model_name="player",
            name="team",
            field=models.ForeignKey(
                related_name="players",
                on_delete=django.db.models.deletion.SET_NULL,
                to="web.team",
                null=True,
                blank=True,
            ),
        ),
    ]
