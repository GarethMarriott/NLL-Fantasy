from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0079_merge_bestball_goalies_into_defense'),
    ]

    operations = [
        migrations.AlterField(
            model_name='nlltransaction',
            name='transaction_type',
            field=models.CharField(
                choices=[
                    ('signed', 'Signed'),
                    ('traded', 'Traded'),
                    ('released', 'Released'),
                    ('waived', 'Waived'),
                    ('reassigned', 'Reassigned'),
                    ('injured_reserve', 'Placed on Injured Reserve'),
                    ('pup', 'Physically Unable to Perform'),
                    ('activated', 'Activated/Returned'),
                    ('retired', 'Retired'),
                    ('other', 'Other'),
                ],
                help_text='Type of transaction',
                max_length=20,
            ),
        ),
    ]