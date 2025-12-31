"""Ensure Player.team exists and remove ImportRun.team.

This migration restores the `player.team` FK and removes the incorrect
`importrun.team` field that was added/removed by earlier conflicting migrations.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0008_remove_player_team_importrun_team"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="importrun",
            name="team",
        ),

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
