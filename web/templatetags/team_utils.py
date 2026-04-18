from django import template
import hashlib

register = template.Library()

# League-specific color palettes
TEAM_COLORS = [
    '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8',
    '#F7DC6F', '#BB8FCE', '#85C1E2', '#F8B88B', '#82E0AA',
    '#F48FB1', '#AED6F1', '#F5B041', '#85C1E2', '#F8B88B',
    '#D7BDE2', '#F1948A', '#AED6F1', '#F9E79F', '#ABEBC6'
]

def get_team_color(team_id, league_id):
    """Generate a consistent color for a team within a league"""
    # Create a hash based on team_id and league_id to get a consistent color
    hash_input = f"{league_id}-{team_id}"
    hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
    color_index = hash_value % len(TEAM_COLORS)
    return TEAM_COLORS[color_index]

@register.inclusion_tag('web/components/team_avatar.html')
def team_avatar(team, size='small'):
    """Display team logo or colored circle"""
    if team.logo:
        return {
            'has_logo': True,
            'logo_url': team.logo.url,
            'team_name': team.name,
            'size': size
        }
    else:
        color = get_team_color(team.id, team.league_id)
        initials = ''.join([word[0].upper() for word in team.name.split()[:2]])
        return {
            'has_logo': False,
            'color': color,
            'initials': initials,
            'team_name': team.name,
            'size': size
        }

@register.filter
def team_color(team):
    """Get color for a team"""
    return get_team_color(team.id, team.league_id)
