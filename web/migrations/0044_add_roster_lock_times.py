# Generated migration for adding roster lock/unlock times to Week model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0043_bugreport'),
    ]

    operations = [
        migrations.AddField(
            model_name='week',
            name='roster_lock_time',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='When rosters lock (typically Friday 5pm PT)'
            ),
        ),
        migrations.AddField(
            model_name='week',
            name='roster_unlock_time',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='When rosters unlock (typically Monday 9am PT)'
            ),
        ),
    ]
