import django.core.validators
from django.db import migrations, models
from django.db.models import F


def merge_goalie_slots(apps, schema_editor):
    League = apps.get_model('web', 'League')
    Roster = apps.get_model('web', 'Roster')

    for league in League.objects.all().iterator():
        old_defense_slots = league.roster_defense
        goalie_starters = list(
            Roster.objects.filter(
                league_id=league.id,
                slot_assignment='starter_g',
            ).order_by('team_id', 'id')
        )
        next_slot_by_team = {}
        for roster in goalie_starters:
            next_slot = next_slot_by_team.get(roster.team_id, old_defense_slots + 1)
            roster.slot_assignment = f'starter_d{next_slot}'
            roster.save(update_fields=['slot_assignment'])
            next_slot_by_team[roster.team_id] = next_slot + 1

    League.objects.update(
        roster_defense=F('roster_defense') + F('roster_goalies'),
        roster_goalies=0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0075_playernllteam'),
    ]

    operations = [
        migrations.RunPython(merge_goalie_slots, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='league',
            name='allow_transition_in_goalies',
        ),
        migrations.AlterField(
            model_name='league',
            name='roster_defense',
            field=models.PositiveSmallIntegerField(default=8, help_text='Number of defense slots, shared by defenders and goalies', validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(20)]),
        ),
        migrations.AlterField(
            model_name='league',
            name='roster_goalies',
            field=models.PositiveSmallIntegerField(default=0, help_text='Deprecated: goalie capacity is included in defense slots', validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(20)]),
        ),
        migrations.AlterField(
            model_name='league',
            name='roster_format',
            field=models.CharField(choices=[('bestball', 'Best Ball (no lineup management)'), ('traditional', 'Traditional (starter slots: Offense and Defense)')], default='bestball', help_text='League format: Best Ball (all players score) or Traditional (only starters score)', max_length=15),
        ),
        migrations.AlterField(
            model_name='roster',
            name='slot_assignment',
            field=models.CharField(choices=[('starter_o1', 'Starter Offense 1'), ('starter_o2', 'Starter Offense 2'), ('starter_o3', 'Starter Offense 3'), ('starter_d1', 'Starter Defense 1'), ('starter_d2', 'Starter Defense 2'), ('starter_d3', 'Starter Defense 3'), ('bench', 'Bench'), ('ir', 'Injured Reserve')], default='bench', help_text="For traditional leagues: which slot this player is assigned to. For best ball leagues: always 'bench' (not used)", max_length=20),
        ),
    ]