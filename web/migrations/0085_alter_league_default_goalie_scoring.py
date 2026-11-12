from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0084_enforce_positive_waiver_priority"),
    ]

    operations = [
        migrations.AlterField(
            model_name="league",
            name="scoring_goalie_saves",
            field=models.DecimalField(
                decimal_places=2,
                default=0.75,
                help_text="Points per save",
                max_digits=5,
            ),
        ),
        migrations.AlterField(
            model_name="league",
            name="scoring_goalie_goals_against",
            field=models.DecimalField(
                decimal_places=2,
                default=-1.0,
                help_text="Points per goal against (typically negative)",
                max_digits=5,
            ),
        ),
    ]