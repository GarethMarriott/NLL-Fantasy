from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0071_team_logo'),
    ]

    operations = [
        migrations.AddField(
            model_name='league',
            name='offseason_rosters_open',
            field=models.BooleanField(
                default=False,
                help_text='Allow dynasty teams to add and drop non-rookies outside Weeks 1-21',
            ),
        ),
    ]