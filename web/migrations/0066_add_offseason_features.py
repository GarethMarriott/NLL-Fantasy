# Generated migration for offseason features

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0065_add_game_scores'),
    ]

    operations = [
        # Add offseason tracking fields to League
        migrations.AddField(
            model_name='league',
            name='season',
            field=models.PositiveIntegerField(default=2026, help_text='Current season year'),
        ),
        migrations.AddField(
            model_name='league',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', 'Season in progress'),
                    ('season_complete', 'Season ended, awaiting renewal'),
                    ('renewal_complete', 'League renewed for new season'),
                ],
                default='active',
                help_text='Current league status',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='league',
            name='season_winner',
            field=models.ForeignKey(
                blank=True,
                help_text='The team that won the championship',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='seasons_won',
                to='web.team',
            ),
        ),
        migrations.AddField(
            model_name='league',
            name='draft_locked',
            field=models.BooleanField(
                default=False,
                help_text='Set to True to lock rosters during active draft (redraft leagues only)'
            ),
        ),
        # Add roster locking fields to Roster
        migrations.AddField(
            model_name='roster',
            name='is_locked',
            field=models.BooleanField(
                default=False,
                help_text='Whether this roster is locked and cannot be modified'
            ),
        ),
        migrations.AddField(
            model_name='roster',
            name='locked_reason',
            field=models.CharField(
                choices=[
                    ('offseason', 'Offseason - awaiting league renewal'),
                    ('draft_active', 'Draft is currently active'),
                    ('week_active', 'Week is currently active'),
                ],
                default='',
                help_text='Reason why roster is locked',
                max_length=20,
            ),
        ),
        # Add season field to Roster to track which season roster is for
        migrations.AddField(
            model_name='roster',
            name='season',
            field=models.PositiveIntegerField(default=2026, help_text='Season year this roster is for'),
        ),
    ]
