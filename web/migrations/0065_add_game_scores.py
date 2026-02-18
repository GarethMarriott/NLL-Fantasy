# Generated migration for adding game score fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0064_futurerookiepick_order_finalized'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='home_score',
            field=models.PositiveSmallIntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='game',
            name='away_score',
            field=models.PositiveSmallIntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='game',
            name='winner',
            field=models.CharField(max_length=100, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='game',
            name='loser',
            field=models.CharField(max_length=100, blank=True, null=True),
        ),
    ]
