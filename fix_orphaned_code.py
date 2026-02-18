#!/usr/bin/env python3
import re

with open('web/views/__init__.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find reorder_draft_picks function and fix it
# Pattern: find the function, the reorder_rookie_draft_picks call, and remove orphaned code
pattern = r'(success, message = reorder_rookie_draft_picks\(draft\.id, new_team_order\))\s+(?:else:|position =).*?(?=\n\n@login_required\n@require_POST\ndef make_draft_pick)'

replacement = r'''\1

    if success:
        messages.success(request, message)
        post_league_message(league, f"📋 Commissioner reordered draft picks")
    else:
        messages.error(request, message)
    
    return JsonResponse({'success': success, 'message': message})


@login_required
@require_POST
def make_draft_pick'''

content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('web/views/__init__.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed reorder_draft_picks function')
