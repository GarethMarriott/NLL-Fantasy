import re

with open('web/templates/web/team_detail.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

stack = []
for_count = 0

for i, line in enumerate(lines, 1):
    # Find all opening tags
    if re.search(r'{%\s+for\s+', line):
        match = re.search(r'{%\s+for\s+(\w+)', line)
        var_name = match.group(1) if match else '?'
        stack.append(('for', i, var_name, line.strip()))
        for_count += 1
    
    # Find all closing tags
    if re.search(r'{%\s+endfor\s*%}', line):
        if stack and stack[-1][0] == 'for':
            popped = stack.pop()
            if i == 729:
                print(f'Line {i}: Found endfor')
                print(f'  Closes: {popped[0]} opened at line {popped[1]} (variable: {popped[2]})')
                print(f'  Current stack: {[(t[0], t[1], t[2]) for t in stack]}')
        else:
            print(f'Line {i}: endfor with no matching for')
            if stack:
                print(f'  Top of stack: {stack[-1][:3]}')

print(f'\nTotal for loops found: {for_count}')
