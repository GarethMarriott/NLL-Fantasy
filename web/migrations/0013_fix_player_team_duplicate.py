"""Fix duplicate team_id column by skipping AddField, keep AlterField operations.

Migration 0012 tried to add Player.team, but the column already exists from
earlier migrations. This migration applies only the AlterField operations
that don't conflict.
"""
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0012_alter_team_options_remove_importrun_team_player_team_and_more'),
    ]

    operations = [
        # Skip the AddField for 'team' since it already exists.
        # Instead, only apply the AlterField operations that are safe.
        migrations.AlterField(
            model_name='player',
            name='number',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text='Jersey number (0-99). Not required to be unique.',
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(99)
                ]
            ),
        ),
        migrations.AlterField(
            model_name='player',
            name='position',
            field=models.CharField(
                choices=[('O', 'Offence'), ('D', 'Defence'), ('T', 'Transition'), ('G', 'Goalie')],
                max_length=1
            ),
        ),
    ]
