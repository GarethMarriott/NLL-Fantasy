#!/usr/bin/env python
import re

# Function to add IR badge after player names
def add_ir_badges(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    output_lines = []
    
    for i, line in enumerate(lines):
        output_lines.append(line)
        
        # Check if this line has a player modal call and player name ending
        if 'onclick="showPlayerModal' in line and '{{ slot.player.last_name }}, {{ slot.player.first_name }}</span>' in line:
            # Check if next line already has IR badge
            if i + 1 < len(lines) and 'is_on_injured_reserve' not in lines[i + 1]:
                # Get indentation
                indent = len(line) - len(line.lstrip())
                badge_line = ' ' * indent + '{% if slot.player.is_on_injured_reserve %}<span class="inline-block px-2 py-0.5 bg-red-500 text-white text-xs font-bold rounded whitespace-nowrap">IR</span>{% endif %}'
                output_lines.append(badge_line)
        
        # Check for taxi entry players
        elif 'onclick="showPlayerModal' in line and '{{ taxi_entry.player.last_name }}, {{ taxi_entry.player.first_name }}</span>' in line:
            # Check if next line already has IR badge
            if i + 1 < len(lines) and 'is_on_injured_reserve' not in lines[i + 1]:
                badge_line = '                    {% if taxi_entry.player.is_on_injured_reserve %}<span class="inline-block px-2 py-0.5 bg-red-500 text-white text-xs font-bold rounded whitespace-nowrap">IR</span>{% endif %}'
                output_lines.append(badge_line)
    
    content = '\n'.join(output_lines)
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f'Updated {filename}')

# Update templates
add_ir_badges('web/templates/web/team_detail.html')
add_ir_badges('web/templates/web/matchups.html')

print('Done!')
