from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0081_add_hold_out_transaction_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="league",
            name="startup_draft_completed",
            field=models.BooleanField(
                default=True,
                help_text="Whether a dynasty league has completed its initial all-player startup draft",
            ),
        ),
        migrations.AddField(
            model_name="draft",
            name="draft_type",
            field=models.CharField(
                choices=[("redraft", "Re-Draft"), ("startup", "Dynasty Start Up")],
                default="redraft",
                help_text="Whether this is a re-draft or a dynasty start up draft",
                max_length=10,
            ),
        ),
    ]