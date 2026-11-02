from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0077_player_entry_draft_pick'),
    ]

    operations = [
        migrations.AddField(
            model_name='league',
            name='bestball_starters_offense',
            field=models.PositiveSmallIntegerField(default=3, help_text='Number of top-scoring offense players counted weekly in best ball', validators=[MinValueValidator(0), MaxValueValidator(20)]),
        ),
        migrations.AddField(
            model_name='league',
            name='bestball_starters_defense',
            field=models.PositiveSmallIntegerField(default=3, help_text='Number of top-scoring defense players counted weekly in best ball', validators=[MinValueValidator(0), MaxValueValidator(20)]),
        ),
        migrations.AddField(
            model_name='league',
            name='bestball_starters_goalie',
            field=models.PositiveSmallIntegerField(default=1, help_text='Number of top-scoring goalies counted weekly in best ball', validators=[MinValueValidator(0), MaxValueValidator(20)]),
        ),
    ]