from django import template

register = template.Library()

# NLL Team abbreviations mapping
TEAM_ABBREVIATIONS = {
    "Toronto Rock": "TOR",
    "Calgary Roughnecks": "CGY",
    "Saskatchewan Rush": "SAS",
    "Winnipeg MIL": "WIN",
    "Buffalo Bandits": "BUF",
    "New York Riptide": "NYR",
    "Vancouver Warriors": "VAN",
    "Edmonton Oil Kings": "EDM",
    "Ottawa Black Bears": "OTT",
    "Panther City Lacrosse Club": "PAN",
    "Las Vegas Desert Dogs": "LV",
    "Oshawa FireWolves": "OSH",
    "Halifax Thunderbirds": "HAL",
    "Rochester Knighthawks": "ROC",
}

@register.filter
def get_item(lst, index):
    """Get item from list by index"""
    try:
        return lst[index]
    except (IndexError, TypeError, KeyError):
        return False

@register.filter
def team_abbr(team_name):
    """Get team abbreviation from full team name"""
    if not team_name:
        return ""
    return TEAM_ABBREVIATIONS.get(team_name, team_name[:3].upper())

@register.filter
def opponent_abbr(opponent_string):
    """Abbreviate opponent matchup string (e.g., 'Toronto Rock @ Calgary Roughnecks' -> 'TOR @ CGY')"""
    if not opponent_string or opponent_string == "BYE":
        return opponent_string
    
    # Handle both " @ " and " vs " formats
    if " @ " in opponent_string:
        parts = opponent_string.split(" @ ")
    elif " vs " in opponent_string:
        parts = opponent_string.split(" vs ")
    else:
        return opponent_string
    
    if len(parts) == 2:
        home = parts[0].strip()
        away = parts[1].strip()
        home_abbr = TEAM_ABBREVIATIONS.get(home, home[:3].upper() if home else "")
        away_abbr = TEAM_ABBREVIATIONS.get(away, away[:3].upper() if away else "")
        separator = " @ " if " @ " in opponent_string else " vs "
        return f"{home_abbr}{separator}{away_abbr}"
    
    return opponent_string
