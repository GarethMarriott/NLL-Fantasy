from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0013_fix_player_team_duplicate"),
    ]

    operations = [
        migrations.AddField(
            model_name="player",
            name="assigned_side",
            field=models.CharField(
                blank=True,
                choices=[("O", "Offence"), ("D", "Defence"), ("T", "Transition"), ("G", "Goalie")],
                help_text="Override for lineup slot (use O or D for Transition players)",
                max_length=1,
                null=True,
            ),
        ),
    ]
