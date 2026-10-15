from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0076_merge_goalie_slots_into_defense'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='entry_draft_pick',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text='Overall NLL Entry Draft selection number',
                null=True,
            ),
        ),
    ]