from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0073_league_offseason_roster_rollover_season'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='rookie_season',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text='First NLL season in which the player was a rookie',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='player',
            name='seasons_played',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='Number of NLL seasons in which the player has appeared',
            ),
        ),
    ]
