from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
from django.db.models import F


def merge_goalie_starters_into_defense(apps, schema_editor):
    League = apps.get_model('web', 'League')
    League.objects.update(
        bestball_starters_defense=F('bestball_starters_defense') + F('bestball_starters_goalie'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0078_league_bestball_starter_slots'),
    ]

    operations = [
        migrations.RunPython(merge_goalie_starters_into_defense, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='league',
            name='bestball_starters_goalie',
        ),
        migrations.AlterField(
            model_name='league',
            name='bestball_starters_defense',
            field=models.PositiveSmallIntegerField(
                default=4,
                help_text='Number of top-scoring defense and goalie players counted weekly in best ball',
                validators=[MinValueValidator(0), MaxValueValidator(20)],
            ),
        ),
    ]