from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0080_add_pup_transaction_type'),
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
                    ('hold_out', 'Hold Out'),
                    ('activated', 'Activated/Returned'),
                    ('retired', 'Retired'),
                    ('other', 'Other'),
                ],
                help_text='Type of transaction',
                max_length=20,
            ),
        ),
    ]