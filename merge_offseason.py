#!/usr/bin/env python
"""Script to properly merge offseason functions into views/__init__.py"""

# Read the offseason functions
with open('web/views/offseason.py', 'r', encoding='utf-8') as f:
    offseason_content = f.read()

# Remove the docstring and imports
lines = offseason_content.split('\n')

# Find where the functions start (after imports and docstring)
start = 0
for i, line in enumerate(lines):
    if line.startswith('@login_required') or (line.startswith('def ') and not line.startswith('def ')):
        start = i
        break

# If we didn't find it with that logic, find first @ symbol
if start == 0:
    for i, line in enumerate(lines):
        if line.startswith('@'):
            start = i
            break

# Get just the function definitions
functions_content = '\n'.join(lines[start:])

# Append to views/__init__.py
with open('web/views/__init__.py', 'a', encoding='utf-8') as f:
    f.write('\n\n# ===== OFFSEASON MANAGEMENT VIEWS =====\n')
    f.write(functions_content)

print(f"Offseason functions appended successfully (starting from line {start})")
