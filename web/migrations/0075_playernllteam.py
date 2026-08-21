from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0074_player_rookie_season_player_seasons_played'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlayerNLLTeam',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.PositiveSmallIntegerField(help_text='NLL season ending year')),
                ('nll_team', models.CharField(max_length=50)),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='nll_team_seasons', to='web.player')),
                ('source_transaction', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='team_history_updates', to='web.nlltransaction')),
            ],
        ),
        migrations.AddConstraint(
            model_name='playernllteam',
            constraint=models.UniqueConstraint(fields=('player', 'season'), name='unique_player_nll_team_per_season'),
        ),
        migrations.AddIndex(
            model_name='playernllteam',
            index=models.Index(fields=['season', 'nll_team'], name='web_playern_season_79fce5_idx'),
        ),
    ]