import re

with open('web/templates/web/team_detail.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

stack = []

for i, line in enumerate(lines, 1):
    # Find all opening tags
    if re.search(r'{%\s+for\s+', line):
        match = re.search(r'{%\s+for\s+(\w+)\s+in\s+([^%]+)', line)
        var_name = match.group(1) if match else '?'
        in_var = match.group(2).strip() if match else '?'
        stack.append(('for', i, var_name, in_var, line.strip()[:60]))
    
    # Find all closing tags
    if re.search(r'{%\s+endfor\s*%}', line):
        if stack and stack[-1][0] == 'for':
            popped = stack.pop()
            print(f'Line {popped[1]}: for {popped[2]} in {popped[3]:30} ... closed at line {i}')
        else:
            print(f'Line {i}: endfor with no matching for opening')
            if stack:
                print(f'  Top of stack: for at line {stack[-1][1]}')

if stack:
    print(f'\nUnclosed for loops:')
    for tag, line_num, var, in_var, content in stack:
        print(f'  Line {line_num}: for {var} in {in_var}')
