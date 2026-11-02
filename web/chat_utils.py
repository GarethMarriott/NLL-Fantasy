from datetime import datetime, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import TeamChatMessage


def get_team_unread_counts(user_team_id, other_team_ids, chat_last_read):
    """Return unread message counts for each private chat involving a team."""
    unread_counts = {team_id: 0 for team_id in other_team_ids}
    if not unread_counts:
        return unread_counts

    now = timezone.now()
    conversation_filters = Q()
    pair_to_team_id = {}

    for other_team_id in unread_counts:
        team1_id, team2_id = sorted((user_team_id, other_team_id))
        chat_key = f"team_{team1_id}_{team2_id}"
        last_read = chat_last_read.get(chat_key)

        if last_read:
            try:
                cutoff = datetime.fromisoformat(last_read)
                if timezone.is_naive(cutoff):
                    cutoff = timezone.make_aware(cutoff, timezone.get_current_timezone())
            except (TypeError, ValueError):
                continue
        else:
            cutoff = now - timedelta(days=7)

        conversation_filters |= Q(
            team1_id=team1_id,
            team2_id=team2_id,
            created_at__gt=cutoff,
        )
        pair_to_team_id[(team1_id, team2_id)] = other_team_id

    if not conversation_filters:
        return unread_counts

    unread_by_pair = TeamChatMessage.objects.filter(conversation_filters).values(
        "team1_id", "team2_id"
    ).annotate(unread=Count("id"))

    for row in unread_by_pair:
        other_team_id = pair_to_team_id.get((row["team1_id"], row["team2_id"]))
        if other_team_id is not None:
            unread_counts[other_team_id] = row["unread"]

    return unread_counts
