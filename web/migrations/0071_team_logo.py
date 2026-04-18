# Generated migration for adding logo field to Team model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0070_update_league_renewal_architecture'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='logo',
            field=models.ImageField(blank=True, null=True, upload_to='team_logos/', help_text='Team logo image (displayed as avatar)'),
        ),
    ]
