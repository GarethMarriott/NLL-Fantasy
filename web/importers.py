import csv
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_date

from web.models import Player, Week, PlayerWeekStat, ImportRun
from web.models import Team


INT_FIELDS = [
    "goals",
    "assists",
    "points",
    "penalty_minutes",
    "powerplay_goals",
    "powerplay_assists",
    "shorthanded_goals",
    "loose_balls",
    "turnovers",
    "caused_turnovers",
    "blocked_shots",
    "shots_on_goal",
]


REQUIRED_COLUMNS = [
    "external_id",
    "first_name",
    "last_name",
    "number",
    "position",
    "season",
    "week_number",
    "start_date",
    "end_date",
]


def _required(row: Dict[str, Any], field: str, line_no: int) -> str:
    if field not in row:
        raise ValidationError(f"Missing required column '{field}' in CSV header.")
    val = (row.get(field) or "").strip()
    if val == "":
        raise ValidationError(f"Line {line_no}: Missing required value for '{field}'.")
    return val


def _to_int(value: str, field: str, line_no: int) -> int:
    v = (value or "").strip()
    if v == "":
        return 0
    try:
        return int(v)
    except ValueError:
        raise ValidationError(f"Line {line_no}: Invalid integer for '{field}': {value!r}")


def _to_decimal_pct(value: str, line_no: int) -> Decimal:
    v = (value or "").strip()
    if v == "":
        return Decimal("0")
    try:
        d = Decimal(v)
    except InvalidOperation:
        raise ValidationError(f"Line {line_no}: Invalid decimal for faceoff_percentage: {value!r}")
    if d < 0 or d > 100:
        raise ValidationError(f"Line {line_no}: faceoff_percentage out of range 0..100: {value!r}")
    return d


@transaction.atomic
def import_weekly_stats_csv(import_run: ImportRun) -> Tuple[str, Dict[str, int]]:
    """
    Reads the CSV file from import_run.uploaded_file and upserts:
      - Player (by external_id)
      - Week (by season+week_number)
      - PlayerWeekStat (by player+week)

    Returns: (log_text, counters_dict)
    Raises ValidationError on problems (transaction rolled back).
    """

    # Counters
    counters = dict(
        players_created=0,
        players_updated=0,
        weeks_created=0,
        weeks_updated=0,
        stats_created=0,
        stats_updated=0,
    )

    # Cache for speed
    week_cache: Dict[tuple[int, int], Week] = {}
    player_cache: Dict[str, Player] = {}

    # Open uploaded file
    import_run.uploaded_file.open("rb")
    try:
        # utf-8-sig handles BOM from Excel exports
        text_stream = (line.decode("utf-8-sig") for line in import_run.uploaded_file.readlines())
    finally:
        import_run.uploaded_file.close()

    reader = csv.DictReader(text_stream)
    if reader.fieldnames is None:
        raise ValidationError("CSV has no header row.")

    # Validate required header columns
    header = [h.strip() for h in reader.fieldnames if h]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValidationError(f"CSV missing required columns: {', '.join(missing)}")

    for line_no, row in enumerate(reader, start=2):  # header is line 1
        # --- Player ---
        external_id = _required(row, "external_id", line_no)
        first_name = _required(row, "first_name", line_no)
        last_name = _required(row, "last_name", line_no)
        number = _to_int(_required(row, "number", line_no), "number", line_no)
        position = _required(row, "position", line_no)

        if position not in dict(Player.Position.choices):
            raise ValidationError(f"Line {line_no}: invalid position {position!r}. Use one of O,D,T,G.")

        # --- Week ---
        season = _to_int(_required(row, "season", line_no), "season", line_no)
        week_number = _to_int(_required(row, "week_number", line_no), "week_number", line_no)

        start_date_str = _required(row, "start_date", line_no)
        end_date_str = _required(row, "end_date", line_no)
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        if not start_date or not end_date:
            raise ValidationError(
                f"Line {line_no}: invalid start_date/end_date (expected YYYY-MM-DD). "
                f"Got {start_date_str!r}, {end_date_str!r}"
            )

        # --- Stats ---
        stat_defaults: Dict[str, Any] = {}
        for field in INT_FIELDS:
            stat_defaults[field] = _to_int(row.get(field, ""), field, line_no)

        stat_defaults["faceoff_percentage"] = _to_decimal_pct(row.get("faceoff_percentage", ""), line_no)
        stat_defaults["source_file"] = import_run.original_filename or import_run.uploaded_file.name

        # --- Upsert Week ---
        wk_key = (season, week_number)
        week = week_cache.get(wk_key)
        if week is None:
            week, created = Week.objects.update_or_create(
                season=season,
                week_number=week_number,
                defaults={"start_date": start_date, "end_date": end_date},
            )
            week_cache[wk_key] = week
            if created:
                counters["weeks_created"] += 1
            else:
                counters["weeks_updated"] += 1
        else:
            # keep dates consistent
            if week.start_date != start_date or week.end_date != end_date:
                week.start_date = start_date
                week.end_date = end_date
                week.save(update_fields=["start_date", "end_date", "updated_at"])
                counters["weeks_updated"] += 1

        # --- Upsert Player ---
        player = player_cache.get(external_id)
        if player is None:
            player, created = Player.objects.update_or_create(
                external_id=external_id,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "number": number,
                    "position": position,
                    "active": True,
                },
            )
            player_cache[external_id] = player
            if created:
                counters["players_created"] += 1
            else:
                counters["players_updated"] += 1
        else:
            changed = (
                player.first_name != first_name
                or player.last_name != last_name
                or player.number != number
                or player.position != position
            )
            if changed:
                player.first_name = first_name
                player.last_name = last_name
                player.number = number
                player.position = position
                player.save(update_fields=["first_name", "last_name", "number", "position", "updated_at"])
                counters["players_updated"] += 1

        # --- Upsert Weekly Stats ---
        stat_obj, created = PlayerWeekStat.objects.update_or_create(
            player=player,
            week=week,
            defaults=stat_defaults,
        )
        if created:
            counters["stats_created"] += 1
        else:
            counters["stats_updated"] += 1

    log_lines = [
        "Import complete.",
        f"Players: +{counters['players_created']} created, {counters['players_updated']} updated",
        f"Weeks:   +{counters['weeks_created']} created, {counters['weeks_updated']} updated",
        f"Stats:   +{counters['stats_created']} created, {counters['stats_updated']} updated",
    ]
    return "\n".join(log_lines), counters


@transaction.atomic
def import_teams_csv(import_run: ImportRun) -> Tuple[str, Dict[str, int]]:
    """Read teams CSV from import_run.uploaded_file and create Teams + assign Players.

    Expected minimal columns: team (or team_name), first_name, last_name.
    Optional: number, position, external_id
    """
    counters = {"teams_created": 0, "players_created": 0, "players_updated": 0}

    import_run.uploaded_file.open("rb")
    try:
        text_stream = (line.decode("utf-8-sig") for line in import_run.uploaded_file.readlines())
    finally:
        import_run.uploaded_file.close()

    reader = csv.DictReader(text_stream)
    if reader.fieldnames is None:
        raise ValidationError("CSV has no header row.")

    header = [h.strip() for h in reader.fieldnames if h]
    # find required columns (accept several aliases; include fteam_id)
    col_map = {h.lower(): h for h in header}
    team_col = None
    matched_team_alias = None
    for n in ("team", "team_name", "teamname", "fteam_id"):
        if n in col_map:
            team_col = col_map[n]
            matched_team_alias = n
            break
    first_col = None
    for n in ("first_name", "firstname", "first"):
        if n in col_map:
            first_col = col_map[n]
            break
    last_col = None
    for n in ("last_name", "lastname", "last"):
        if n in col_map:
            last_col = col_map[n]
            break

    if not team_col or not first_col or not last_col:
        raise ValidationError("Teams CSV must include columns: team, first_name, last_name")

    # optional (accept p_number as alias)
    number_col = None
    for n in ("number", "jersey", "p_number"):
        if n in col_map:
            number_col = col_map[n]
            break
    pos_col = None
    for n in ("position", "pos"):
        if n in col_map:
            pos_col = col_map[n]
            break
    ext_col = None
    for n in ("external_id", "externalid", "id"):
        if n in col_map:
            ext_col = col_map[n]
            break

    for line_no, row in enumerate(reader, start=2):
        team_name = (row.get(team_col) or "").strip()
        first = (row.get(first_col) or "").strip()
        last = (row.get(last_col) or "").strip()
        if not team_name or not first or not last:
            raise ValidationError(f"Line {line_no}: missing team/first_name/last_name")

        number = None
        if number_col:
            nval = (row.get(number_col) or "").strip()
            if nval:
                try:
                    number = int(nval)
                except ValueError:
                    raise ValidationError(f"Line {line_no}: invalid number {nval!r}")

        position = (row.get(pos_col) or "").strip() if pos_col else ""
        if position and position not in dict(Player.Position.choices):
            # normalize some common values
            p = position.upper()
            if p in ("F", "FORWARD", "OFFENCE", "OFFENSE"):
                position = "O"
            elif p in ("D", "DEFENCE", "DEFENSE"):
                position = "D"
            elif p in ("T", "TRANSITION"):
                position = "T"
            elif p in ("G", "GOALIE"):
                position = "G"
            else:
                raise ValidationError(f"Line {line_no}: invalid position {position!r}")

        external = (row.get(ext_col) or "").strip() if ext_col else None

        # If the CSV used the `fteam_id` column, treat the value as the team identifier
        # and match/create Team by name equal to that identifier. Do not treat it as a DB PK.
        if matched_team_alias == "fteam_id":
            team, created = Team.objects.get_or_create(name=team_name)
            if created:
                counters["teams_created"] += 1
        else:
            # For other team column types, allow numeric values to be interpreted as PK
            team = None
            if team_name.isdigit():
                try:
                    team = Team.objects.filter(id=int(team_name)).first()
                except Exception:
                    team = None

            if not team:
                team, created = Team.objects.get_or_create(name=team_name)
                if created:
                    counters["teams_created"] += 1

        player = None
        if external:
            player = Player.objects.filter(external_id=external).first()

        if not player:
            qs = Player.objects.filter(first_name__iexact=first, last_name__iexact=last)
            if number is not None:
                qs = qs.filter(number=number)
            player = qs.first()

        if player:
            changed = False
            if getattr(player, "team_id", None) != (team.id if team else None):
                player.team = team
                changed = True
            if number is not None and player.number != number:
                player.number = number
                changed = True
            if position and player.position != position:
                player.position = position
                changed = True
            if external and player.external_id != external:
                player.external_id = external
                changed = True
            if changed:
                player.save()
                counters["players_updated"] += 1
        else:
            Player.objects.create(
                first_name=first,
                last_name=last,
                number=number or 0,
                position=position or "O",
                external_id=external or None,
                active=True,
                team=team,
            )
            counters["players_created"] += 1

    log_lines = ["Teams import complete.", f"Teams: +{counters['teams_created']}", f"Players: +{counters['players_created']} created, {counters['players_updated']} updated"]
    return "\n".join(log_lines), counters
