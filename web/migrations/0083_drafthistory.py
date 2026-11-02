from django.db import migrations, models
import django.db.models.deletion


def archive_completed_drafts(apps, schema_editor):
    Draft = apps.get_model("web", "Draft")
    DraftPick = apps.get_model("web", "DraftPick")
    RookieDraft = apps.get_model("web", "RookieDraft")
    RookieDraftPick = apps.get_model("web", "RookieDraftPick")
    DraftHistory = apps.get_model("web", "DraftHistory")

    for draft in Draft.objects.filter(completed=True).select_related("league"):
        picks = list(DraftPick.objects.filter(draft_id=draft.id).select_related("team", "player").order_by("overall_pick"))
        results = [
            {
                "round": pick.round,
                "pick_number": pick.pick_number,
                "overall_pick": pick.overall_pick,
                "team_name": pick.team.name,
                "player_name": f"{pick.player.first_name} {pick.player.last_name}" if pick.player else None,
                "position": pick.player.position if pick.player else None,
                "nll_team": pick.player.nll_team if pick.player else None,
            }
            for pick in picks
        ]
        DraftHistory.objects.get_or_create(
            league=draft.league,
            source_model="draft",
            source_draft_id=draft.id,
            defaults={
                "season_year": draft.league.season,
                "draft_type": draft.draft_type,
                "draft_style": draft.draft_style,
                "total_rounds": draft.total_rounds,
                "completed_at": draft.completed_at,
                "results": results,
            },
        )

    for draft in RookieDraft.objects.filter(completed=True).select_related("league"):
        picks = list(RookieDraftPick.objects.filter(draft_id=draft.id).select_related("team", "player").order_by("overall_pick"))
        results = [
            {
                "round": pick.round,
                "pick_number": pick.pick_number,
                "overall_pick": pick.overall_pick,
                "team_name": pick.team.name,
                "player_name": f"{pick.player.first_name} {pick.player.last_name}" if pick.player else None,
                "position": pick.player.position if pick.player else None,
                "nll_team": pick.player.nll_team if pick.player else None,
            }
            for pick in picks
        ]
        DraftHistory.objects.get_or_create(
            league=draft.league,
            source_model="rookie_draft",
            source_draft_id=draft.id,
            defaults={
                "season_year": draft.season_year,
                "draft_type": "rookie",
                "draft_style": draft.draft_style,
                "total_rounds": max((pick.round for pick in picks), default=0),
                "completed_at": draft.completed_at,
                "results": results,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0082_dynasty_startup_draft"),
    ]

    operations = [
        migrations.CreateModel(
            name="DraftHistory",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("season_year", models.PositiveIntegerField()),
                ("draft_type", models.CharField(choices=[("startup", "Dynasty Start Up"), ("rookie", "Rookie"), ("redraft", "Re-Draft")], max_length=10)),
                ("draft_style", models.CharField(blank=True, max_length=10)),
                ("total_rounds", models.PositiveSmallIntegerField()),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("source_model", models.CharField(max_length=20)),
                ("source_draft_id", models.PositiveBigIntegerField()),
                ("results", models.JSONField(default=list)),
                ("archived_at", models.DateTimeField(auto_now_add=True)),
                ("league", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="draft_archives", to="web.league")),
            ],
            options={
                "ordering": ["-season_year", "-completed_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="drafthistory",
            index=models.Index(fields=["league", "-season_year"], name="web_drafthi_league__3b6934_idx"),
        ),
        migrations.AddConstraint(
            model_name="drafthistory",
            constraint=models.UniqueConstraint(fields=("league", "source_model", "source_draft_id"), name="unique_draft_history_source"),
        ),
        migrations.RunPython(archive_completed_drafts, migrations.RunPython.noop),
    ]