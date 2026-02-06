import re

with open('web/templates/web/team_detail.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

stack = []
block_tags = {'block', 'for', 'if', 'with', 'ifchanged'}
close_map = {'block': 'endblock', 'for': 'endfor', 'if': 'endif', 'with': 'endwith', 'ifchanged': 'endifchanged'}

for i, line in enumerate(lines[:750], 1):
    # Find all opening tags
    for tag in block_tags:
        if re.search(rf'{{% {tag}\s', line):
            stack.append((tag, i, line.strip()))
    
    # Find all closing tags
    for close_tag in close_map.values():
        if re.search(rf'{{% {close_tag} %}}', line):
            if stack:
                open_tag, open_line, open_content = stack[-1]
                expected_close = close_map[open_tag]
                if close_tag == expected_close:
                    stack.pop()
                else:
                    print(f'Line {i}: {close_tag} does not match opening {open_tag} at line {open_line}')
            else:
                print(f'Line {i}: {close_tag} with no matching opening tag')

print(f'\nUnclosed tags at line 750:')
for tag, line_num, content in stack:
    print(f'  {tag} opened at line {line_num}: {content}')
