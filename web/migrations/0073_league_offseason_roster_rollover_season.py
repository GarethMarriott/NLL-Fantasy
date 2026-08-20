from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0072_league_offseason_rosters_open'),
    ]

    operations = [
        migrations.AddField(
            model_name='league',
            name='offseason_roster_rollover_season',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Season created by the most recent dynasty offseason roster rollover',
                null=True,
            ),
        ),
    ]