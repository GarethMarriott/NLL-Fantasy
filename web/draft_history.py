from .models import DraftHistory


def _serialize_picks(picks):
    return [
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


def archive_draft(draft, season_year=None):
    """Store or refresh the immutable snapshot for a completed regular draft."""
    picks = draft.picks.select_related("team", "player").order_by("overall_pick")
    return DraftHistory.objects.update_or_create(
        league=draft.league,
        source_model="draft",
        source_draft_id=draft.id,
        defaults={
            "season_year": season_year or draft.league.season,
            "draft_type": draft.draft_type,
            "draft_style": draft.draft_style,
            "total_rounds": draft.total_rounds,
            "completed_at": draft.completed_at,
            "results": _serialize_picks(picks),
        },
    )


def archive_rookie_draft(draft):
    """Store or refresh the immutable snapshot for a completed rookie draft."""
    picks = draft.picks.select_related("team", "player").order_by("overall_pick")
    return DraftHistory.objects.update_or_create(
        league=draft.league,
        source_model="rookie_draft",
        source_draft_id=draft.id,
        defaults={
            "season_year": draft.season_year,
            "draft_type": DraftHistory.DraftType.ROOKIE,
            "draft_style": draft.draft_style,
            "total_rounds": max((pick.round for pick in picks), default=0),
            "completed_at": draft.completed_at,
            "results": _serialize_picks(picks),
        },
    )